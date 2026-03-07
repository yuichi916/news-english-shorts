"""Navigator (Zundamon) voice line generator.

Generates Japanese host commentary lines for each video phase,
synthesizes TTS audio, and combines into a single timed audio track.

Supports:
- edge-tts (ja-JP-NanamiNeural) — default, no server required
- VOICEVOX (localhost:50021) — better Zundamon voice if available

Usage:
    from navigator_generator import generate_navigator_clips, combine_navigator_audio
    clips, narration_offset = generate_navigator_clips(script, output_dir)
    nav_path = combine_navigator_audio(clips, phase_timing, output_dir)
"""

import asyncio
import io
import json
import os
import struct
import tempfile
import urllib.request
import urllib.error
import wave

from pydub import AudioSegment

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── TTS configuration ────────────────────────────────────────────────────────
EDGE_TTS_VOICE = "ja-JP-NanamiNeural"
EDGE_TTS_RATE = "+5%"       # slightly faster for short lines
EDGE_TTS_PITCH = "+0Hz"     # natural pitch for more natural speech

VOICEVOX_URL = "http://localhost:50021"
VOICEVOX_SPEAKER_ID = 3     # ずんだもん (normal)


# ── Navigator line templates ─────────────────────────────────────────────────
# Each entry: (phase_key, time_key, list_of_templates)
# time_key maps to a key in phase_timing dict, or a callable

def _build_navigator_lines(script: dict) -> list[dict]:
    """Build navigator lines from script data.

    Uses script["navigator"]["intro"] and script["navigator"]["outro"] if available
    for news-specific commentary. Falls back to generic templates otherwise.

    Returns list of dicts: {"phase": str, "text": str, "time_key": str}
    """
    navigator = script.get("navigator", {})

    # Intro: use script-provided line or fall back to generic
    if navigator.get("intro"):
        intro_text = navigator["intro"]
    else:
        topic_ja = script.get("hook_text", script.get("topic", "ニュース"))
        if len(topic_ja) > 25:
            topic_ja = topic_ja[:25]
        intro_text = f"今日のニュースは、{topic_ja}！聞き取りチャレンジなのだ！"

    # Outro: use script-provided line or fall back to generic
    if navigator.get("outro"):
        outro_text = navigator["outro"]
    else:
        outro_text = "面白かったらチャンネル登録してほしいのだ！また明日なのだ！"

    lines = [
        {
            "phase": "hook",
            "text": intro_text,
            "time_key": "hook_start",
        },
        {
            "phase": "listen",
            "text": "英語をよく聞くのだ！",
            "time_key": "listen_card",
        },
        {
            "phase": "kp",
            "text": "キーフレーズの時間なのだ！しっかり覚えるのだ！",
            "time_key": "kp_card",
        },
        {
            "phase": "answer",
            "text": "答え合わせの時間なのだ！",
            "time_key": "answer_card",
        },
        {
            "phase": "outro",
            "text": outro_text,
            "time_key": "outro_start",
        },
    ]
    return lines


def _compute_line_offsets(phase_timing: dict) -> dict[str, float]:
    """Map time_key names to absolute video-time offsets (seconds)."""
    from video_generator import (
        HOOK_DURATION, SECTION_CARD_DURATION, ANSWER_DURATION, OUTRO_DURATION,
    )

    hook_duration = phase_timing.get("hook_duration", HOOK_DURATION)
    outro_duration = phase_timing.get("outro_duration", OUTRO_DURATION)
    kp_end = phase_timing["kp_end"]
    total = phase_timing["total_duration"]

    return {
        "hook_start": 0.3,
        "listen_card": hook_duration + 0.2,
        "kp_card": phase_timing["all_audio_end"] + 0.3,
        "answer_card": kp_end + 0.3,
        "outro_start": total - outro_duration + 0.3,
    }


# ── TTS backends ─────────────────────────────────────────────────────────────

