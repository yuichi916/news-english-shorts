"""Avatar lip-sync video generator.

Generates a transparent WebM video of a character avatar with lip-sync
animation driven by TTS audio amplitude.

Characters are stored in avatars/<character>/ with mouth_0..3.png sprites.
Sprites can be any size (including full-body). Dimensions are auto-detected.
If sprites are missing, Pillow placeholder images are auto-generated.
"""

import math
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
AVATARS_DIR = os.path.join(PROJECT_DIR, "avatars")

PLACEHOLDER_SIZE = 300  # fallback placeholder sprite size (px)
FPS = 30
SMOOTH_WINDOW = 3       # moving-average window for jitter removal
MOUTH_THRESHOLDS = [0.02, 0.15, 0.45]  # amplitude → mouth state boundaries

# ── Animation constants ──────────────────────────────────────────────────────
ANIM_PAD = 14                # extra canvas padding (px) per side for animation
ANIM_BREATHE_AMP = 3.5      # breathing vertical amplitude (px) — always on
ANIM_BREATHE_FREQ = 0.30    # breathing frequency (Hz) — slow, natural
ANIM_SWAY_AMP = 2.5         # idle horizontal sway amplitude (px) — always on
ANIM_SWAY_FREQ = 0.18       # idle sway frequency (Hz) — very slow drift
ANIM_SPEAK_AMP = 3.0        # speaking bounce amplitude (px) — added on top
ANIM_SPEAK_FREQ = 4.0       # speaking bounce frequency (Hz)
ANIM_SPEAK_SWAY = 1.5       # speaking horizontal movement (px)
ANIM_SPEAK_SWAY_FREQ = 2.5  # speaking sway frequency (Hz)


# ── Placeholder asset generation ─────────────────────────────────────────────

