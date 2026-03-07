"""Stable Diffusion background generator - SD WebUI reForge API integration.

Generates contextual background images using SD WebUI API (localhost:7860).
Falls back gracefully when API is unavailable.

Features:
- Auto-generates prompts from script topic/theme
- 832x1472 SDXL generation → 1080x1920 resize
- Post-processing: darken + blur + vignette for text readability
- Caches by script ID to avoid regeneration
"""

import base64
import io
import json
import os
import urllib.request
import urllib.error

import anthropic
from PIL import Image, ImageDraw, ImageFilter

SD_API_URL = "http://localhost:7860"
GEN_WIDTH = 832
GEN_HEIGHT = 1472
FINAL_WIDTH = 1080
FINAL_HEIGHT = 1920

# Theme → SD prompt style mapping (anime/illustration style)
THEME_PROMPTS = {
    "midnight": "deep indigo and navy night sky, city skyline silhouette, neon accent lights, anime background art",
    "ocean": "calm ocean horizon at twilight, soft blue gradient sky, distant clouds, anime scenery",
    "ember": "warm sunset cityscape, orange and amber glow, soft light rays, anime background art",
    "forest": "lush green hillside, soft sunlight through trees, gentle breeze, anime nature scenery",
    "purple": "evening twilight sky, purple and pink gradient, city lights below, anime background art",
}

NEGATIVE_PROMPT = (
    "text, watermark, logo, words, letters, numbers, signature, "
    "person, face, human, hand, fingers, "
    "blurry, low quality, worst quality, jpeg artifacts, "
    "3d render, photorealistic, photo, realistic"
)

SMART_PROMPT_MODEL = "claude-haiku-4-5-20251001"

SMART_PROMPT_SYSTEM = """\
You are an SDXL prompt engineer creating anime-style background illustrations for a \
Japanese English-learning YouTube Shorts channel featuring ずんだもん (Zundamon). \
The backgrounds should look like anime scenery art — soft, colorful, and appealing. \
They should subtly relate to the news topic through setting/mood, not literal depiction. \
Output ONLY the prompt text, nothing else."""

SMART_PROMPT_TEMPLATE = """\
Generate an SDXL prompt for an anime-style background that evokes this news topic's mood.

NEWS TOPIC: {topic}
KEY TERMS: {highlights}

COLOR MOOD: {theme_style}

CRITICAL RULES:
1. Create a SCENIC ANIME BACKGROUND (no characters) that evokes the topic's mood or setting.
   - Technology → futuristic city, glowing screens, modern office, server room corridor
   - Economy/finance → city business district, stock exchange building, shopping street
   - Climate → dramatic sky, weather scene, nature landscape
   - Politics → government building, cityscape, formal interior
   - War/conflict → stormy sky, ruined cityscape, dramatic clouds
2. Use ANIME ILLUSTRATION style: soft lighting, clean lines, vibrant but not oversaturated colors.
3. The scene should be slightly dim/evening-toned for text readability (not pure dark).
4. Use {theme_style} as the color palette guide.
5. Include depth with foreground blur or atmospheric perspective.
6. End with: anime background, illustration, masterpiece, best quality, no text, no people, no characters
7. Under 80 words, single paragraph."""


def _load_cached_prompt(cache_path: str) -> str | None:
    """Load cached smart prompt if available."""
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def _save_prompt_cache(cache_path: str, prompt: str) -> None:
    """Save generated prompt to cache file."""
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(prompt)


