"""
Generates 4 original, minimal AI-face icons for Z.A.I.N.E's screen:
idle.png, listening.png, thinking.png, speaking.png
Run once: python generate_assets.py
Pure geometric shapes drawn with Pillow — no external images, no copyrighted material.
"""

import os
from PIL import Image, ImageDraw

SIZE = 400
BG = (10, 10, 10, 255)
OUT_DIR = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(OUT_DIR, exist_ok=True)


def new_canvas():
    img = Image.new("RGBA", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)
    return img, draw


def head_outline(draw, glow_color, glow_width=6):
    cx, cy, r = SIZE // 2, SIZE // 2, 150
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=glow_color, width=glow_width)


def save(img, name):
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print(f"Saved {path}")


# ---------- IDLE / REACTION ----------
img, draw = new_canvas()
GREY = (150, 150, 150, 255)
head_outline(draw, GREY)
cx, cy = SIZE // 2, SIZE // 2
eye_y = cy - 20
draw.ellipse([cx - 60, eye_y - 15, cx - 30, eye_y + 15], fill=GREY)  # left eye
draw.ellipse([cx + 30, eye_y - 15, cx + 60, eye_y + 15], fill=GREY)  # right eye
draw.line([cx - 35, cy + 50, cx + 35, cy + 50], fill=GREY, width=6)  # neutral mouth
save(img, "idle.png")

# ---------- LISTENING ----------
img, draw = new_canvas()
RED = (255, 51, 51, 255)
head_outline(draw, RED, glow_width=8)
cx, cy = SIZE // 2, SIZE // 2
eye_y = cy - 20
draw.ellipse([cx - 65, eye_y - 20, cx - 25, eye_y + 20], fill=RED)  # wide alert eyes
draw.ellipse([cx + 25, eye_y - 20, cx + 65, eye_y + 20], fill=RED)
# sound wave arcs on both sides (indicating audio input)
for i, r in enumerate([20, 35, 50]):
    bbox_l = [cx - 150 - r, cy - r, cx - 150 + r, cy + r]
    draw.arc(bbox_l, start=300, end=60, fill=RED, width=4)
    bbox_r = [cx + 150 - r, cy - r, cx + 150 + r, cy + r]
    draw.arc(bbox_r, start=120, end=240, fill=RED, width=4)
draw.line([cx - 25, cy + 55, cx + 25, cy + 55], fill=RED, width=6)
save(img, "listening.png")

# ---------- THINKING ----------
img, draw = new_canvas()
YELLOW = (255, 204, 0, 255)
head_outline(draw, YELLOW)
cx, cy = SIZE // 2, SIZE // 2
eye_y = cy - 25
# eyes looking upward (offset small circles near top of eye sockets)
draw.ellipse([cx - 60, eye_y - 15, cx - 30, eye_y + 15], outline=YELLOW, width=4)
draw.ellipse([cx - 50, eye_y - 12, cx - 40, eye_y - 2], fill=YELLOW)
draw.ellipse([cx + 30, eye_y - 15, cx + 60, eye_y + 15], outline=YELLOW, width=4)
draw.ellipse([cx + 40, eye_y - 12, cx + 50, eye_y - 2], fill=YELLOW)
draw.line([cx - 30, cy + 55, cx + 30, cy + 55], fill=YELLOW, width=6)
# thought dots rising to the upper right
for i, (dx, dy, r) in enumerate([(90, -90, 8), (115, -120, 11), (145, -155, 15)]):
    draw.ellipse([cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r], fill=YELLOW)
save(img, "thinking.png")

# ---------- SPEAKING ----------
img, draw = new_canvas()
BLUE = (51, 153, 255, 255)
head_outline(draw, BLUE, glow_width=8)
cx, cy = SIZE // 2, SIZE // 2
eye_y = cy - 20
draw.ellipse([cx - 60, eye_y - 15, cx - 30, eye_y + 15], fill=BLUE)
draw.ellipse([cx + 30, eye_y - 15, cx + 60, eye_y + 15], fill=BLUE)
# open mouth (oval)
draw.ellipse([cx - 35, cy + 35, cx + 35, cy + 75], fill=BLUE)
# sound waves radiating from the mouth
for i, r in enumerate([15, 30, 45]):
    bbox = [cx - r, cy + 90 - r // 2, cx + r, cy + 90 + r // 2]
    draw.arc(bbox, start=20, end=160, fill=BLUE, width=4)
save(img, "speaking.png")

print("All 4 assets generated.")
