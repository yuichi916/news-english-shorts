"""Background gradient image generator v2 - Premium visual backgrounds.

Creates visually rich backgrounds for YouTube Shorts with:
- Multi-stop radial + linear gradient blend
- Bokeh light orbs (soft glowing circles)
- Diagonal accent lines
- Subtle geometric grid pattern
- Vignette + film grain noise
Each theme has gradient colors + accent colors for ASS subtitle styling.
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

WIDTH = 1080
HEIGHT = 1920

# Theme presets: (top, mid, bottom, radial_center, radial_edge)
THEMES = {
    "midnight": {
        "grad": [(18, 12, 52), (55, 48, 125), (22, 18, 55)],
        "radial": (80, 65, 160),
        "bokeh": [(120, 100, 255, 35), (80, 180, 255, 25), (200, 140, 255, 20)],
        "line": (100, 80, 200),
        "grid": (60, 50, 120),
    },
    "ocean": {
        "grad": [(10, 28, 58), (25, 85, 128), (14, 35, 62)],
        "radial": (30, 110, 160),
        "bokeh": [(50, 200, 255, 30), (100, 255, 220, 22), (30, 150, 255, 28)],
        "line": (50, 160, 220),
        "grid": (30, 80, 120),
    },
    "ember": {
        "grad": [(42, 10, 16), (115, 25, 35), (35, 12, 18)],
        "radial": (140, 45, 55),
        "bokeh": [(255, 120, 50, 30), (255, 80, 80, 25), (255, 180, 60, 20)],
        "line": (220, 80, 50),
        "grid": (120, 40, 30),
    },
    "forest": {
        "grad": [(8, 38, 22), (20, 78, 50), (10, 32, 20)],
        "radial": (30, 100, 65),
        "bokeh": [(60, 255, 120, 28), (120, 255, 80, 22), (40, 200, 160, 25)],
        "line": (60, 200, 100),
        "grid": (30, 80, 50),
    },
    "purple": {
        "grad": [(28, 8, 55), (82, 28, 112), (20, 10, 45)],
        "radial": (110, 40, 140),
        "bokeh": [(200, 100, 255, 32), (255, 80, 200, 22), (140, 120, 255, 26)],
        "line": (180, 80, 240),
        "grid": (90, 40, 120),
    },
}

# Theme accent colors for ASS styling (ASS BGR format: &HBBGGRR)
THEME_ACCENTS = {
    "midnight": {"accent": "&H00FFCC00&", "highlight": "&H0088FF00&", "streak": (100, 150, 255)},
    "ocean":    {"accent": "&H00FFDD44&", "highlight": "&H0000DDAA&", "streak": (60, 180, 255)},
    "ember":    {"accent": "&H004488FF&", "highlight": "&H002299FF&", "streak": (255, 120, 60)},
    "forest":   {"accent": "&H0044FFAA&", "highlight": "&H0066FF66&", "streak": (80, 255, 120)},
    "purple":   {"accent": "&H00FF88DD&", "highlight": "&H00FF66AA&", "streak": (200, 130, 255)},
}

DEFAULT_THEME = "midnight"


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _draw_linear_gradient(img: Image.Image, colors: list):
    """Draw 3-stop vertical linear gradient."""
    draw = ImageDraw.Draw(img)
    mid_y = HEIGHT // 2
    for y in range(HEIGHT):
        if y < mid_y:
            t = y / mid_y
            color = _lerp_color(colors[0], colors[1], t)
        else:
            t = (y - mid_y) / (HEIGHT - mid_y)
            color = _lerp_color(colors[1], colors[2], t)
        draw.line([(0, y), (WIDTH, y)], fill=color)


def _add_radial_glow(img: Image.Image, center_color: tuple,
                     cx: int = None, cy: int = None, radius: int = None):
    """Add a soft radial glow at given position."""
    if cx is None:
        cx = WIDTH // 2
    if cy is None:
        cy = int(HEIGHT * 0.38)
    if radius is None:
        radius = int(HEIGHT * 0.45)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)

    for r in range(radius, 0, -3):
        t = r / radius
        alpha = int(max(0, 32 * (1 - t * t)))
        color_t = _lerp_color(center_color, (0, 0, 0), t * t)
        gdraw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(*color_t, alpha),
        )

    img_rgba = img.convert("RGBA")
    return Image.alpha_composite(img_rgba, glow).convert("RGB")


def _add_bokeh(img: Image.Image, bokeh_specs: list, seed: int = 42):
    """Add soft bokeh light orbs. Each spec: (r, g, b, max_alpha)."""
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    for _ in range(18):
        spec = rng.choice(bokeh_specs)
        r, g, b, max_alpha = spec

        orb_r = rng.randint(30, 120)
        x = rng.randint(-orb_r, WIDTH + orb_r)
        y = rng.randint(int(HEIGHT * 0.08), int(HEIGHT * 0.85))

        orb = Image.new("RGBA", (orb_r * 2, orb_r * 2), (0, 0, 0, 0))
        orb_draw = ImageDraw.Draw(orb)
        for ring in range(orb_r, 0, -1):
            t = ring / orb_r
            alpha = int(max_alpha * (1 - t * t))
            orb_draw.ellipse(
                [orb_r - ring, orb_r - ring, orb_r + ring, orb_r + ring],
                fill=(r, g, b, alpha),
            )

        orb = orb.filter(ImageFilter.GaussianBlur(radius=orb_r * 0.4))
        overlay.paste(orb, (x - orb_r, y - orb_r), orb)

    img_rgba = img.convert("RGBA")
    return Image.alpha_composite(img_rgba, overlay).convert("RGB")


def _add_diagonal_lines(img: Image.Image, line_color: tuple, count: int = 6, seed: int = 123):
    """Add subtle diagonal accent lines across the image."""
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for _ in range(count):
        alpha = rng.randint(8, 22)
        thickness = rng.randint(1, 3)
        # Lines go from left edge to right edge at various angles
        y_start = rng.randint(-200, HEIGHT + 200)
        y_end = y_start + rng.randint(-600, 600)
        draw.line(
            [(0, y_start), (WIDTH, y_end)],
            fill=(*line_color, alpha),
            width=thickness,
        )

    img_rgba = img.convert("RGBA")
    return Image.alpha_composite(img_rgba, overlay).convert("RGB")


def _add_grid_pattern(img: Image.Image, grid_color: tuple, spacing: int = 80):
    """Add subtle geometric grid pattern."""
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    alpha = 10

    # Horizontal lines
    for y in range(0, HEIGHT, spacing):
        draw.line([(0, y), (WIDTH, y)], fill=(*grid_color, alpha), width=1)

    # Vertical lines
    for x in range(0, WIDTH, spacing):
        draw.line([(x, 0), (x, HEIGHT)], fill=(*grid_color, alpha), width=1)

    # Diamond accent pattern (sparser)
    diamond_spacing = spacing * 3
    diamond_alpha = 14
    for cy in range(diamond_spacing, HEIGHT, diamond_spacing):
        for cx in range(diamond_spacing, WIDTH, diamond_spacing):
            size = 12
            pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
            draw.polygon(pts, outline=(*grid_color, diamond_alpha))

    img_rgba = img.convert("RGBA")
    return Image.alpha_composite(img_rgba, overlay).convert("RGB")


def _add_vignette(img: Image.Image, strength: int = 130):
    """Add radial vignette (darker edges)."""
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    cx, cy = WIDTH // 2, HEIGHT // 2
    max_dist = (cx ** 2 + cy ** 2) ** 0.5
    for ring in range(0, int(max_dist), 4):
        alpha = int(min(255, (ring / max_dist) ** 1.6 * strength))
        vdraw.ellipse(
            [cx - ring, cy - ring, cx + ring, cy + ring],
            outline=(0, 0, 0, alpha),
        )
    return Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")


def _add_noise(img: Image.Image, intensity: int = 10, seed: int = 42):
    """Add film grain noise for depth."""
    rng = random.Random(seed)
    noise = Image.new("RGB", (WIDTH, HEIGHT))
    noise_data = []
    for _ in range(WIDTH * HEIGHT):
        v = rng.randint(-intensity, intensity)
        noise_data.append((v, v, v))
    noise.putdata(noise_data)
    noise = noise.filter(ImageFilter.GaussianBlur(radius=0.8))

    img_arr = img.load()
    noise_arr = noise.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            r1, g1, b1 = img_arr[x, y]
            r2, g2, b2 = noise_arr[x, y]
            img_arr[x, y] = (
                max(0, min(255, r1 + r2)),
                max(0, min(255, g1 + g2)),
                max(0, min(255, b1 + b2)),
            )
    return img


def _add_light_streaks(img: Image.Image, streak_color: tuple, count: int = 3, seed: int = 77):
    """Add angled light streaks."""
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for i in range(count):
        streak_y = int(HEIGHT * (0.2 + 0.25 * i))
        angle = rng.uniform(-0.15, 0.15)
        width = rng.randint(40, 80)
        max_alpha = rng.randint(12, 25)

        for dy in range(-width, width + 1):
            t = abs(dy) / width
            alpha = int(max(0, max_alpha * (1 - t * t)))
            y1 = streak_y + dy
            y2 = int(y1 + WIDTH * math.tan(angle))
            draw.line([(0, y1), (WIDTH, y2)], fill=(*streak_color, alpha), width=1)

    img_rgba = img.convert("RGBA")
    return Image.alpha_composite(img_rgba, overlay).convert("RGB")


def create_gradient_bg(output_path: str, theme: str = DEFAULT_THEME) -> str:
    """Create a premium gradient background image with multiple visual layers."""
    t = THEMES.get(theme, THEMES[DEFAULT_THEME])
    accents = THEME_ACCENTS.get(theme, THEME_ACCENTS[DEFAULT_THEME])

    img = Image.new("RGB", (WIDTH, HEIGHT))

    # Layer 1: Linear gradient base
    _draw_linear_gradient(img, t["grad"])

    # Layer 2: Radial glow (center-upper area)
    img = _add_radial_glow(img, t["radial"])

    # Layer 3: Secondary radial glow (lower-right)
    img = _add_radial_glow(img, t["radial"],
                           cx=int(WIDTH * 0.75), cy=int(HEIGHT * 0.68),
                           radius=int(HEIGHT * 0.3))

    # Layer 4: Subtle geometric grid
    img = _add_grid_pattern(img, t["grid"])

    # Layer 5: Diagonal accent lines
    img = _add_diagonal_lines(img, t["line"])

    # Layer 6: Angled light streaks
    img = _add_light_streaks(img, accents["streak"])

    # Layer 7: Bokeh light orbs
    img = _add_bokeh(img, t["bokeh"])

    # Layer 8: Vignette
    img = _add_vignette(img)

    # Layer 9: Film grain noise
    img = _add_noise(img)

    img.save(output_path, quality=95)
    print(f"Background: {output_path}")
    return output_path


def ensure_theme_bg(theme: str, bg_dir: str) -> str:
    """Ensure background image exists for given theme, generate if needed."""
    os.makedirs(bg_dir, exist_ok=True)
    path = os.path.join(bg_dir, f"{theme}.jpg")
    if not os.path.exists(path):
        create_gradient_bg(path, theme=theme)
    return path


if __name__ == "__main__":
    import sys
    os.makedirs("backgrounds", exist_ok=True)
    if len(sys.argv) > 1:
        theme = sys.argv[1]
        create_gradient_bg(f"backgrounds/{theme}.jpg", theme=theme)
    else:
        for t_name in THEMES:
            create_gradient_bg(f"backgrounds/{t_name}.jpg", theme=t_name)
    print(f"Available themes: {', '.join(THEMES.keys())}")
