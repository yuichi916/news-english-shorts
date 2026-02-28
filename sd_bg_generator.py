"""Stable Diffusion background generator - SD WebUI reForge API integration.

Generates contextual background images using SD WebUI API (localhost:7860).
Falls back gracefully when API is unavailable.

Features:
- Auto-generates prompts from script topic/theme
- 768x1344 generation → 1080x1920 resize
- Post-processing: darken + blur + vignette for text readability
- Caches by script ID to avoid regeneration
"""

import base64
import io
import json
import os
import urllib.request
import urllib.error

from PIL import Image, ImageDraw, ImageFilter

SD_API_URL = "http://localhost:7860"
GEN_WIDTH = 768
GEN_HEIGHT = 1344
FINAL_WIDTH = 1080
FINAL_HEIGHT = 1920

# Theme → SD prompt style mapping
THEME_PROMPTS = {
    "midnight": "dark purple and blue cosmic atmosphere, nebula, starfield, deep space",
    "ocean": "deep ocean underwater scene, bioluminescent, dark blue water, coral reef silhouette",
    "ember": "dark volcanic landscape, glowing lava, ember particles, red and orange atmosphere",
    "forest": "dark enchanted forest, misty trees, green bioluminescent plants, moonlight",
    "purple": "dark purple crystal cave, amethyst formations, purple light rays, mystical",
}

NEGATIVE_PROMPT = (
    "text, watermark, logo, words, letters, numbers, signature, "
    "person, face, human, hand, fingers, bright, overexposed, "
    "blurry, low quality, jpeg artifacts, cartoon, anime"
)


def _build_prompt(script: dict) -> str:
    """Build SD prompt from script topic and theme."""
    topic = script.get("topic", "")
    theme = script.get("theme", "midnight")
    base_style = THEME_PROMPTS.get(theme, THEME_PROMPTS["midnight"])

    # Create contextual prompt from topic keywords
    topic_keywords = topic.lower().replace("'", "").replace('"', "")

    prompt = (
        f"abstract background for news about {topic_keywords}, "
        f"{base_style}, "
        "cinematic lighting, moody atmosphere, bokeh, "
        "dark background suitable for text overlay, "
        "professional news broadcast feel, 8k quality, "
        "ultra detailed, no text, no people"
    )
    return prompt


def _post_process(img: Image.Image) -> Image.Image:
    """Post-process SD output for text readability: darken + blur + vignette."""
    # Resize to final dimensions
    img = img.resize((FINAL_WIDTH, FINAL_HEIGHT), Image.LANCZOS)

    # Darken to 65% brightness
    from PIL import ImageEnhance
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.65)

    # Light gaussian blur for softness
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    # Vignette effect
    vignette = Image.new("RGBA", (FINAL_WIDTH, FINAL_HEIGHT), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    cx, cy = FINAL_WIDTH // 2, FINAL_HEIGHT // 2
    max_dist = (cx ** 2 + cy ** 2) ** 0.5
    for ring in range(0, int(max_dist), 4):
        alpha = int(min(255, (ring / max_dist) ** 1.5 * 160))
        vdraw.ellipse(
            [cx - ring, cy - ring, cx + ring, cy + ring],
            outline=(0, 0, 0, alpha),
        )
    img_rgba = img.convert("RGBA")
    img = Image.alpha_composite(img_rgba, vignette).convert("RGB")

    return img


def _call_sd_api(prompt: str, negative_prompt: str = NEGATIVE_PROMPT) -> Image.Image:
    """Call SD WebUI txt2img API and return PIL Image."""
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": GEN_WIDTH,
        "height": GEN_HEIGHT,
        "steps": 20,
        "cfg_scale": 7,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "seed": -1,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{SD_API_URL}/sdapi/v1/txt2img",
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise ConnectionError(f"SD WebUI not available at {SD_API_URL}: {e}")
    except TimeoutError:
        raise ConnectionError(f"SD WebUI request timed out")

    if "images" not in result or not result["images"]:
        raise RuntimeError("SD API returned no images")

    img_data = base64.b64decode(result["images"][0])
    return Image.open(io.BytesIO(img_data))


def generate_sd_bg(script: dict, output_path: str) -> str:
    """Generate an SD background image for the given script."""
    prompt = _build_prompt(script)
    print(f"SD generating: {prompt[:80]}...")

    raw_img = _call_sd_api(prompt)
    processed = _post_process(raw_img)
    processed.save(output_path, quality=95)

    print(f"SD background saved: {output_path}")
    return output_path


def ensure_sd_bg(script: dict, bg_dir: str) -> str:
    """Ensure SD background exists for script, generate if needed. Returns path."""
    os.makedirs(bg_dir, exist_ok=True)
    script_id = script.get("id", "unknown")
    path = os.path.join(bg_dir, f"sd_{script_id}.jpg")

    if os.path.exists(path):
        print(f"SD background cached: {path}")
        return path

    return generate_sd_bg(script, path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sd_bg_generator.py <script.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        script = json.load(f)

    os.makedirs("backgrounds", exist_ok=True)
    generate_sd_bg(script, f"backgrounds/sd_{script['id']}.jpg")
