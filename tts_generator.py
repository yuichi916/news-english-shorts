"""TTS audio generation module using edge-tts.

Generates English narration audio with sentence-level timestamps
for subtitle synchronization. v8: insight narration + KP example audio.
"""

import asyncio
import json
import os
import edge_tts

VOICES = {
    "male_us": "en-US-GuyNeural",
    "female_us": "en-US-JennyNeural",
    "male_uk": "en-GB-RyanNeural",
    "female_uk": "en-GB-SoniaNeural",
}

DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_RATE = "-10%"


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


async def _generate_all(
    narr_text, narr_audio, narr_srt, narr_timing,
    kp_text, kp_audio, kp_timing,
    voice, rate,
):
    """Generate narration audio and KP example audio in one async context."""
    boundaries = await generate_audio(
        narr_text, narr_audio, narr_srt, narr_timing, voice=voice, rate=rate
    )
    kp_boundaries = []
    if kp_text and kp_audio:
        kp_boundaries = await generate_audio(
            kp_text, kp_audio, None, kp_timing, voice=voice, rate=rate
        )
    return boundaries, kp_boundaries


def generate_from_script(script_path: str, output_dir: str, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE):
    """Generate TTS from a script JSON file.

    Returns: (audio_path, srt_path, timing_path, boundaries,
              narr_sentence_count, kp_audio_path, kp_timing_path)
    """
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    script_id = script["id"]
    os.makedirs(output_dir, exist_ok=True)

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

    # Generate both audio files
    boundaries, kp_boundaries = asyncio.run(_generate_all(
        full_text, audio_path, srt_path, timing_path,
        kp_text, kp_audio_path, kp_timing_path,
        voice, rate,
    ))

    # Fallback: if narration_structure missing, use total boundaries minus insight
    if narr_sentence_count == 0:
        narr_sentence_count = len(boundaries) - (1 if insight_en else 0)

    print(f"  Narration: {narr_sentence_count} sentences, Insight: {len(boundaries) - narr_sentence_count}")
    if kp_boundaries:
        print(f"  KP examples: {len(kp_boundaries)} phrases, {kp_boundaries[-1]['end_s']:.1f}s")

    return audio_path, srt_path, timing_path, boundaries, narr_sentence_count, kp_audio_path, kp_timing_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tts_generator.py <script.json> [voice] [rate]")
        print(f"\nAvailable voices: {json.dumps(VOICES, indent=2)}")
        sys.exit(1)

    script_file = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_VOICE
    rate = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_RATE

    output = os.path.join(os.path.dirname(os.path.abspath(script_file)), "..", "audio")
    generate_from_script(script_file, output, voice=voice, rate=rate)
