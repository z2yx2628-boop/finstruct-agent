"""Create scanned-looking copies of text PDFs that already have Gold labels.

Each page is rendered to an image, lightly rotated, blurred and speckled,
then saved as an image-only PDF with the same file name. Running the frozen
extractor on both versions and scoring them against the SAME Gold isolates
the accuracy lost to OCR.

Usage:
    .\\.venv\\Scripts\\python.exe scripts\\make_synthetic_scans.py ^
        data\\raw\\capacity_v6_holdout data\\raw\\capacity_v6_holdout_scan
"""
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter

DPI = 150
SEED = 20260923


def degrade(image: Image.Image, rng: random.Random) -> Image.Image:
    image = image.convert("L")
    image = image.rotate(
        rng.uniform(-1.2, 1.2), expand=False, fillcolor=255,
        resample=Image.BICUBIC,
    )
    image = image.filter(ImageFilter.GaussianBlur(radius=0.6))
    pixels = image.load()
    width, height = image.size
    for _ in range(width * height // 400):
        x, y = rng.randrange(width), rng.randrange(height)
        pixels[x, y] = rng.choice((0, 255))
    return image


def make_scan(source: Path, target: Path, rng: random.Random) -> int:
    output = pymupdf.open()
    with pymupdf.open(source) as document:
        for page in document:
            pixmap = page.get_pixmap(dpi=DPI)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image = degrade(image, rng)
            buffer = target.with_suffix(".tmp.png")
            image.save(buffer)
            new_page = output.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, filename=str(buffer))
            buffer.unlink()
    output.save(target)
    pages = len(output)
    output.close()
    return pages


def main() -> int:
    source_dir, target_dir = Path(sys.argv[1]), Path(sys.argv[2])
    target_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for source in sorted(source_dir.glob("*.pdf")):
        target = target_dir / source.name
        pages = make_scan(source, target, rng)
        with pymupdf.open(target) as check:
            native = sum(len(page.get_text().strip()) for page in check)
        print(f"[ok] {source.name}: {pages} pages, native text chars = {native}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
