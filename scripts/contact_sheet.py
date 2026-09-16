"""Render one page at every G4 rung so a human can judge legibility.

Usage:
    python scripts/contact_sheet.py INPUT.pdf OUT.png [PAGE]

PAGE is 1-based and defaults to the page carrying the most ink.
"""

import os
import sys

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfshrink.core import G4_LADDER, prep                       # noqa: E402
from pdfshrink.encode import build_g4_pdf, g4_encode             # noqa: E402
from pdfshrink.render import inspect, load_bilevel_pages         # noqa: E402

DISPLAY_DPI = 300.0
BAND = 240


def _font():
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, 26)
    return ImageFont.load_default()


def _busiest_page(path):
    doc = pdfium.PdfDocument(path)
    try:
        best, score = 0, -1
        for i in range(len(doc)):
            arr = np.array(doc[i].render(scale=50 / 72.0,
                                         grayscale=True).to_pil().convert("L"))
            ink = int((arr < 128).sum())
            if ink > score:
                best, score = i, ink
        return best
    finally:
        doc.close()


def _crop(path, page_index, window):
    doc = pdfium.PdfDocument(path)
    try:
        pil = doc[page_index].render(scale=DISPLAY_DPI / 72.0,
                                     grayscale=True).to_pil().convert("L")
    finally:
        doc.close()
    y0, y1 = window
    w, h = pil.size
    return pil.crop((int(0.08 * w), int(y0 * h), int(0.72 * w), int(y1 * h)))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, out = sys.argv[1], sys.argv[2]
    page_index = int(sys.argv[3]) - 1 if len(sys.argv) > 3 \
        else _busiest_page(src)

    profile = inspect(src)
    if profile.kind != "bilevel":
        print("not a bilevel document: %s" % profile.kind)
        return 1

    doc = pdfium.PdfDocument(src)
    probe = np.array(doc[page_index].render(
        scale=200 / 72.0, grayscale=True).to_pil().convert("L"))
    doc.close()
    rows = (probe < 128).sum(axis=1)
    top = max(range(0, max(1, probe.shape[0] - BAND), 20),
              key=lambda y: rows[y:y + BAND].sum())
    window = (top / probe.shape[0], (top + BAND) / probe.shape[0])

    samples = [("original", src)]
    source = load_bilevel_pages(src)
    workdir = os.path.dirname(os.path.abspath(out))
    for scale, blur, bint, speck in G4_LADDER:
        dpi = int(round(profile.dpi * scale))
        pages = []
        for arr in source:
            page = prep(arr, scale, blur, bint, speck)
            h, w = page.shape
            pages.append((g4_encode(page), w, h))
        dst = os.path.join(workdir, "_sheet_%d.pdf" % dpi)
        build_g4_pdf(pages, dst, profile.page_pts)
        samples.append(("G4 %d dpi" % dpi, dst))

    font, crops = _font(), []
    for label, path in samples:
        crop = _crop(path, page_index, window)
        crops.append(("%s  -  %.0f Ko" % (label, os.path.getsize(path) / 1024),
                      crop))

    cw = max(c.width for _, c in crops)
    ch = max(c.height for _, c in crops)
    pad, bar = 12, 40
    sheet = Image.new("L", (cw + pad * 2,
                            (ch + bar + pad) * len(crops) + pad), 255)
    draw = ImageDraw.Draw(sheet)
    for i, (label, crop) in enumerate(crops):
        y = pad + i * (ch + bar + pad)
        draw.rectangle([pad, y, pad + cw, y + bar], fill=30)
        draw.text((pad + 10, y + 7), label, fill=255, font=font)
        sheet.paste(crop, (pad, y + bar))
    sheet.save(out)
    print("written:", out, "page", page_index + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
