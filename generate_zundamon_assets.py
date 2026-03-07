"""Generate Zundamon-style avatar sprites (mouth_0..3.png).

Run once to create assets:
    python generate_zundamon_assets.py

Outputs 300x300 RGBA PNGs to avatars/zundamon/.
Draws at 4x resolution then downscales for clean anti-aliasing.
"""

import os
from PIL import Image, ImageDraw

SIZE = 300
SCALE = 4          # draw at 4x, downscale for AA
S = SCALE           # shorthand
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatars", "zundamon")

# ── Color palette ────────────────────────────────────────────────────────────
HAIR_BASE    = (110, 200, 100, 255)      # bright edamame green
HAIR_DARK    = (70, 155, 60, 255)        # shadow green
HAIR_LIGHT   = (150, 225, 130, 255)      # highlight green
HAIR_OUTLINE = (55, 120, 45, 255)        # dark outline

SKIN         = (255, 232, 210, 255)      # warm peach
SKIN_SHADOW  = (245, 210, 185, 255)      # chin shadow

BLUSH        = (255, 175, 175, 90)       # cheek blush

EYE_WHITE    = (255, 255, 255, 255)
IRIS_OUTER   = (80, 175, 70, 255)        # green iris outer
IRIS_INNER   = (55, 130, 50, 255)        # green iris inner
PUPIL        = (25, 50, 25, 255)
HIGHLIGHT_L  = (255, 255, 255, 240)      # large highlight
HIGHLIGHT_S  = (255, 255, 255, 180)      # small highlight

EYEBROW      = (65, 130, 55, 220)        # green-tinted brows

MOUTH_LINE   = (160, 80, 70, 255)
MOUTH_FILL   = (190, 75, 65, 255)
TONGUE       = (225, 110, 110, 230)
TEETH        = (255, 252, 248, 220)

OUTFIT_WHITE = (245, 245, 250, 255)
OUTFIT_TRIM  = (100, 195, 90, 255)

ACCESSORY_BEAN = (130, 210, 100, 255)    # edamame accessory
ACCESSORY_DARK = (80, 165, 65, 255)


def sc(*coords):
    """Scale coordinates by the global SCALE factor."""
    return [c * S for c in coords]


def _draw_back_hair(draw: ImageDraw.ImageDraw):
    """Draw hair behind the face — main volume."""
    # Main hair mass (large rounded shape)
    draw.ellipse(sc(35, 20, 265, 220), fill=HAIR_BASE, outline=HAIR_OUTLINE, width=2*S)

    # Side hair falling down (left)
    draw.polygon(sc(40, 130, 30, 250, 55, 260, 70, 180), fill=HAIR_BASE)
    draw.polygon(sc(35, 140, 25, 255, 40, 260, 50, 180), fill=HAIR_DARK)

    # Side hair falling down (right)
    draw.polygon(sc(260, 130, 270, 250, 245, 260, 230, 180), fill=HAIR_BASE)
    draw.polygon(sc(265, 140, 275, 255, 260, 260, 250, 180), fill=HAIR_DARK)

    # Hair volume highlight (top-left)
    draw.ellipse(sc(60, 30, 160, 100), fill=HAIR_LIGHT)


def _draw_face(draw: ImageDraw.ImageDraw):
    """Draw the face shape."""
    # Main face oval (larger, more prominent)
    draw.ellipse(sc(62, 100, 238, 265), fill=SKIN)

    # Subtle chin shadow
    draw.ellipse(sc(90, 225, 210, 268), fill=SKIN_SHADOW)

    # Ears (small, partially hidden by hair)
    draw.ellipse(sc(55, 155, 75, 190), fill=SKIN)
    draw.ellipse(sc(225, 155, 245, 190), fill=SKIN)
    # Inner ear
    draw.ellipse(sc(59, 160, 71, 183), fill=SKIN_SHADOW)
    draw.ellipse(sc(229, 160, 241, 183), fill=SKIN_SHADOW)


def _draw_front_hair(draw: ImageDraw.ImageDraw):
    """Draw bangs and front hair details over the face."""
    # Top hair dome
    draw.ellipse(sc(48, 10, 252, 140), fill=HAIR_BASE)

    # Hair highlight (broad, top area)
    draw.ellipse(sc(65, 18, 220, 78), fill=HAIR_LIGHT)

    # Fringe: solid base block that covers forehead
    draw.rectangle(sc(68, 90, 232, 138), fill=HAIR_BASE)

    # Smooth bottom edge of fringe: row of overlapping ellipses
    for bx in range(72, 228, 10):
        draw.ellipse(sc(bx - 12, 128, bx + 12, 154), fill=HAIR_BASE)

    # Subtle light patch on left side of bangs (wide, blends in)
    draw.ellipse(sc(70, 70, 180, 130), fill=HAIR_LIGHT)

    # Side hair locks (tapered shapes)
    # Left lock
    draw.polygon(sc(48, 100, 35, 180, 40, 225, 58, 228, 68, 160, 68, 110),
                 fill=HAIR_BASE)
    draw.polygon(sc(42, 110, 32, 185, 36, 222, 48, 225, 55, 160, 55, 115),
                 fill=HAIR_DARK)

    # Right lock
    draw.polygon(sc(252, 100, 265, 180, 260, 225, 242, 228, 232, 160, 232, 110),
                 fill=HAIR_BASE)
    draw.polygon(sc(258, 110, 268, 185, 264, 222, 252, 225, 245, 160, 245, 115),
                 fill=HAIR_DARK)


