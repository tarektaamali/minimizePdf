"""Encoders and PDF assembly.

jbig2enc is the one external binary this project tolerates, and it is
optional: without it, bilevel documents fall back to the raster path and
simply compress less well.
"""

import os
import shutil
import subprocess

import numpy as np
import pikepdf
from PIL import Image
from pikepdf import Dictionary, Name

JBIG2 = "jbig2"

# A double-clicked launcher does not always inherit a shell PATH that
# includes Homebrew, and silently losing JBIG2 means silently losing most
# of the compression, so look in the usual places too.
_EXTRA_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")


def jbig2_path():
    found = shutil.which(JBIG2)
    if found:
        return found
    for folder in _EXTRA_PATHS:
        candidate = os.path.join(folder, JBIG2)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def have_jbig2():
    return jbig2_path() is not None


def write_pbm(arr, path):
    Image.fromarray(np.where(arr, 0, 255).astype(np.uint8)).convert("1").save(path)


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
