# The mark

`mithra.png` is the master artwork: a compass rose in lapis and Achaemenid gold
with a camera aperture at its centre — navigation and imaging, which is what the
product does.

Everything shipped is derived from it by `scripts/build_brand.py`. Do not hand-edit
the derived files; replace the master and re-run the script.

| File | Size | Used for |
|---|---|---|
| `apps/web/src/app/favicon.ico` | 16, 32, 48 | The browser tab |
| `apps/web/src/app/icon.png` | 256 | The icon browsers prefer when they can |
| `apps/web/src/app/apple-icon.png` | 180 | Home screen on iOS |
| `apps/web/public/brand/logo.png` | 256 | Sign-in |
| `apps/web/public/brand/mark.png` | 64 | The navigation rail, at 26px |

## Two marks, one artwork

The full rose carries a ring of glyphs and sixteen spokes. Below about 48 pixels
those collapse into a blur, and a browser tab is sixteen — so the small sizes use
the central aperture alone, cropped from the same file at 34% of its width. It is
a reduction of the mark, not a second logo, and it is the part that still reads
when there is nothing left to draw with.

The full mark is used wherever there is room for it: sign-in, the README, and the
icon a phone puts on a home screen.