def _draw_ahoge(draw: ImageDraw.ImageDraw):
    """Draw the antenna hair (ahoge) on top."""
    # Main ahoge — curved upward
    draw.polygon(sc(148, 35, 140, 0, 155, 5, 152, 30), fill=HAIR_BASE)
    draw.polygon(sc(148, 30, 135, -5, 145, 0, 148, 25), fill=HAIR_LIGHT)
    draw.line(sc(142, 2, 148, 30), fill=HAIR_OUTLINE, width=S)


def _draw_edamame_accessory(draw: ImageDraw.ImageDraw):
    """Draw the edamame hair clip on the left side of hair."""
    # Bean pod shape (3 bumps)
    ax, ay = 65, 100
    draw.ellipse(sc(ax-12, ay-6, ax+4, ay+10), fill=ACCESSORY_BEAN, outline=ACCESSORY_DARK, width=S)
    draw.ellipse(sc(ax-6, ay-10, ax+10, ay+6), fill=ACCESSORY_BEAN, outline=ACCESSORY_DARK, width=S)
    draw.ellipse(sc(ax+2, ay-14, ax+18, ay+2), fill=ACCESSORY_BEAN, outline=ACCESSORY_DARK, width=S)
    # Highlights
    draw.ellipse(sc(ax-8, ay-3, ax-2, ay+3), fill=HAIR_LIGHT)
    draw.ellipse(sc(ax-2, ay-7, ax+4, ay-1), fill=HAIR_LIGHT)
    draw.ellipse(sc(ax+6, ay-11, ax+12, ay-5), fill=HAIR_LIGHT)


def _draw_eyes(draw: ImageDraw.ImageDraw):
    """Draw large anime-style eyes."""
    for is_right, ex in enumerate([118, 182]):
        ey = 178

        # Eye outline (slightly thicker on top)
        draw.ellipse(sc(ex-24, ey-20, ex+24, ey+20), fill=EYE_WHITE,
                     outline=HAIR_OUTLINE, width=2*S)

        # Upper eyelid line (thicker)
        draw.arc(sc(ex-24, ey-22, ex+24, ey+18), start=200, end=340,
                 fill=HAIR_OUTLINE, width=3*S)

        # Iris (large, expressive)
        draw.ellipse(sc(ex-17, ey-14, ex+17, ey+18), fill=IRIS_OUTER)

        # Inner iris gradient
        draw.ellipse(sc(ex-13, ey-10, ex+13, ey+14), fill=IRIS_INNER)

        # Pupil
        draw.ellipse(sc(ex-8, ey-6, ex+8, ey+10), fill=PUPIL)

        # Iris ring detail
        draw.arc(sc(ex-15, ey-12, ex+15, ey+16), start=220, end=320,
                 fill=(90, 190, 80, 120), width=2*S)

        # Large highlight (upper-right for left eye, upper-left for right eye)
        hx_off = 5 if is_right == 0 else -5
        draw.ellipse(sc(ex+hx_off-4, ey-14, ex+hx_off+8, ey-2), fill=HIGHLIGHT_L)

        # Small secondary highlight (lower-left)
        draw.ellipse(sc(ex-hx_off-8, ey+4, ex-hx_off-2, ey+10), fill=HIGHLIGHT_S)

        # Eyelashes (top, small strokes)
        if is_right == 0:  # left eye
            draw.line(sc(ex-22, ey-16, ex-27, ey-22), fill=HAIR_OUTLINE, width=2*S)
            draw.line(sc(ex-16, ey-20, ex-19, ey-28), fill=HAIR_OUTLINE, width=2*S)
        else:  # right eye
            draw.line(sc(ex+22, ey-16, ex+27, ey-22), fill=HAIR_OUTLINE, width=2*S)
            draw.line(sc(ex+16, ey-20, ex+19, ey-28), fill=HAIR_OUTLINE, width=2*S)


