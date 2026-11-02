#!/usr/bin/env python3
"""Generate deterministic photo-like PNG fixtures for the web-vitals harness.

Purpose:
Create N photo-like PNGs with mixed portrait and landscape sizes between 832 and 1216 px.
Flat synthetic images compress to almost nothing, so they make album and home timings
look better than real libraries. These images carry gradients, shapes and texture so the
derived thumb_512 and preview_1440 WebP files land near real-photo byte sizes.

Guarantees:
* the same --out, --count and --seed produce identical PNG bytes; PIL's effect_noise
  cannot be seeded, so the texture uses seeded random bytes with the same mid-frequency
  look (6 px cells upscaled bicubically, blended at alpha 0.3, plus fine grain at alpha
  0.05; grain 0.1 pushed preview_1440 past 380 KB, so 0.05 keeps it near 250 KB)
* every image is 832-1216 px on both sides, in either orientation
* the first three images print their measured thumb_512 (WebP q78) and preview_1440
  (WebP q86) sizes; thumb_512 is aimed at about 35-50 KB per image
* uses PIL only; numpy is not required

Run when:
* preparing a fixture library for scripts/perf/web_vitals/ (see README.md)
* changing the photo-like fixture used by the web-vitals measurements
"""

from __future__ import annotations

import argparse
import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

MIN_EDGE = 832
MAX_EDGE = 1216
EDGE_STEP = 8
SHAPE_COUNT = 80
SHAPE_BLUR_RADIUS = 1.2
TEXTURE_CELL = 6
TEXTURE_ALPHA = 0.3
GRAIN_ALPHA = 0.05
THUMB_EDGE = 512
THUMB_QUALITY = 78
PREVIEW_EDGE = 1440
PREVIEW_QUALITY = 86
REPORT_COUNT = 3
WEBP_METHOD = 4


def _ramp(low: int, high: int) -> list[int]:
    """Return a 256-entry lookup table that maps 0..255 linearly onto low..high."""
    return [low + (high - low) * value // 255 for value in range(256)]


def _size(rng: random.Random) -> tuple[int, int]:
    """Pick a size whose short and long edges both sit inside the 832-1216 range."""
    short = rng.randrange(MIN_EDGE, MAX_EDGE + 1, EDGE_STEP)
    long_edge = rng.randrange(short, MAX_EDGE + 1, EDGE_STEP)
    return (short, long_edge) if rng.random() < 0.5 else (long_edge, short)


def _color(rng: random.Random) -> tuple[int, int, int]:
    """Return a random RGB colour."""
    return (rng.randrange(256), rng.randrange(256), rng.randrange(256))


def _gradient_channel(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    """Blend a random-direction linear ramp with a radial ramp into one grayscale channel."""
    linear = Image.linear_gradient("L")
    if rng.random() < 0.5:
        linear = linear.transpose(Image.Transpose.ROTATE_90)
    if rng.random() < 0.5:
        linear = linear.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    low, high = sorted(rng.randrange(256) for _ in range(2))
    linear = linear.resize(size, Image.Resampling.BILINEAR).point(_ramp(low, high))
    radial_low, radial_high = sorted(rng.randrange(256) for _ in range(2))
    radial = Image.radial_gradient("L").resize(size, Image.Resampling.BILINEAR).point(_ramp(radial_low, radial_high))
    return Image.blend(linear, radial, rng.uniform(0.2, 0.5))


def _gradient_base(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    """Build the RGB base from three independent gradient channels."""
    channels = [_gradient_channel(rng, size) for _ in range(3)]
    return Image.merge("RGB", channels)


def _draw_shapes(image: Image.Image, rng: random.Random) -> Image.Image:
    """Draw random ellipses and lines on a transparent layer, blur it slightly, and composite it."""
    width, height = image.size
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for _ in range(SHAPE_COUNT):
        color = (*_color(rng), rng.randrange(50, 170))
        if rng.random() < 0.6:
            cx = rng.uniform(-0.1, 1.1) * width
            cy = rng.uniform(-0.1, 1.1) * height
            rx = rng.uniform(0.02, 0.25) * width
            ry = rng.uniform(0.02, 0.25) * height
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=color)
        else:
            points = (
                rng.uniform(0, width),
                rng.uniform(0, height),
                rng.uniform(0, width),
                rng.uniform(0, height),
            )
            draw.line(points, fill=color, width=rng.randrange(2, 13))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=SHAPE_BLUR_RADIUS))
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def _texture(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    """Return a mid-frequency grayscale noise field: random 4 px cells upscaled with bicubic filtering."""
    width, height = size
    cells = (-(-width // TEXTURE_CELL), -(-height // TEXTURE_CELL))
    coarse = Image.frombytes("L", cells, rng.randbytes(cells[0] * cells[1]))
    return coarse.resize(size, Image.Resampling.BICUBIC)


def _grain(rng: random.Random, size: tuple[int, int]) -> Image.Image:
    """Return a full-resolution grayscale grain field from seeded random bytes."""
    width, height = size
    return Image.frombytes("L", size, rng.randbytes(width * height))


def make_photo(rng: random.Random) -> Image.Image:
    """Generate one photo-like RGB image using the supplied seeded random generator."""
    size = _size(rng)
    image = _gradient_base(rng, size)
    image = _draw_shapes(image, rng)
    texture = _texture(rng, size)
    image = Image.blend(image, Image.merge("RGB", (texture, texture, texture)), TEXTURE_ALPHA)
    grain = _grain(rng, size)
    return Image.blend(image, Image.merge("RGB", (grain, grain, grain)), GRAIN_ALPHA)


def _fit(image: Image.Image, edge: int) -> Image.Image:
    """Scale the long edge down to ``edge`` (Lanczos) and never upscale, like the backend derivatives."""
    if max(image.size) <= edge:
        return image
    scale = edge / max(image.size)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def webp_size(image: Image.Image, edge: int, quality: int) -> int:
    """Return the encoded WebP byte size of ``image`` fitted to ``edge``."""
    buffer = io.BytesIO()
    _fit(image, edge).save(buffer, "WEBP", quality=quality, method=WEBP_METHOD)
    return len(buffer.getvalue())


def _kib(size: int) -> str:
    """Format a byte count as KB with one decimal."""
    return f"{size / 1024:.1f} KB"


def main(argv: list[str] | None = None) -> int:
    """Write the fixture PNGs and print the first images' derivative sizes."""
    parser = argparse.ArgumentParser(description="Generate deterministic photo-like PNG fixtures.")
    parser.add_argument("--out", type=Path, required=True, help="directory to write photo_NNN.png files into")
    parser.add_argument("--count", type=int, default=20, help="number of images to generate (default: 20)")
    parser.add_argument("--seed", type=int, default=1, help="seed for reproducible output (default: 1)")
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count must be at least 1")

    args.out.mkdir(parents=True, exist_ok=True)
    for index in range(args.count):
        image = make_photo(random.Random(f"{args.seed}:{index}"))
        name = f"photo_{index:03d}.png"
        image.save(args.out / name, "PNG")
        if index < REPORT_COUNT:
            thumb = webp_size(image, THUMB_EDGE, THUMB_QUALITY)
            preview = webp_size(image, PREVIEW_EDGE, PREVIEW_QUALITY)
            print(
                f"{name} {image.width}x{image.height} "
                f"thumb_512 webp q{THUMB_QUALITY} {_kib(thumb)} "
                f"preview_1440 webp q{PREVIEW_QUALITY} {_kib(preview)}"
            )
    print(f"wrote {args.count} PNG fixtures to {args.out} (seed {args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