def _build_smart_prompt(script: dict) -> str:
    """Generate a contextual SD prompt using Claude Haiku."""
    topic = script.get("topic", "")
    theme = script.get("theme", "midnight")
    narration_text = script.get("narration", {}).get("text", "")
    insight_en = script.get("insight", {}).get("en", "")
    highlights = script.get("narration", {}).get("highlights", [])[:6]
    theme_style = THEME_PROMPTS.get(theme, THEME_PROMPTS["midnight"])

    user_prompt = SMART_PROMPT_TEMPLATE.format(
        topic=topic,
        narration_text=narration_text,
        insight_en=insight_en,
        highlights=", ".join(highlights),
        theme_style=theme_style,
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=SMART_PROMPT_MODEL,
        max_tokens=300,
        system=SMART_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text.strip()


def _build_prompt(script: dict) -> str:
    """Build SD prompt from script topic and theme."""
    topic = script.get("topic", "")
    theme = script.get("theme", "midnight")
    base_style = THEME_PROMPTS.get(theme, THEME_PROMPTS["midnight"])

    # Create contextual prompt from topic keywords
    topic_keywords = topic.lower().replace("'", "").replace('"', "")

    prompt = (
        f"An anime-style scenic background evoking {topic_keywords}, "
        f"{base_style}, "
        "soft evening lighting, atmospheric perspective, depth of field, "
        "anime background, illustration, masterpiece, best quality, "
        "no text, no people, no characters, no faces"
    )
    return prompt


def _post_process(img: Image.Image) -> Image.Image:
    """Post-process SD output for text readability: moderate darken + soft blur + vignette."""
    # Resize to final dimensions
    img = img.resize((FINAL_WIDTH, FINAL_HEIGHT), Image.LANCZOS)

    # Moderate darken (75% brightness — lighter than before to keep anime style)
    from PIL import ImageEnhance
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(0.75)

    # Slight blur for softness (less than before)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))

    # Soft vignette effect (lighter than before)
    vignette = Image.new("RGBA", (FINAL_WIDTH, FINAL_HEIGHT), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    cx, cy = FINAL_WIDTH // 2, FINAL_HEIGHT // 2
    max_dist = (cx ** 2 + cy ** 2) ** 0.5
    for ring in range(0, int(max_dist), 4):
        alpha = int(min(255, (ring / max_dist) ** 1.8 * 120))
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
        "steps": 30,
        "cfg_scale": 7,
        "sampler_name": "DPM++ 2M SDE",
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


def generate_sd_bg(script: dict, output_path: str, smart_bg: bool = False) -> str:
    """Generate an SD background image for the given script."""
    script_id = script.get("id", "unknown")
    bg_dir = os.path.dirname(output_path)
    cache_path = os.path.join(bg_dir, f"sd_{script_id}.prompt.txt")

    prompt = None
    if smart_bg:
        # Try cached smart prompt first
        cached = _load_cached_prompt(cache_path)
        if cached:
            prompt = cached
            print(f"Smart prompt loaded from cache: {cache_path}")
        else:
            try:
                prompt = _build_smart_prompt(script)
                _save_prompt_cache(cache_path, prompt)
                print(f"Smart prompt generated and cached: {cache_path}")
            except Exception as e:
                print(f"Smart prompt failed ({e}), falling back to simple prompt")

    if prompt is None:
        prompt = _build_prompt(script)

    print(f"SD generating: {prompt[:80]}...")

    raw_img = _call_sd_api(prompt)
    processed = _post_process(raw_img)
    processed.save(output_path, quality=95)

    print(f"SD background saved: {output_path}")
    return output_path


def ensure_sd_bg(script: dict, bg_dir: str, smart_bg: bool = False) -> str:
    """Ensure SD background exists for script, generate if needed. Returns path."""
    os.makedirs(bg_dir, exist_ok=True)
    script_id = script.get("id", "unknown")
    path = os.path.join(bg_dir, f"sd_{script_id}.jpg")

    if os.path.exists(path):
        print(f"SD background cached: {path}")
        return path

    return generate_sd_bg(script, path, smart_bg=smart_bg)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sd_bg_generator.py <script.json> [--smart-bg]")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        script = json.load(f)

    smart_bg = "--smart-bg" in sys.argv
    os.makedirs("backgrounds", exist_ok=True)
    generate_sd_bg(script, f"backgrounds/sd_{script['id']}.jpg", smart_bg=smart_bg)
