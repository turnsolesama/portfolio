"""Convert a selected PNG to application assets; Pillow is a build-only tool."""
import argparse
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
HEADER_SIZES = (36, 45, 54, 72)


def build(source, output=ROOT):
    output = Path(output)
    image = Image.open(source).convert('RGBA')
    if image.width != image.height:
        raise ValueError('Expected a square source image; no automatic cropping is performed.')
    if image.getchannel('A').getextrema()[0] == 255:
        raise ValueError('Source needs real transparency; this tool does not remove backgrounds.')
    (output / 'artwork').mkdir(parents=True, exist_ok=True)
    icon = image.resize((256, 256), Image.Resampling.LANCZOS)
    icon.save(output / 'switcher.png')
    # Tk's ICO loader requires BMP entries, not PNG-compressed ICO entries.
    icon.save(output / 'switcher.ico', format='ICO', bitmap_format='bmp',
              sizes=[(size, size) for size in ICON_SIZES])
    image.resize((64, 64), Image.Resampling.LANCZOS).save(output / 'switcher_64.png')
    for size in HEADER_SIZES:
        image.resize((size, size), Image.Resampling.LANCZOS).save(output / f'artwork/header-{size}.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.source, args.output)
