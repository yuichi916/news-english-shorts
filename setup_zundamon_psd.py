"""Extract Zundamon mouth sprites from the official PSD standing image.

Setup:
  1. Download PSD from: https://seiga.nicovideo.jp/seiga/im11206626
     Download: https://ux.getuploader.com/s_ahiru/download/59  (pass: zunda)
  2. Place PSD in ~/news-english-shorts/
  3. Run: python setup_zundamon_psd.py

Outputs avatars/zundamon/mouth_0..3.png (300x300 RGBA).

Requires: pip install psd-tools
"""

import glob
import os
import sys

from PIL import Image

try:
    from psd_tools import PSDImage
except ImportError:
    print("ERROR: psd-tools not installed. Run: pip install psd-tools")
    sys.exit(1)

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROJECT_DIR, "avatars", "zundamon")
SPRITE_SIZE = 300

# Mouth layers: state → layer name (from V3.2 基本版)
MOUTH_STATES = {
    0: "むふ",      # closed
    1: "ほう",      # half open
    2: "ほあ",      # open
    3: "ほあー",    # wide open
}


def _decode_name(layer) -> str:
    """Get layer name, fixing Shift-JIS encoding if needed."""
    name = layer.name
    try:
        name = name.encode('latin-1').decode('shift-jis')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    return name.strip()


def find_psd_file() -> str | None:
    """Find a Zundamon PSD in the project directory."""
    for f in glob.glob(os.path.join(PROJECT_DIR, "*.psd")):
        return f
    return None


def _find_group(psd, group_name: str):
    """Find a layer group by decoded name."""
    for layer in psd:
        if _decode_name(layer) == group_name:
            return layer
    return None


def _find_layer_in_group(group, target_name: str):
    """Find a layer by decoded name within a group."""
    for layer in group:
        if _decode_name(layer) == f"*{target_name}":
            return layer
    return None


def extract(psd_path: str):
    """Extract mouth variant sprites from the PSD."""
    print(f"Loading: {psd_path}")
    psd = PSDImage.open(psd_path)
    print(f"  Size: {psd.width}x{psd.height}")

    # Find the mouth group
    mouth_group = _find_group(psd, "!口")
    if not mouth_group:
        print("ERROR: Could not find !口 group")
        # Print layer names for debugging
        for layer in psd:
            print(f"  group: {_decode_name(layer)}")
        return False

    print(f"  Mouth group: {len(list(mouth_group))} layers")

    os.makedirs(OUT_DIR, exist_ok=True)

    for state, mouth_name in MOUTH_STATES.items():
        # Hide all mouth layers, then show only the target
        target = None
        for ml in mouth_group:
            decoded = _decode_name(ml)
            if decoded == f"*{mouth_name}":
                target = ml
                ml.visible = True
            else:
                ml.visible = False

        if not target:
            print(f"  WARNING: mouth layer '{mouth_name}' not found, skipping state {state}")
            continue

        # Render full composite
        composite = psd.composite()

        # Crop: head + upper body (top ~42% of standing image)
        w, h = composite.size
        crop_bottom = int(h * 0.42)
        # Slight horizontal trim
        margin_x = int(w * 0.12)
        cropped = composite.crop((margin_x, 0, w - margin_x, crop_bottom))

        # Fit into SPRITE_SIZE square
        cw, ch = cropped.size
        ratio = min(SPRITE_SIZE / cw, SPRITE_SIZE / ch)
        new_w = int(cw * ratio)
        new_h = int(ch * ratio)
        resized = cropped.resize((new_w, new_h), Image.LANCZOS)

        final = Image.new("RGBA", (SPRITE_SIZE, SPRITE_SIZE), (0, 0, 0, 0))
        paste_x = (SPRITE_SIZE - new_w) // 2
        paste_y = (SPRITE_SIZE - new_h) // 2
        final.paste(resized, (paste_x, paste_y))

        path = os.path.join(OUT_DIR, f"mouth_{state}.png")
        final.save(path)
        print(f"  mouth_{state} ({mouth_name}): {path}")

    # Restore default visibility
    for ml in mouth_group:
        decoded = _decode_name(ml)
        ml.visible = (decoded == "*ほう")

    print(f"\nDone! Sprites: {OUT_DIR}")
    return True


if __name__ == "__main__":
    psd_path = sys.argv[1] if len(sys.argv) > 1 else find_psd_file()
    if not psd_path:
        print("No PSD found. Place ずんだもん立ち絵素材*.psd in the project directory.")
        sys.exit(1)
    extract(psd_path)
