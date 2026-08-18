"""Derive every shipped icon from the master artwork.

    python scripts/build_brand.py

Run it after replacing docs/brand/mithra.png. Hand-editing the derived files is
how a favicon ends up one revision behind the logo on the sign-in screen, with
nobody able to say which is current.

The two-mark decision is explained in docs/brand/README.md: the full compass rose
below about 48 pixels is a blur, so the small sizes carry its central aperture
instead — a reduction of the same artwork rather than a second logo.
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageFilter

ROOT = pathlib.Path(__file__).resolve().parent.parent
MASTER = ROOT / "docs/brand/mithra.png"
APP = ROOT / "apps/web/src/app"
PUBLIC = ROOT / "apps/web/public/brand"

# How much of the master's width the central aperture occupies. Measured, not
# guessed: below this the gold ring is cut, above it the spokes creep in and the
# reduction stops being legible at 16 pixels.
MEDALLION = 0.34


def _resize(image: Image.Image, size: int) -> Image.Image:
    out = image.resize((size, size), Image.Resampling.LANCZOS)
    if size <= 64:
        # Thin gold lines on lapis turn to grey mush under plain downsampling
        # well before 32px. Just enough sharpening to keep them as lines.
        return out.filter(ImageFilter.UnsharpMask(radius=0.6, percent=110, threshold=2))
    # Indistinguishable from full colour at these sizes, and a fifth smaller.
    return out.quantize(colors=256, method=Image.Quantize.FASTOCTREE).convert("RGBA")


def main() -> None:
    master = Image.open(MASTER).convert("RGBA")
    width, height = master.size

    half = MEDALLION / 2
    medallion = master.crop(
        (
            int(width * (0.5 - half)),
            int(height * (0.5 - half)),
            int(width * (0.5 + half)),
            int(height * (0.5 + half)),
        )
    )

    PUBLIC.mkdir(parents=True, exist_ok=True)

    # The tab, at the three sizes a browser actually asks for.
    _resize(medallion, 48).save(APP / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    _resize(master, 256).save(APP / "icon.png", optimize=True)
    _resize(master, 180).save(APP / "apple-icon.png", optimize=True)
    _resize(master, 256).save(PUBLIC / "logo.png", optimize=True)
    _resize(medallion, 64).save(PUBLIC / "mark.png", optimize=True)

    for path in (
        APP / "favicon.ico",
        APP / "icon.png",
        APP / "apple-icon.png",
        PUBLIC / "logo.png",
        PUBLIC / "mark.png",
    ):
        print(f"{path.relative_to(ROOT)!s:44} {path.stat().st_size / 1024:6.1f} KB")


if __name__ == "__main__":
    main()
