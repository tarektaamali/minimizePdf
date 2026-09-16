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


import io

import pypdfium2 as pdfium

INK_THRESHOLD = 128


def _to_ink(image):
    """1 = ink. PIL gives white as True, hence the inversion."""
    return (~np.array(image.convert("1")).astype(bool)).astype(np.uint8)


def _is_jbig2(image):
    """JBIG2 is recognised up front rather than discovered by failure.

    pikepdf decodes it by spawning jbig2dec, which is not shipped, so
    letting it try means one doomed process per page.
    """
    return "/JBIG2Decode" in str(image.get("/Filter"))


def load_bilevel_pages(path):
    """Ink arrays at the embedded images' own resolution.

    pikepdf extracts the stored image directly, which is exact and cheap,
    but it shells out to jbig2dec for JBIG2 streams. That binary is not
    shipped, so those pages -- and any other pikepdf cannot decode -- are
    rendered with pypdfium2 instead, which decodes JBIG2 itself.
    """
    out, deferred = [], []
    with pikepdf.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            images = _page_images(page)
            if not images:
                raise ValueError("page without an image in a bilevel document")
            image = images[0]
            if _is_jbig2(image):
                out.append(None)
                deferred.append((index, int(image.Width), int(image.Height)))
                continue
            try:
                out.append(_to_ink(pikepdf.PdfImage(image).as_pil_image()))
            except Exception:
                out.append(None)
                deferred.append((index, int(image.Width), int(image.Height)))

    if deferred:
        doc = pdfium.PdfDocument(path)
        try:
            for index, w, h in deferred:
                page = doc[index]
                pil = page.render(scale=w / page.get_width(),
                                  grayscale=True).to_pil().convert("L")
                if pil.size != (w, h):
                    pil = pil.resize((w, h), Image.NEAREST)
                out[index] = (np.array(pil) < INK_THRESHOLD).astype(np.uint8)
        finally:
            doc.close()
    return out


def render_jpeg_pages(path, dpi, quality):
    """Rasterise every page to JPEG at the given resolution."""
    out = []
    doc = pdfium.PdfDocument(path)
    try:
        for index in range(len(doc)):
            pil = doc[index].render(scale=dpi / 72.0).to_pil().convert("RGB")
            buf = io.BytesIO()
            pil.save(buf, format="JPEG", quality=quality, optimize=True)
            out.append((buf.getvalue(), pil.width, pil.height))
    finally:
        doc.close()
    return out


def decode_pages_ink(path, shapes):
    """Render a PDF back to ink arrays matching the given shapes.

    Verification compares what the encoder was fed against what a reader
    actually sees, so this deliberately goes through a renderer rather
    than pulling the stored stream back out.
    """
    out = []
    doc = pdfium.PdfDocument(path)
    try:
        if len(doc) != len(shapes):
            raise ValueError("page count changed during compression")
        for index, (h, w) in enumerate(shapes):
            page = doc[index]
            scale = w / page.get_width()
            pil = doc[index].render(scale=scale, grayscale=True).to_pil().convert("L")
            if pil.size != (w, h):
                pil = pil.resize((w, h), Image.NEAREST)
            out.append((np.array(pil) < INK_THRESHOLD).astype(np.uint8))
    finally:
        doc.close()
    return out
