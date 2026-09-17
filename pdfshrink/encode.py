"""Encoders and PDF assembly.

jbig2enc is the one external binary this project tolerates, and it is
optional: without it, bilevel documents fall back to the raster path and
simply compress less well.
"""

import io
import os
import shutil
import subprocess

import numpy as np
import pikepdf
from PIL import Image, TiffImagePlugin
from pikepdf import Dictionary, Name

JBIG2 = "jbig2"

# Pillow splits a TIFF into strips once it exceeds this many bytes. A PDF
# CCITTFaxDecode stream must be one continuous G4 stream for the whole
# image, so strips are disabled outright: a partial strip decodes into a
# smaller file that looks entirely plausible and is silently corrupt.
TiffImagePlugin.STRIP_SIZE = 2 ** 28

# A double-clicked launcher does not always inherit a shell PATH that
# includes Homebrew, and silently losing JBIG2 means silently losing most
# of the compression, so look in the usual places too.
_EXTRA_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")

# Where the Windows installer puts the encoder: a jbig2 folder beside the
# application, holding jbig2.exe and the DLLs it links against. Windows
# resolves those DLLs from the executable's own directory, so they must
# stay together.
APP_DIRS = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "jbig2"),
)


def _executable(folder):
    for name in (JBIG2, JBIG2 + ".exe"):
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def jbig2_path():
    found = shutil.which(JBIG2)
    if found:
        return found
    for folder in tuple(APP_DIRS) + _EXTRA_PATHS:
        candidate = _executable(folder)
        if candidate:
            return candidate
    return None


def have_jbig2():
    return jbig2_path() is not None


def write_pbm(arr, path):
    Image.fromarray(np.where(arr, 0, 255).astype(np.uint8)).convert("1").save(path)


def g4_encode(arr):
    """CCITT group 4 bytes for a 1 = ink array, as a single strip."""
    image = Image.fromarray(np.where(arr, 0, 255).astype(np.uint8)).convert("1")
    buf = io.BytesIO()
    image.save(buf, format="TIFF", compression="group4")
    tif = Image.open(io.BytesIO(buf.getvalue()))
    offsets, counts = tif.tag_v2[273], tif.tag_v2[279]
    if len(offsets) != 1:
        raise ValueError("expected a single TIFF strip, got %d" % len(offsets))
    return buf.getvalue()[offsets[0]:offsets[0] + counts[0]]


def build_g4_pdf(pages, dst, pts):
    """Assemble CCITT G4 streams into a PDF.

    pages is a list of (g4_bytes, width, height). BlackIs1 is true because
    Pillow codes black as 1; false silently inverts every page.
    """
    pdf = pikepdf.new()
    for data, w, h in pages:
        img = pdf.make_stream(data)
        img.Type = Name.XObject
        img.Subtype = Name.Image
        img.Width = w
        img.Height = h
        img.ColorSpace = Name.DeviceGray
        img.BitsPerComponent = 1
        img.Filter = Name.CCITTFaxDecode
        img.DecodeParms = Dictionary(K=-1, Columns=w, Rows=h, BlackIs1=True)
        _place(pdf, img, pts)
    return _save(pdf, dst)


def jbig2_encode(pbm_paths, workdir, symthr):
    """Symbol-code a batch so repeated glyphs are stored once for all pages."""
    d = os.path.join(workdir, "enc")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for p in pbm_paths:
        shutil.copy(p, d)
    names = sorted(os.path.basename(p) for p in pbm_paths)
    subprocess.run([jbig2_path(), "-s", "-p", "-t", str(symthr)] + names,
                   cwd=d, check=True, capture_output=True)
    with open(os.path.join(d, "output.sym"), "rb") as fh:
        sym = fh.read()
    streams = []
    for i in range(len(names)):
        with open(os.path.join(d, "output.%04d" % i), "rb") as fh:
            streams.append(fh.read())
    return sym, streams


# TODO(preserve-structure): every builder below starts from pikepdf.new(), so
# annotations, links, outlines, form fields, page labels and XMP metadata are
# dropped - measured: 2 annotations and the document title lost on a rebuild.
# The fix is to open the source and replace each page's image XObject in place
# rather than constructing a fresh document around the new streams.
def _place(pdf, stream, pts):
    pw, ph = pts
    page = pdf.add_blank_page(page_size=(pw, ph))
    page.Contents = pdf.make_stream(
        ("q %.2f 0 0 %.2f 0 0 cm /Im0 Do Q" % (pw, ph)).encode())
    page.Resources = Dictionary(XObject=Dictionary(Im0=stream))


def _save(pdf, dst):
    pdf.save(dst, compress_streams=True,
             object_stream_mode=pikepdf.ObjectStreamMode.generate)
    return os.path.getsize(dst)


def build_jbig2_pdf(shapes, sym, streams, dst, pts):
    pdf = pikepdf.new()
    globals_stream = pdf.make_stream(sym)
    for (h, w), data in zip(shapes, streams):
        img = pdf.make_stream(data)
        img.Type = Name.XObject
        img.Subtype = Name.Image
        img.Width = w
        img.Height = h
        img.ColorSpace = Name.DeviceGray
        img.BitsPerComponent = 1
        img.Filter = Name.JBIG2Decode
        img.DecodeParms = Dictionary(JBIG2Globals=globals_stream)
        _place(pdf, img, pts)
    return _save(pdf, dst)


def build_jpeg_pdf(jpegs, dst, pts):
    pdf = pikepdf.new()
    for data, w, h in jpegs:
        img = pdf.make_stream(data)
        img.Type = Name.XObject
        img.Subtype = Name.Image
        img.Width = w
        img.Height = h
        img.ColorSpace = Name.DeviceRGB
        img.BitsPerComponent = 8
        img.Filter = Name.DCTDecode
        _place(pdf, img, pts)
    return _save(pdf, dst)


def lossless_save(src, dst):
    """Structural recompression only. Fonts and vectors stay untouched.

    pikepdf is libqpdf, so this is the same operation the qpdf binary
    performed, without requiring it to be installed.
    """
    with pikepdf.open(src) as pdf:
        pdf.save(dst, compress_streams=True, recompress_flate=True,
                 object_stream_mode=pikepdf.ObjectStreamMode.generate)
    return os.path.getsize(dst)