def ensure_avatar_assets(character: str = "zundamon") -> str:
    """Ensure mouth_0..3.png exist for *character*; generate placeholders if missing.

    Returns the character directory path.
    """
    char_dir = os.path.join(AVATARS_DIR, character)
    os.makedirs(char_dir, exist_ok=True)

    needed = [f"mouth_{i}.png" for i in range(4)]
    existing = [n for n in needed if os.path.exists(os.path.join(char_dir, n))]

    if len(existing) == 4:
        return char_dir

    # Generate placeholders: green circle face + 4 mouth stages
    mouth_heights = [0, 12, 28, 48]  # closed, small, medium, large

    for idx, h in enumerate(mouth_heights):
        path = os.path.join(char_dir, f"mouth_{idx}.png")
        if os.path.exists(path):
            continue

        img = Image.new("RGBA", (PLACEHOLDER_SIZE, PLACEHOLDER_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Face circle (zundamon-green)
        margin = 10
        draw.ellipse(
            [margin, margin, PLACEHOLDER_SIZE - margin, PLACEHOLDER_SIZE - margin],
            fill=(144, 238, 144, 230),
            outline=(60, 160, 60, 255),
            width=3,
        )

        # Eyes
        eye_y = PLACEHOLDER_SIZE // 3
        for ex in [PLACEHOLDER_SIZE // 3, PLACEHOLDER_SIZE * 2 // 3]:
            draw.ellipse([ex - 12, eye_y - 12, ex + 12, eye_y + 12], fill=(40, 40, 40, 255))
            draw.ellipse([ex - 5, eye_y - 8, ex + 3, eye_y], fill=(255, 255, 255, 200))

        # Mouth
        cx, cy = PLACEHOLDER_SIZE // 2, PLACEHOLDER_SIZE * 5 // 8
        if h == 0:
            # Closed: horizontal line
            draw.line([(cx - 18, cy), (cx + 18, cy)], fill=(80, 40, 40, 255), width=3)
        else:
            # Open: ellipse
            draw.ellipse(
                [cx - 20, cy - h // 2, cx + 20, cy + h // 2],
                fill=(180, 60, 60, 255),
                outline=(80, 40, 40, 255),
                width=2,
            )

        img.save(path)

    print(f"Avatar placeholders generated: {char_dir}")
    return char_dir


# ── Audio amplitude analysis ─────────────────────────────────────────────────

def _audio_rms_per_frame(audio_path: str, fps: int = FPS) -> list[float]:
    """Return per-frame RMS amplitude (0..1 normalised) from an audio file."""
    from pydub import AudioSegment

    seg = AudioSegment.from_file(audio_path)
    mono = seg.set_channels(1)
    samples = mono.get_array_of_samples()
    sample_rate = mono.frame_rate

    samples_per_frame = sample_rate / fps
    total_frames = int(math.ceil(len(samples) / samples_per_frame))

    rms_values: list[float] = []
    for i in range(total_frames):
        start = int(i * samples_per_frame)
        end = min(int((i + 1) * samples_per_frame), len(samples))
        chunk = samples[start:end]
        if len(chunk) == 0:
            rms_values.append(0.0)
            continue
        mean_sq = sum(s * s for s in chunk) / len(chunk)
        rms = math.sqrt(mean_sq)
        rms_values.append(rms)

    # Normalise to 0..1
    peak = max(rms_values) if rms_values else 1.0
    if peak > 0:
        rms_values = [v / peak for v in rms_values]

    return rms_values


def build_speech_amplitude_timeline(
    total_duration: float,
    narr_audio: str,
    narr_offset: float,
    insight_audio: str | None = None,
    insight_offset: float | None = None,
    insight_audio_start: float | None = None,
    kp_audio: str | None = None,
    kp_offset: float | None = None,
    narr_sentence_count: int | None = None,
    navigator_audio: str | None = None,
) -> list[float]:
    """Build a per-frame amplitude timeline covering the full video duration.

    Only uses navigator audio for lip-sync (Zundamon speaks only for
    navigator lines, not during English narration/insight/KP).
    """
    total_frames = int(math.ceil(total_duration * FPS))
    timeline = [0.0] * total_frames

    # Only navigator audio drives Zundamon lip-sync
    if navigator_audio and os.path.exists(navigator_audio):
        nav_rms = _audio_rms_per_frame(navigator_audio)
        for j, val in enumerate(nav_rms):
            if 0 <= j < total_frames:
                timeline[j] = max(timeline[j], val)

    return timeline


# ── Smoothing & quantisation ─────────────────────────────────────────────────

def smooth_amplitudes(amplitudes: list[float], window: int = SMOOTH_WINDOW) -> list[float]:
    """Moving-average smoothing to reduce jitter."""
    if window < 2:
        return amplitudes
    out: list[float] = []
    half = window // 2
    n = len(amplitudes)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out.append(sum(amplitudes[lo:hi]) / (hi - lo))
    return out


def amplitude_to_mouth_states(amplitudes: list[float]) -> list[int]:
    """Map normalised amplitudes to 4-level mouth state (0-3)."""
    states: list[int] = []
    for a in amplitudes:
        if a < MOUTH_THRESHOLDS[0]:
            states.append(0)
        elif a < MOUTH_THRESHOLDS[1]:
            states.append(1)
        elif a < MOUTH_THRESHOLDS[2]:
            states.append(2)
        else:
            states.append(3)
    return states


# ── Video generation ─────────────────────────────────────────────────────────

def generate_avatar_video(
    total_duration: float,
    narr_audio: str,
    narr_offset: float,
    output_path: str,
    character: str = "zundamon",
    insight_audio: str | None = None,
    insight_offset: float | None = None,
    insight_audio_start: float | None = None,
    kp_audio: str | None = None,
    kp_offset: float | None = None,
    narr_sentence_count: int | None = None,
    navigator_audio: str | None = None,
) -> tuple[str, int, int]:
    """Generate a transparent WebM avatar video with lip-sync animation.

    Returns (output_path, canvas_width, canvas_height).
    """
    from video_generator import AVATAR_TARGET_WIDTH

    char_dir = ensure_avatar_assets(character)

    # Load sprites (auto-detect dimensions) and pre-scale to overlay size
    sprites: list[Image.Image] = []
    for i in range(4):
        img = Image.open(os.path.join(char_dir, f"mouth_{i}.png")).convert("RGBA")
        sprites.append(img)

    orig_w, orig_h = sprites[0].size
    # Pre-scale to target overlay width to avoid encoding huge frames
    if orig_w > AVATAR_TARGET_WIDTH:
        scale = AVATAR_TARGET_WIDTH / orig_w
        new_w = AVATAR_TARGET_WIDTH
        new_h = int(orig_h * scale)
        sprites = [s.resize((new_w, new_h), Image.LANCZOS) for s in sprites]
        print(f"  Avatar sprites: {orig_w}x{orig_h}px -> pre-scaled to {new_w}x{new_h}px")
    else:
        print(f"  Avatar sprites: {orig_w}x{orig_h}px")

    sprite_w, sprite_h = sprites[0].size
    canvas_w = sprite_w + ANIM_PAD * 2
    canvas_h = sprite_h + ANIM_PAD * 2
    print(f"  Canvas: {canvas_w}x{canvas_h}px")

    # Build amplitude timeline
    timeline = build_speech_amplitude_timeline(
        total_duration=total_duration,
        narr_audio=narr_audio,
        narr_offset=narr_offset,
        insight_audio=insight_audio,
        insight_offset=insight_offset,
        insight_audio_start=insight_audio_start,
        kp_audio=kp_audio,
        kp_offset=kp_offset,
        narr_sentence_count=narr_sentence_count,
        navigator_audio=navigator_audio,
    )

    smoothed = smooth_amplitudes(timeline)
    mouth_states = amplitude_to_mouth_states(smoothed)

    # Write animated frames to temp directory
    tmp_dir = tempfile.mkdtemp(prefix="avatar_frames_")
    try:
        total_frames = len(mouth_states)
        for idx, state in enumerate(mouth_states):
            t = idx / FPS
            sprite = sprites[state]

            # Always-on idle animation: breathing + gentle sway
            breathe_y = ANIM_BREATHE_AMP * math.sin(2 * math.pi * ANIM_BREATHE_FREQ * t)
            sway_x = ANIM_SWAY_AMP * math.sin(2 * math.pi * ANIM_SWAY_FREQ * t)

            if state > 0:
                # Speaking: add bounce + extra horizontal energy
                speak_y = ANIM_SPEAK_AMP * math.sin(2 * math.pi * ANIM_SPEAK_FREQ * t)
                speak_x = ANIM_SPEAK_SWAY * math.sin(2 * math.pi * ANIM_SPEAK_SWAY_FREQ * t)
                y_offset = int(breathe_y + speak_y)
                x_offset = int(sway_x + speak_x)
            else:
                # Idle: gentle breathing + slow drift
                y_offset = int(breathe_y)
                x_offset = int(sway_x)

            canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            canvas.paste(sprite, (ANIM_PAD + x_offset, ANIM_PAD + y_offset), sprite)

            frame_path = os.path.join(tmp_dir, f"frame_{idx:06d}.png")
            canvas.save(frame_path)

        # Encode to VP9 WebM with alpha
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", os.path.join(tmp_dir, "frame_%06d.png"),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-auto-alt-ref", "0",
            "-b:v", "500k",
            "-t", f"{total_duration:.2f}",
            output_path,
        ]

        print(f"Encoding avatar video ({total_frames} frames, {total_duration:.1f}s)...")
        result = subprocess.run(cmd, capture_output=True, timeout=600,
                                encoding="utf-8", errors="replace")

        if result.returncode != 0:
            stderr = result.stderr or ""
            print(f"Avatar FFmpeg error:\n{stderr[-2000:]}")
            raise RuntimeError("Avatar video encoding failed")

        print(f"Avatar video saved: {output_path}")
        return output_path, canvas_w, canvas_h

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
