"""Page inspection and rasterisation, built on pikepdf and pypdfium2.

This module exists to keep Poppler out of the project: every fact the
engine needs about a document is obtained through a pip-installable
library, so the same code runs on macOS and Windows.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pikepdf
from PIL import Image


@dataclass
class Profile:
    pages: int
    kind: str                      # "bilevel" | "raster" | "digital"
    dpi: Optional[int]
    page_pts: Tuple[float, float]
    has_text_layer: bool = False


def _page_images(page):
    resources = page.get("/Resources", {})
    xobjects = resources.get("/XObject", {})
    out = []
    for _, obj in dict(xobjects).items():
        if str(obj.get("/Subtype")) == "/Image":
            out.append(obj)
    return out


def inspect(path):
    with pikepdf.open(path) as pdf:
        pages = list(pdf.pages)
        n = len(pages)
        box = [float(v) for v in pages[0].mediabox]
        pts = (box[2] - box[0], box[3] - box[1])

        has_text = any("/Font" in p.get("/Resources", {}) for p in pages)

        widths, depths, full_page = [], set(), 0
        for page in pages:
            images = _page_images(page)
            if len(images) != 1:
                continue
            img = images[0]
            w, h = int(img.Width), int(img.Height)
            pw = float(page.mediabox[2]) - float(page.mediabox[0])
            ph = float(page.mediabox[3]) - float(page.mediabox[1])
            # An image is "full page" when it resolves to within 10% of
            # the page's own aspect and covers it; a logo never does.
            aspect = (w / pw) / (h / ph) if pw > 0 and ph > 0 else 0
            if 0.9 < aspect < 1.1:
                full_page += 1
                widths.append(w / (pw / 72.0))
                depths.add(int(img.get("/BitsPerComponent", 8)))

        if full_page != n or not widths:
            return Profile(n, "digital", None, pts, has_text)

        dpi = int(round(sum(widths) / len(widths)))
        kind = "bilevel" if depths == {1} else "raster"
        return Profile(n, kind, dpi, pts, has_text)
