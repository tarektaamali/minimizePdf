"""Prove the installation works, in French, before the installer exits.

This checks that every pinned dependency loads and that a real compression
runs end to end: pikepdf opens and saves, Pillow encodes CCITT G4, numpy
packs the bitmaps, scipy despeckles, and pypdfium2 reads the result back.

It deliberately does not assert that the output is smaller than the input.
The sample is synthetic and noise-free, so Flate compresses it better than
G4 does; a real scan behaves the other way round. Asserting size here would
fail on a perfectly good installation.
"""

import os
import tempfile

import numpy as np
import pikepdf
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from pikepdf import Dictionary, Name

from pdfshrink.core import HAVE_SCIPY, shrink

LINE = ("Reduire PDF - verification de l'installation - 0123456789 "
        "ABCDEFGHIJKLM nopqrstuvwxyz")
PAGES = 2


def _font(size):
    for candidate in (r"C:\Windows\Fonts\arial.ttf",
                      "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def sample(path):
    """Two pages of rendered text at 150 dpi."""
    w, h = 1240, 1754
    font = _font(26)
    pdf = pikepdf.new()
    for _ in range(PAGES):
        page_image = Image.new("L", (w, h), 255)
        draw = ImageDraw.Draw(page_image)
        for row in range(120, h - 120, 44):
            draw.text((110, row), LINE, fill=0, font=font)
        ink = np.array(page_image) < 128
        stream = pdf.make_stream(np.packbits(~ink, axis=1).tobytes())
        stream.Type, stream.Subtype = Name.XObject, Name.Image
        stream.Width, stream.Height = w, h
        stream.ColorSpace, stream.BitsPerComponent = Name.DeviceGray, 1
        page = pdf.add_blank_page(page_size=(595.2, 841.44))
        page.Contents = pdf.make_stream(b"q 595.2 0 0 841.44 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    pdf.save(path)


def check(src, dst):
    if not HAVE_SCIPY:
        return "scipy est absent, le nettoyage des images ne fonctionnera pas."

    sample(src)
    result = shrink(src, dst, target=200 * 1024)
    if not result.ok or not os.path.exists(dst):
        return "la compression n'a pas abouti."

    doc = pdfium.PdfDocument(dst)
    try:
        if len(doc) != PAGES:
            return "le document produit a %d pages au lieu de %d." % (
                len(doc), PAGES)
        rendered = np.array(
            doc[0].render(scale=1.0, grayscale=True).to_pil().convert("L"))
    finally:
        doc.close()

    ink = float((rendered < 128).mean())
    if not 0.005 < ink < 0.9:
        return "le document produit ne contient pas de texte lisible."

    print("OK : %d octets -> %d octets, %d pages, texte relu"
          % (os.path.getsize(src), os.path.getsize(dst), PAGES))
    return None


def main():
    folder = tempfile.mkdtemp()
    src = os.path.join(folder, "test.pdf")
    dst = os.path.join(folder, "out.pdf")
    try:
        problem = check(src, dst)
        if problem:
            print("ECHEC : %s" % problem)
            return 1
        return 0
    except Exception as error:                      # noqa: BLE001
        print("ECHEC : %s" % error)
        return 1
    finally:
        for path in (src, dst):
            if os.path.exists(path):
                os.remove(path)
        os.rmdir(folder)


if __name__ == "__main__":
    raise SystemExit(main())
