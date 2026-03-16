"""
Run once on the Pi to generate src/assets/icon.png.
  python src/assets/create_icon.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE      = 256
ASSETS    = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(ASSETS, "MaterialIcons-Regular.ttf")
OUT_PATH  = os.path.join(ASSETS, "icon.png")

img  = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Dark circle background
draw.ellipse([4, 4, SIZE - 4, SIZE - 4], fill=(30, 30, 40, 255))

# Flight glyph (Material Icons: flight \ue539)
font  = ImageFont.truetype(FONT_PATH, 160)
glyph = "\ue539"
bbox  = draw.textbbox((0, 0), glyph, font=font)
x     = (SIZE - (bbox[2] - bbox[0])) // 2 - bbox[0]
y     = (SIZE - (bbox[3] - bbox[1])) // 2 - bbox[1]
draw.text((x, y), glyph, font=font, fill=(100, 180, 255, 255))

img.save(OUT_PATH)
print(f"Saved {OUT_PATH}")