def _start_voicevox_engine() -> bool:
    """Try to start local VOICEVOX Engine if installed."""
    import subprocess
    engine_path = os.path.join(PROJECT_DIR, "voicevox", "windows-cpu", "run.exe")
    if not os.path.exists(engine_path):
        return False
    try:
        subprocess.Popen(
            [engine_path, "--host", "127.0.0.1", "--port", "50021"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Wait for engine to start
        import time
        for _ in range(30):
            time.sleep(1)
            try:
                req = urllib.request.Request(f"{VOICEVOX_URL}/version", method="GET")
                urllib.request.urlopen(req, timeout=2)
                return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def _voicevox_available() -> bool:
    """Check if VOICEVOX engine is running, auto-start if installed."""
    try:
        req = urllib.request.Request(f"{VOICEVOX_URL}/version", method="GET")
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        # Try to auto-start engine
        print("  VOICEVOX not running, attempting to start engine...")
        if _start_voicevox_engine():
            print("  VOICEVOX Engine started successfully!")
            return True
        return False


def _tts_voicevox(text: str, output_path: str, speaker_id: int = VOICEVOX_SPEAKER_ID):
    """Generate audio via VOICEVOX API."""
    import urllib.parse

    # Step 1: audio_query
    query_url = f"{VOICEVOX_URL}/audio_query?text={urllib.parse.quote(text)}&speaker={speaker_id}"
    req = urllib.request.Request(query_url, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        query_json = resp.read()

    # Step 2: synthesis
    synth_url = f"{VOICEVOX_URL}/synthesis?speaker={speaker_id}"
    req = urllib.request.Request(
        synth_url, data=query_json, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        wav_data = resp.read()

    # Convert WAV to MP3 via pydub
    seg = AudioSegment.from_wav(io.BytesIO(wav_data))
    seg.export(output_path, format="mp3")


async def _tts_edge(text: str, output_path: str):
    """Generate audio via edge-tts."""
    import edge_tts

    communicate = edge_tts.Communicate(
        text, EDGE_TTS_VOICE, rate=EDGE_TTS_RATE, pitch=EDGE_TTS_PITCH,
    )
    await communicate.save(output_path)


def _generate_line_audio(text: str, output_path: str, use_voicevox: bool = False):
    """Generate TTS audio for a single navigator line."""
    if use_voicevox:
        _tts_voicevox(text, output_path)
    else:
        asyncio.run(_tts_edge(text, output_path))


# ── Main pipeline ────────────────────────────────────────────────────────────

def generate_navigator_clips(
    script: dict,
    output_dir: str,
    script_id: str | None = None,
) -> tuple[list[tuple[dict, AudioSegment]], float, dict[str, float]]:
    """Generate individual navigator TTS clips and compute narration offset.

    Returns:
        tuple: (clips, narration_offset, nav_durations)
            clips: list of (line_dict, AudioSegment) pairs
            narration_offset: recommended narration start time (seconds)
            nav_durations: {time_key: duration_sec} for each clip
    """
    from video_generator import HOOK_DURATION, SECTION_CARD_DURATION, NARRATION_OFFSET as DEFAULT_NARRATION_OFFSET

    use_voicevox = _voicevox_available()
    engine_name = "VOICEVOX" if use_voicevox else "edge-tts"
    print(f"  Navigator TTS engine: {engine_name}")

    lines = _build_navigator_lines(script)

    tmp_dir = tempfile.mkdtemp(prefix="nav_tts_")
    clips: list[tuple[dict, AudioSegment]] = []
    nav_durations: dict[str, float] = {}

    try:
        for i, line in enumerate(lines):
            clip_path = os.path.join(tmp_dir, f"line_{i}.mp3")
            try:
                _generate_line_audio(line["text"], clip_path, use_voicevox=use_voicevox)
                seg = AudioSegment.from_mp3(clip_path)
                clips.append((line, seg))

                duration_sec = len(seg) / 1000.0
                nav_durations[line["time_key"]] = duration_sec
                print(f"    [{line['phase']}] {line['text']} ({duration_sec:.1f}s)")
            except Exception as e:
                print(f"    [{line['phase']}] TTS failed: {e}")
                continue
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Dynamic hook phase: extend if Zundamon hook line is long
    hook_duration = HOOK_DURATION
    if "hook_start" in nav_durations:
        hook_nav_end = 0.3 + nav_durations["hook_start"]
        hook_duration = max(HOOK_DURATION, hook_nav_end + 0.5)

    # Pre-narration line offsets (using dynamic hook_duration)
    pre_narration_offsets = {
        "hook_start": 0.3,
        "listen_card": hook_duration + 0.2,
    }
    pre_narration_end = 0.0
    for line_dict, seg in clips:
        tk = line_dict["time_key"]
        if tk in pre_narration_offsets:
            offset = pre_narration_offsets[tk]
            dur = len(seg) / 1000.0
            end = offset + dur
            if end > pre_narration_end:
                pre_narration_end = end

    # Narration starts after: pre-narration nav lines + gap + section card
    narration_offset = max(DEFAULT_NARRATION_OFFSET, pre_narration_end + 0.3 + SECTION_CARD_DURATION)
    print(f"  Hook duration: {hook_duration:.1f}s (dynamic), Narration offset: {narration_offset:.1f}s")

    return clips, narration_offset, nav_durations


def combine_navigator_audio(
    clips: list[tuple[dict, AudioSegment]],
    phase_timing: dict,
    output_dir: str,
    script_id: str | None = None,
) -> tuple[str | None, list[dict]]:
    """Combine pre-generated navigator clips into a single timed audio track.

    Args:
        clips: list of (line_dict, AudioSegment) from generate_navigator_clips
        phase_timing: Dict from compute_phase_timing()
        output_dir: Directory to save the output file
        script_id: ID for filename

    Returns:
        tuple: (audio_path, navigator_timing)
            audio_path: Path to the navigator audio MP3, or None if no clips.
            navigator_timing: list of {start, end} dicts for each speech interval,
                used for ducking other audio during navigator speech.
    """
    if not clips:
        print("  No navigator lines generated.")
        return None, []

    sid = script_id or "nav"
    output_path = os.path.join(output_dir, f"{sid}_navigator.mp3")

    offsets = _compute_line_offsets(phase_timing)
    total_duration = phase_timing["total_duration"]
    total_ms = int(total_duration * 1000)

    # Sort clips chronologically by offset
    sorted_clips = sorted(
        [(offsets.get(line["time_key"], 0.0), line, seg) for line, seg in clips],
        key=lambda x: x[0],
    )

    # Trim clips to prevent overlap with the next clip
    trimmed: list[tuple[float, dict, AudioSegment]] = []
    for i, (offset_sec, line, seg) in enumerate(sorted_clips):
        if i + 1 < len(sorted_clips):
            next_offset = sorted_clips[i + 1][0]
            max_ms = int((next_offset - offset_sec) * 1000) - 50  # 50ms gap
            if max_ms > 0 and len(seg) > max_ms:
                seg = seg[:max_ms].fade_out(50)
                print(f"    [{line['phase']}] trimmed to {max_ms}ms (next clip at {next_offset:.1f}s)")
        trimmed.append((offset_sec, line, seg))

    combined = AudioSegment.silent(duration=total_ms)
    navigator_timing: list[dict] = []
    last_end_ms = 0

    for offset_sec, line, seg in trimmed:
        duration_sec = len(seg) / 1000.0
        pos_ms = int(offset_sec * 1000)

        if pos_ms + len(seg) > total_ms:
            seg = seg[:total_ms - pos_ms]
            duration_sec = len(seg) / 1000.0
        if pos_ms < total_ms:
            combined = combined.overlay(seg, position=pos_ms)

        end_ms = pos_ms + len(seg)
        if end_ms > last_end_ms:
            last_end_ms = end_ms

        navigator_timing.append({"start": offset_sec, "end": offset_sec + duration_sec})
        print(f"    [{line['phase']}] @ {offset_sec:.1f}s ({duration_sec:.1f}s)")

    # Boost volume only in regions with speech, then silence the rest
    # to prevent noise from +3dB amplification of silent regions
    fade_margin = 300  # ms fade-out after last speech
    if last_end_ms + fade_margin < total_ms:
        speech_part = combined[:last_end_ms] + 3  # +3dB on speech only
        speech_part = speech_part.fade_out(fade_margin)
        silent_part = AudioSegment.silent(duration=total_ms - last_end_ms)
        combined = speech_part + silent_part
    else:
        # Speech extends to end — boost then fade out to avoid trailing noise
        combined = combined + 3
        combined = combined.fade_out(fade_margin)

    combined.export(output_path, format="mp3")
    print(f"  Navigator audio: {output_path} ({total_duration:.1f}s)")
    return output_path, navigator_timing