def _draw_eyebrows(draw: ImageDraw.ImageDraw):
    """Draw expressive eyebrows."""
    # Left eyebrow
    draw.arc(sc(93, 136, 143, 160), start=210, end=330,
             fill=EYEBROW, width=3*S)
    # Right eyebrow
    draw.arc(sc(157, 136, 207, 160), start=210, end=330,
             fill=EYEBROW, width=3*S)


def _draw_nose_and_cheeks(draw: ImageDraw.ImageDraw):
    """Draw subtle nose and cheek blush."""
    # Nose: tiny accent
    draw.arc(sc(144, 204, 156, 215), start=30, end=150,
             fill=(210, 175, 160, 140), width=2*S)

    # Cheek blush (soft ellipses)
    draw.ellipse(sc(75, 198, 110, 222), fill=BLUSH)
    draw.ellipse(sc(190, 198, 225, 222), fill=BLUSH)


def _draw_outfit(draw: ImageDraw.ImageDraw):
    """Draw the white outfit collar / upper body hint at the bottom."""
    # Neck
    draw.rectangle(sc(130, 252, 170, 275), fill=SKIN)

    # Collar / outfit top (white with green trim)
    draw.polygon(sc(80, 270, 70, 300, 230, 300, 220, 270, 175, 258, 125, 258),
                 fill=OUTFIT_WHITE)

    # Green trim lines
    draw.line(sc(125, 258, 80, 272), fill=OUTFIT_TRIM, width=2*S)
    draw.line(sc(175, 258, 220, 272), fill=OUTFIT_TRIM, width=2*S)

    # Center line
    draw.line(sc(150, 258, 150, 300), fill=OUTFIT_TRIM, width=S)

    # Green ribbon / bow
    draw.polygon(sc(135, 260, 125, 268, 135, 276, 145, 268), fill=OUTFIT_TRIM)
    draw.polygon(sc(165, 260, 155, 268, 165, 276, 175, 268), fill=OUTFIT_TRIM)
    draw.ellipse(sc(145, 264, 155, 274), fill=ACCESSORY_BEAN)


def _draw_mouth(draw: ImageDraw.ImageDraw, state: int):
    """Draw mouth at the given state (0=closed, 1=small, 2=medium, 3=large)."""
    cx, cy = 150, 232

    if state == 0:
        # Closed: gentle cat-mouth smile (w shape)
        draw.arc(sc(cx-14, cy-6, cx-2, cy+8), start=0, end=180,
                 fill=MOUTH_LINE, width=2*S)
        draw.arc(sc(cx+2, cy-6, cx+14, cy+8), start=0, end=180,
                 fill=MOUTH_LINE, width=2*S)

    elif state == 1:
        # Small open
        draw.ellipse(sc(cx-10, cy-4, cx+10, cy+8),
                     fill=MOUTH_FILL, outline=MOUTH_LINE, width=2*S)
        draw.ellipse(sc(cx-5, cy+1, cx+5, cy+8), fill=TONGUE)

    elif state == 2:
        # Medium open
        draw.ellipse(sc(cx-14, cy-8, cx+14, cy+14),
                     fill=MOUTH_FILL, outline=MOUTH_LINE, width=2*S)
        draw.ellipse(sc(cx-8, cy+3, cx+8, cy+14), fill=TONGUE)
        # Top teeth hint
        draw.ellipse(sc(cx-9, cy-8, cx+9, cy-2), fill=TEETH)

    else:
        # Large open — excited/shouting
        draw.ellipse(sc(cx-18, cy-12, cx+18, cy+20),
                     fill=MOUTH_FILL, outline=MOUTH_LINE, width=2*S)
        draw.ellipse(sc(cx-10, cy+5, cx+10, cy+20), fill=TONGUE)
        # Top teeth
        draw.ellipse(sc(cx-12, cy-12, cx+12, cy-4), fill=TEETH)
        # Bottom teeth hint
        draw.ellipse(sc(cx-8, cy+12, cx+8, cy+18), fill=TEETH)


def generate():
    os.makedirs(OUT_DIR, exist_ok=True)

    for state in range(4):
        canvas = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # Draw layers back-to-front
        _draw_back_hair(draw)
        _draw_face(draw)
        _draw_outfit(draw)
        _draw_nose_and_cheeks(draw)
        _draw_eyes(draw)
        _draw_eyebrows(draw)
        _draw_mouth(draw, state)
        _draw_front_hair(draw)
        _draw_ahoge(draw)
        _draw_edamame_accessory(draw)

        # Downscale with high-quality resampling
        img = canvas.resize((SIZE, SIZE), Image.LANCZOS)

        path = os.path.join(OUT_DIR, f"mouth_{state}.png")
        img.save(path)
        print(f"Saved: {path}")

    print(f"\nAll 4 sprites saved to {OUT_DIR}")


if __name__ == "__main__":
    generate()
