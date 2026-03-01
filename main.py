"""News English Shorts - Main production pipeline.

Usage:
  python main.py <script.json>              Generate video from script
  python main.py --batch <dir>              Process all scripts in directory
  python main.py --voice female_us <script> Use a different voice

Full pipeline: script JSON → TTS audio → video with dual subtitles
"""

import argparse
import glob
import json
import os
import sys
import time

from tts_generator import generate_from_script, VOICES, ELEVENLABS_VOICES, DEFAULT_VOICE, DEFAULT_RATE
from video_generator import generate_video


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
AUDIO_DIR = os.path.join(PROJECT_DIR, "audio")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")


def process_script(script_path: str, voice: str = DEFAULT_VOICE,
                    rate: str = DEFAULT_RATE, use_sd: bool = True,
                    smart_bg: bool = False,
                    tts_engine: str = "edge") -> str:
    """Run full pipeline on a single script file."""
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    sid = script["id"]
    print(f"\n{'='*60}")
    print(f"Processing: {sid}")
    print(f"Topic: {script['topic']}")
    print(f"{'='*60}")

    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Step 1: Generate TTS audio (narration + insight + KP examples)
    engine_label = f"ElevenLabs" if tts_engine == "elevenlabs" else "edge-tts"
    print(f"\n[1/2] Generating TTS audio ({engine_label})...")
    t0 = time.time()
    audio_path, srt_path, timing_path, _, narr_sentence_count, kp_audio_path, kp_timing_path = generate_from_script(
        script_path, AUDIO_DIR, voice=voice, rate=rate, tts_engine=tts_engine
    )
    print(f"  Done in {time.time() - t0:.1f}s")

    # Step 2: Generate video
    print("\n[2/2] Generating video...")
    t0 = time.time()
    output_path = os.path.join(OUTPUT_DIR, f"{sid}.mp4")
    generate_video(
        script_path, audio_path, timing_path, output_path,
        use_sd=use_sd,
        smart_bg=smart_bg,
        narr_sentence_count=narr_sentence_count,
        kp_audio_path=kp_audio_path,
        kp_timing_path=kp_timing_path,
    )
    print(f"  Done in {time.time() - t0:.1f}s")

    print(f"\nOutput: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="News English Shorts - Video Production Pipeline"
    )
    parser.add_argument(
        "script", nargs="?",
        help="Path to script JSON file"
    )
    parser.add_argument(
        "--batch", metavar="DIR",
        help="Process all JSON scripts in directory"
    )
    parser.add_argument(
        "--voice", default=DEFAULT_VOICE,
        help=f"TTS voice (default: {DEFAULT_VOICE}). Options: {', '.join(VOICES.keys())}"
    )
    parser.add_argument(
        "--rate", default=DEFAULT_RATE,
        help=f"Speech rate (default: {DEFAULT_RATE})"
    )
    parser.add_argument(
        "--no-sd", action="store_true",
        help="Disable Stable Diffusion backgrounds (use gradient fallback)"
    )
    parser.add_argument(
        "--smart-bg", action="store_true",
        help="Use Claude AI to generate contextual SD background prompts"
    )
    parser.add_argument(
        "--tts", choices=["edge", "elevenlabs"], default="edge",
        help="TTS engine (default: edge)"
    )
    parser.add_argument(
        "--list-voices", action="store_true",
        help="List available TTS voices"
    )

    args = parser.parse_args()

    if args.list_voices:
        print("Available voices (edge-tts):")
        for name, voice_id in VOICES.items():
            print(f"  {name}: {voice_id}")
        print("\nAvailable voices (ElevenLabs):")
        for name, voice_id in ELEVENLABS_VOICES.items():
            print(f"  {name}: {voice_id}")
        return

    # Resolve voice name to voice ID
    voice = VOICES.get(args.voice, args.voice)

    use_sd = not args.no_sd
    smart_bg = args.smart_bg
    tts_engine = args.tts

    if args.batch:
        scripts = sorted(glob.glob(os.path.join(args.batch, "*.json")))
        if not scripts:
            print(f"No JSON files found in {args.batch}")
            sys.exit(1)

        print(f"Batch processing {len(scripts)} scripts...")
        if not use_sd:
            print("  (SD backgrounds disabled)")
        if smart_bg:
            print("  (Smart SD backgrounds: Claude AI)")
        if tts_engine == "elevenlabs":
            print("  (TTS: ElevenLabs)")
        outputs = []
        for script_path in scripts:
            try:
                output = process_script(script_path, voice=voice, rate=args.rate,
                                        use_sd=use_sd, smart_bg=smart_bg,
                                        tts_engine=tts_engine)
                outputs.append(output)
            except Exception as e:
                print(f"ERROR processing {script_path}: {e}")

        print(f"\n{'='*60}")
        print(f"Batch complete: {len(outputs)}/{len(scripts)} videos generated")
        for o in outputs:
            print(f"  {o}")

    elif args.script:
        if not os.path.exists(args.script):
            print(f"Script not found: {args.script}")
            sys.exit(1)
        process_script(args.script, voice=voice, rate=args.rate,
                       use_sd=use_sd, smart_bg=smart_bg,
                       tts_engine=tts_engine)

    else:
        parser.print_help()
        print(f"\nScript files in {SCRIPTS_DIR}:")
        for f in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.json"))):
            print(f"  {os.path.basename(f)}")


if __name__ == "__main__":
    main()
