"""TTS audio generation module using edge-tts or ElevenLabs.

Generates English narration audio with sentence-level timestamps
for subtitle synchronization. v8: insight narration + KP example audio.
v9: ElevenLabs API support (--tts elevenlabs).
"""

import asyncio
import base64
import json
import os
import edge_tts

VOICES = {
    "male_us": "en-US-GuyNeural",
    "female_us": "en-US-JennyNeural",
    "male_uk": "en-GB-RyanNeural",
    "female_uk": "en-GB-SoniaNeural",
}

ELEVENLABS_VOICES = {
    "el_brian":   "nPczCjzI2devNBz1zQrb",  # Male, clear narrator
    "el_daniel":  "onwK4e9ZLuTAKqWW03F9",  # Male, British
    "el_adam":    "pNInz6obpgDQGcFmaJgB",  # Male, deep
    "el_rachel":  "21m00Tcm4TlvDq8ikWAM",  # Female, classic
    "el_sarah":   "EXAVITQu4vr4xnSDxMaL",  # Female, professional
}

DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_RATE = "-10%"
DEFAULT_ELEVENLABS_VOICE = "el_brian"
DEFAULT_ELEVENLABS_MODEL = "eleven_flash_v2_5"


async def generate_audio(
    text: str,
    output_audio_path: str,
    output_srt_path: str | None,
    output_timing_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
):
    """Generate TTS audio and subtitle timing data.

    output_srt_path can be None to skip SRT generation.
    """
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    sub_maker = edge_tts.SubMaker()
    sentence_boundaries = []

    with open(output_audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            else:
                sub_maker.feed(chunk)
                if chunk["type"] == "SentenceBoundary":
                    offset_ms = chunk["offset"] / 10000
                    duration_ms = chunk["duration"] / 10000
                    sentence_boundaries.append({
                        "text": chunk["text"],
                        "start_ms": offset_ms,
                        "end_ms": offset_ms + duration_ms,
                        "start_s": round(offset_ms / 1000, 2),
                        "end_s": round((offset_ms + duration_ms) / 1000, 2),
                    })

    # Save SRT (optional)
    if output_srt_path:
        srt_content = sub_maker.get_srt()
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

    # Save timing data for video pipeline
    with open(output_timing_path, "w", encoding="utf-8") as f:
        json.dump(sentence_boundaries, f, ensure_ascii=False, indent=2)

    print(f"Audio: {output_audio_path}")
    if output_srt_path:
        print(f"SRT:   {output_srt_path}")
    print(f"Timing: {output_timing_path} ({len(sentence_boundaries)} sentences)")
    return sentence_boundaries


async def generate_audio_elevenlabs(
    text: str,
    output_audio_path: str,
    output_srt_path: str | None,
    output_timing_path: str,
    voice_id: str = ELEVENLABS_VOICES[DEFAULT_ELEVENLABS_VOICE],
    model_id: str = DEFAULT_ELEVENLABS_MODEL,
):
    """Generate TTS audio via ElevenLabs API with sentence-level timing.

    Uses convert_with_timestamps() to get character-level alignment,
    then derives sentence boundaries from period positions.
    """
    from elevenlabs import ElevenLabs

    client = ElevenLabs()

    response = client.text_to_speech.convert_with_timestamps(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format="mp3_44100_128",
    )

    # Collect audio chunks and alignment data
    audio_chunks = []
    all_chars = []
    all_char_starts = []
    all_char_ends = []

    for item in response:
        if item.audio_base64:
            audio_chunks.append(base64.b64decode(item.audio_base64))
        if item.alignment:
            all_chars.extend(item.alignment.characters)
            all_char_starts.extend(item.alignment.character_start_times_seconds)
            all_char_ends.extend(item.alignment.character_end_times_seconds)

    # Save MP3
    with open(output_audio_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    # Build sentence boundaries from character-level alignment
    # Detect sentence ends: period followed by space (or end of text)
    sentence_boundaries = []
    sent_start_idx = 0

    for i, ch in enumerate(all_chars):
        is_period = ch == "."
        if not is_period:
            continue
        # Check if this period ends a sentence (followed by space or end)
        next_idx = i + 1
        at_end = next_idx >= len(all_chars)
        followed_by_space = (not at_end) and all_chars[next_idx] == " "
        if not (at_end or followed_by_space):
            continue

        # Extract sentence text
        sent_text = "".join(all_chars[sent_start_idx:i + 1]).strip()
        if not sent_text:
            # Skip to next char after the space
            sent_start_idx = next_idx + 1 if followed_by_space else next_idx
            continue

        start_s = all_char_starts[sent_start_idx]
        end_s = all_char_ends[i]
        sentence_boundaries.append({
            "text": sent_text,
            "start_ms": round(start_s * 1000),
            "end_ms": round(end_s * 1000),
            "start_s": round(start_s, 2),
            "end_s": round(end_s, 2),
        })
        # Next sentence starts after the space
        sent_start_idx = next_idx + 1 if followed_by_space else next_idx

    # Handle any remaining text after the last period
    if sent_start_idx < len(all_chars):
        remaining = "".join(all_chars[sent_start_idx:]).strip()
        if remaining:
            start_s = all_char_starts[sent_start_idx]
            end_s = all_char_ends[-1]
            sentence_boundaries.append({
                "text": remaining,
                "start_ms": round(start_s * 1000),
                "end_ms": round(end_s * 1000),
                "start_s": round(start_s, 2),
                "end_s": round(end_s, 2),
            })

    # Save SRT (optional)
    if output_srt_path:
        srt_lines = []
        for idx, seg in enumerate(sentence_boundaries, 1):
            start = _ms_to_srt_time(seg["start_ms"])
            end = _ms_to_srt_time(seg["end_ms"])
            srt_lines.append(f"{idx}\n{start} --> {end}\n{seg['text']}\n")
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

    # Save timing data
    with open(output_timing_path, "w", encoding="utf-8") as f:
        json.dump(sentence_boundaries, f, ensure_ascii=False, indent=2)

    print(f"Audio: {output_audio_path}")
    if output_srt_path:
        print(f"SRT:   {output_srt_path}")
    print(f"Timing: {output_timing_path} ({len(sentence_boundaries)} sentences)")
    return sentence_boundaries


def _ms_to_srt_time(ms: int) -> str:
    """Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    remainder = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{remainder:03d}"


def _show_elevenlabs_quota():
    """Print ElevenLabs character usage quota."""
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs()
        subscription = client.user.get_subscription()
        used = subscription.character_count
        limit = subscription.character_limit
        remaining = limit - used
        print(f"\nElevenLabs: {used:,} / {limit:,} characters used ({remaining:,} remaining)")
    except Exception as e:
        print(f"\nElevenLabs quota check failed: {e}")


async def _generate_all(
    narr_text, narr_audio, narr_srt, narr_timing,
    kp_text, kp_audio, kp_timing,
    voice, rate,
    tts_engine="edge",
    elevenlabs_voice_id=None,
    elevenlabs_model_id=DEFAULT_ELEVENLABS_MODEL,
):
    """Generate narration audio and KP example audio in one async context."""
    if tts_engine == "elevenlabs":
        voice_id = elevenlabs_voice_id or ELEVENLABS_VOICES[DEFAULT_ELEVENLABS_VOICE]
        boundaries = await generate_audio_elevenlabs(
            narr_text, narr_audio, narr_srt, narr_timing,
            voice_id=voice_id, model_id=elevenlabs_model_id,
        )
        kp_boundaries = []
        if kp_text and kp_audio:
            kp_boundaries = await generate_audio_elevenlabs(
                kp_text, kp_audio, None, kp_timing,
                voice_id=voice_id, model_id=elevenlabs_model_id,
            )
    else:
        boundaries = await generate_audio(
            narr_text, narr_audio, narr_srt, narr_timing, voice=voice, rate=rate
        )
        kp_boundaries = []
        if kp_text and kp_audio:
            kp_boundaries = await generate_audio(
                kp_text, kp_audio, None, kp_timing, voice=voice, rate=rate
            )
    return boundaries, kp_boundaries


def generate_from_script(script_path: str, output_dir: str, voice: str = DEFAULT_VOICE,
                         rate: str = DEFAULT_RATE, tts_engine: str = "edge"):
    """Generate TTS from a script JSON file.

    Args:
        tts_engine: "edge" (default) or "elevenlabs"

    Returns: (audio_path, srt_path, timing_path, boundaries,
              narr_sentence_count, kp_audio_path, kp_timing_path)
    """
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    script_id = script["id"]
    os.makedirs(output_dir, exist_ok=True)

    # Resolve ElevenLabs voice ID if needed
    elevenlabs_voice_id = None
    if tts_engine == "elevenlabs":
        if voice in ELEVENLABS_VOICES:
            elevenlabs_voice_id = ELEVENLABS_VOICES[voice]
        elif voice in ELEVENLABS_VOICES.values():
            elevenlabs_voice_id = voice  # Already a voice ID
        else:
            elevenlabs_voice_id = ELEVENLABS_VOICES[DEFAULT_ELEVENLABS_VOICE]
            print(f"  Voice '{voice}' not in ElevenLabs voices, using {DEFAULT_ELEVENLABS_VOICE}")

    # Build narration text (narration + optional insight)
    narr_text = script["narration"]["text"]
    insight_en = script.get("insight", {}).get("en", "")
    if insight_en:
        full_text = narr_text + " " + insight_en
    else:
        full_text = narr_text

    # Count narration-only sentences from narration_structure
    narr_sentence_count = len(script.get("narration_structure", []))

    audio_path = os.path.join(output_dir, f"{script_id}.mp3")
    srt_path = os.path.join(output_dir, f"{script_id}.srt")
    timing_path = os.path.join(output_dir, f"{script_id}_timing.json")

    # Build KP example text
    examples = [kp.get("example", "") for kp in script.get("key_phrases", []) if kp.get("example")]
    kp_text = " ".join(examples) if examples else ""
    kp_audio_path = os.path.join(output_dir, f"{script_id}_kp.mp3") if kp_text else None
    kp_timing_path = os.path.join(output_dir, f"{script_id}_kp_timing.json") if kp_text else None

    if tts_engine == "elevenlabs":
        print(f"  Engine: ElevenLabs (model: {DEFAULT_ELEVENLABS_MODEL})")

    # Generate both audio files
    boundaries, kp_boundaries = asyncio.run(_generate_all(
        full_text, audio_path, srt_path, timing_path,
        kp_text, kp_audio_path, kp_timing_path,
        voice, rate,
        tts_engine=tts_engine,
        elevenlabs_voice_id=elevenlabs_voice_id,
    ))

    # Fallback: if narration_structure missing, use total boundaries minus insight
    if narr_sentence_count == 0:
        narr_sentence_count = len(boundaries) - (1 if insight_en else 0)

    print(f"  Narration: {narr_sentence_count} sentences, Insight: {len(boundaries) - narr_sentence_count}")
    if kp_boundaries:
        print(f"  KP examples: {len(kp_boundaries)} phrases, {kp_boundaries[-1]['end_s']:.1f}s")

    if tts_engine == "elevenlabs":
        _show_elevenlabs_quota()

    return audio_path, srt_path, timing_path, boundaries, narr_sentence_count, kp_audio_path, kp_timing_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tts_generator.py <script.json> [voice] [rate] [--tts elevenlabs]")
        print(f"\nEdge-TTS voices: {json.dumps(VOICES, indent=2)}")
        print(f"ElevenLabs voices: {json.dumps(ELEVENLABS_VOICES, indent=2)}")
        sys.exit(1)

    script_file = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VOICE
    rate = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_RATE

    tts_engine = "edge"
    if "--tts" in sys.argv:
        tts_idx = sys.argv.index("--tts")
        if tts_idx + 1 < len(sys.argv):
            tts_engine = sys.argv[tts_idx + 1]

    output = os.path.join(os.path.dirname(os.path.abspath(script_file)), "..", "audio")
    generate_from_script(script_file, output, voice=voice, rate=rate, tts_engine=tts_engine)
