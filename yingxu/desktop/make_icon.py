"""Render this application's original vector mark into an offline Windows icon."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect width="256" height="256" rx="58" fill="#191d1c"/>
<rect x="44" y="53" width="168" height="150" rx="18" fill="#a7baa7"/>
<rect x="66" y="69" width="124" height="118" rx="7" fill="#242c28"/>
<path d="M108 94L156 128L108 162Z" fill="#e9e8dc"/>
<g fill="#191d1c"><rect x="51" y="73" width="9" height="17" rx="3"/><rect x="51" y="111" width="9" height="17" rx="3"/><rect x="51" y="150" width="9" height="17" rx="3"/><rect x="196" y="90" width="9" height="17" rx="3"/><rect x="196" y="128" width="9" height="17" rx="3"/><rect x="196" y="166" width="9" height="17" rx="3"/></g>
</svg>'''
(root / "brand.svg").write_text(svg, encoding="utf-8")
scale = 4
image = Image.new("RGBA", (256 * scale, 256 * scale), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)


def rect(box, radius, color):
    draw.rounded_rectangle(tuple(int(x * scale) for x in box), radius * scale, fill=color)


rect((0, 0, 255, 255), 58, "#191d1c")
rect((44, 53, 212, 203), 18, "#a7baa7")
rect((66, 69, 190, 187), 7, "#242c28")
draw.polygon([(108 * scale, 94 * scale), (156 * scale, 128 * scale), (108 * scale, 162 * scale)], fill="#e9e8dc")
for x, y in [(51, 73), (51, 111), (51, 150), (196, 90), (196, 128), (196, 166)]:
    rect((x, y, x + 9, y + 17), 3, "#191d1c")
image = image.resize((256, 256), Image.Resampling.LANCZOS)
image.save(root / "brand.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Created original sage film icon")
