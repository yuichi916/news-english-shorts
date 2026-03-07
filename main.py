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
from video_generator import generate_video, compute_phase_timing, NARRATION_OFFSET
from avatar_generator import generate_avatar_video
from navigator_generator import generate_navigator_clips, combine_navigator_audio


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
AUDIO_DIR = os.path.join(PROJECT_DIR, "audio")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")


def process_script(script_path: str, voice: str = DEFAULT_VOICE,
                    rate: str = DEFAULT_RATE, use_sd: bool = True,
                    smart_bg: bool = False,
                    tts_engine: str = "edge",
                    avatar_enabled: bool = True,
                    avatar_character: str = "zundamon") -> str:
    """Run full pipeline on a single script file."""
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)

    sid = script["id"]
    is_long_form = script.get("format") == "long_form"

    # Long-form videos don't use avatar/navigator (no hook/KP/answer phases)
    if is_long_form:
        avatar_enabled = False

    print(f"\n{'='*60}")
    print(f"Processing: {sid} {'[LONG-FORM]' if is_long_form else ''}")
    print(f"Topic: {script['topic']}")
    print(f"{'='*60}")

    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    step = 0
    total_steps = 1 + (1 if avatar_enabled else 0) + 1  # TTS + (avatar) + video
    if avatar_enabled:
        total_steps += 1  # navigator

    # Step 1: Generate TTS audio (narration + insight + KP examples)
    step += 1
    engine_label = f"ElevenLabs" if tts_engine == "elevenlabs" else "edge-tts"
    print(f"\n[{step}/{total_steps}] Generating TTS audio ({engine_label})...")
    t0 = time.time()
    audio_path, srt_path, timing_path, _, narr_sentence_count, kp_audio_path, kp_timing_path = generate_from_script(
        script_path, AUDIO_DIR, voice=voice, rate=rate, tts_engine=tts_engine
    )
    print(f"  Done in {time.time() - t0:.1f}s")

    # Compute phase timing (needed for avatar + navigator)
    avatar_video_path = None
    navigator_audio_path = None
    narration_offset = None    # dynamic, set from navigator clip durations
    navigator_timing = None    # speech intervals for audio ducking
    avatar_size = None         # (width, height) for overlay scaling

    if avatar_enabled:
        with open(timing_path, "r", encoding="utf-8") as f:
            timing_data = json.load(f)

        # Step 2: Generate navigator TTS clips + compute narration offset
        step += 1
        print(f"\n[{step}/{total_steps}] Generating navigator audio ({avatar_character})...")
        t0 = time.time()
        nav_clips, narration_offset, nav_durations = generate_navigator_clips(
            script, AUDIO_DIR, script_id=sid,
        )

        # Compute phase timing with dynamic narration offset + nav durations
        pt = compute_phase_timing(timing_data, narr_sentence_count, kp_timing_path,
                                  narration_offset=narration_offset,
                                  nav_durations=nav_durations)

        # Combine clips into single timed track (returns timing for ducking)
        navigator_audio_path, navigator_timing = combine_navigator_audio(
            nav_clips, pt, AUDIO_DIR, script_id=sid,
        )
        print(f"  Done in {time.time() - t0:.1f}s")

        # Step 3: Generate avatar lip-sync video
        step += 1
        print(f"\n[{step}/{total_steps}] Generating avatar video ({avatar_character})...")
        t0 = time.time()
        avatar_video_path = os.path.join(AUDIO_DIR, f"{sid}_avatar.webm")
        avatar_video_path, av_w, av_h = generate_avatar_video(
            total_duration=pt["total_duration"],
            narr_audio=audio_path,
            narr_offset=narration_offset,
            output_path=avatar_video_path,
            character=avatar_character,
            insight_audio=audio_path if pt["insight_audio_start"] is not None else None,
            insight_offset=pt["insight_offset"] if pt["insight_audio_start"] is not None else None,
            insight_audio_start=pt["insight_audio_start"],
            kp_audio=kp_audio_path,
            kp_offset=pt["kp_phase_start"] if kp_audio_path else None,
            narr_sentence_count=narr_sentence_count,
            navigator_audio=navigator_audio_path,
        )
        avatar_size = (av_w, av_h)
        print(f"  Done in {time.time() - t0:.1f}s")

    # Final step: Generate video
    step += 1
    print(f"\n[{step}/{total_steps}] Generating video...")
    t0 = time.time()
    output_path = os.path.join(OUTPUT_DIR, f"{sid}.mp4")
    generate_video(
        script_path, audio_path, timing_path, output_path,
        use_sd=use_sd,
        smart_bg=smart_bg,
        narr_sentence_count=narr_sentence_count,
        kp_audio_path=kp_audio_path,
        kp_timing_path=kp_timing_path,
        avatar_video_path=avatar_video_path,
        navigator_audio_path=navigator_audio_path,
        narration_offset=narration_offset,
        navigator_timing=navigator_timing,
        avatar_size=avatar_size,
        nav_durations=nav_durations if avatar_enabled else None,
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
        help=f"Speech rate (default: {DEFAULT_RATE})".replace("%", "%%")
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
    parser.add_argument(
        "--no-avatar", action="store_true",
        help="Disable avatar overlay"
    )
    parser.add_argument(
        "--avatar-character", default="zundamon",
        help="Avatar character name (default: zundamon)"
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
    avatar_enabled = not args.no_avatar
    avatar_character = args.avatar_character

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
                                        tts_engine=tts_engine,
                                        avatar_enabled=avatar_enabled,
                                        avatar_character=avatar_character)
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
                       tts_engine=tts_engine,
                       avatar_enabled=avatar_enabled,
                       avatar_character=avatar_character)

    else:
        parser.print_help()
        print(f"\nScript files in {SCRIPTS_DIR}:")
        for f in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.json"))):
            print(f"  {os.path.basename(f)}")


if __name__ == "__main__":
    main()
