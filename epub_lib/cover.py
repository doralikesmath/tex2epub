"""epub_lib.cover -- generate a simple cover image.

Deliberately minimal: a solid background, the title, an author line, an
accent rule. Pass --cover on the command line to supply your own artwork
instead.
"""
from __future__ import annotations

from pathlib import Path


def generate(title: str, author: str, out_path: Path,
             size: tuple[int, int] = (1200, 1600)) -> None:
    """Write a basic cover PNG. Requires Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:                      # pragma: no cover
        raise RuntimeError("Pillow is required for cover generation "
                           "(pip install pillow), or pass --no-cover.")

    W, H = size
    img = Image.new("RGB", (W, H), "#0f3764")
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 340, W, H - 330], fill="#1e5aa0")

    def font(sz: int):
        for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/Library/Fonts/Georgia.ttf"):
            try:
                return ImageFont.truetype(p, sz)
            except OSError:
                continue
        return ImageFont.load_default()

    def centred(text: str, y: int, fnt, fill="white"):
        bb = d.textbbox((0, 0), text, font=fnt)
        d.text(((W - (bb[2] - bb[0])) / 2, y), text, font=fnt, fill=fill)

    # word-wrap the title to at most ~16 chars per line
    words = title.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 16 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)

    y = 320
    for ln in lines[:4]:
        centred(ln.upper(), y, font(92))
        y += 116

    if author:
        centred(author, H - 470, font(46), "#9fc4e8")

    img.save(out_path)
