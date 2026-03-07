"""Extract full-body Zundamon mouth sprites from PSD standing illustration.

Reads the PSD file, toggles mouth layers, and exports 4 lip-sync states
as transparent PNGs to avatars/zundamon/.

Mouth mapping:
  mouth_0 (closed)      ← *むふ
  mouth_1 (small open)  ← *お
  mouth_2 (medium open) ← *ほー
  mouth_3 (wide open)   ← *ほぁー

Usage:
    python extract_zundamon_sprites.py [path_to_psd]
"""

import os
import sys

import psd_tools
from PIL import Image

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PSD = os.path.join(PROJECT_DIR, "ずんだもん立ち絵素材2.3.psd")
OUTPUT_DIR = os.path.join(PROJECT_DIR, "avatars", "zundamon")

# Mouth layer hex → mouth state index
# Layer names in the PSD are UTF-8 encoded; we match by hex prefix
MOUTH_LAYER_MAP = {
    "2ae38280e381b5":       0,  # *むふ (closed)
    "2ae3818a":             1,  # *お (small open)
    "2ae381bbe383bc":       2,  # *ほー (medium open)
    "2ae381bbe38182e383bc": 3,  # *ほぁー (wide open)
}


def _layer_hex(layer) -> str:
    return layer.name.encode("utf-8").hex()


def _find_group_by_hex(layers, target_hex: str):
    """Recursively find a layer/group by its name's UTF-8 hex prefix."""
    for layer in layers:
        if _layer_hex(layer).startswith(target_hex):
            return layer
        if hasattr(layer, "__iter__"):
            result = _find_group_by_hex(layer, target_hex)
            if result:
                return result
    return None


def _set_only_mouth(mouth_group, target_hex: str):
    """Make only the target mouth layer visible within the mouth group."""
    for child in mouth_group:
        child_hex = _layer_hex(child)
        child.visible = child_hex == target_hex


def extract_sprites(psd_path: str = DEFAULT_PSD, output_dir: str = OUTPUT_DIR):
    """Extract 4 mouth sprites from PSD."""
    print(f"Loading PSD: {psd_path}")
    psd = psd_tools.PSDImage.open(psd_path)
    print(f"  Canvas: {psd.width}x{psd.height}")

    # Find the mouth group (!口 = hex 21e58fa3)
    mouth_group = _find_group_by_hex(psd, "21e58fa3")
    if not mouth_group:
        print("ERROR: Could not find mouth group (!口) in PSD")
        sys.exit(1)

    print(f"  Mouth group found with {len(list(mouth_group))} layers")

    os.makedirs(output_dir, exist_ok=True)

    for target_hex, mouth_idx in MOUTH_LAYER_MAP.items():
        # Toggle mouth layer
        _set_only_mouth(mouth_group, target_hex)

        # Composite all visible layers (force=True for RGBA with transparency)
        img = psd.composite(force=True)

        # Crop to bounding box (remove transparent margins)
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)

        output_path = os.path.join(output_dir, f"mouth_{mouth_idx}.png")
        img.save(output_path)
        print(f"  mouth_{mouth_idx}.png: {img.size[0]}x{img.size[1]}px")

    print(f"\nSprites saved to {output_dir}")


if __name__ == "__main__":
    psd_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PSD
    extract_sprites(psd_path)
