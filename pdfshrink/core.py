"""Strategy selection and the quality ladders.

The ladders run best-quality-first and stop at the first rung that fits,
so the result is the best quality meeting the budget rather than the
smallest possible file. When nothing fits, the ladder is walked again from
the smallest end to find the smallest rung that still verifies clean; that
file is left at the destination so it can be offered without a second run.
"""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

from .encode import (build_jbig2_pdf, build_jpeg_pdf, have_jbig2,
                     jbig2_encode, lossless_save, write_pbm)
from .render import inspect, load_bilevel_pages, render_jpeg_pages
from .verify import is_clean, verify

try:
    from scipy import ndimage
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

# scale, blur, binary threshold, speck size, symbol-match threshold
BILEVEL_LADDER = [
    (1.00, 0.0, 186, 0, 0.85),
    (1.00, 0.0, 186, 4, 0.82),
    (1.00, 0.0, 186, 4, 0.80),
    (0.67, 0.4, 195, 4, 0.85),
    (0.67, 0.5, 200, 6, 0.82),
    (0.50, 0.6, 205, 8, 0.85),
    (0.50, 0.6, 205, 8, 0.82),
    (0.50, 0.6, 205, 8, 0.80),
    (0.50, 0.6, 205, 8, 0.78),
    (0.50, 0.6, 205, 8, 0.76),
]

RASTER_LADDER = [(300, 80), (250, 75), (200, 70), (150, 65), (120, 60),
                 (100, 55), (85, 50), (72, 45)]


@dataclass
class Result:
    ok: bool
    before: int
    profile: object
    size: Optional[int] = None
    dpi: Optional[int] = None
    check: Optional[Tuple[int, Optional[int]]] = None
    best_safe_size: Optional[int] = None
    best_safe_dpi: Optional[int] = None
    reason: Optional[str] = None
    attempts: List[Tuple] = field(default_factory=list)


def prep(arr, scale, blur, bint, speck):
    """Downsample in grayscale, soften, threshold, drop specks.

    Softening before thresholding is counter-intuitive but shrinks the
    file: the symbol coder only reuses a shape it recognises as a repeat,
    and a hard threshold leaves every letter's edge slightly different.
    """
    h, w = arr.shape
    g = Image.fromarray(np.where(arr, 0, 255).astype(np.uint8))
    if scale < 0.999:
        g = g.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BOX)
    if blur > 0:
        g = g.filter(ImageFilter.GaussianBlur(blur))
    out = (np.array(g) < bint).astype(np.uint8)

    if speck > 0 and HAVE_SCIPY:
        ink = out.astype(bool)
        labels, count = ndimage.label(ink, structure=np.ones((3, 3)))
        if count:
            sizes = np.bincount(labels.ravel())
            tiny = np.isin(labels, np.nonzero(sizes < speck)[0]) & ink
            out = (ink & ~tiny).astype(np.uint8)
    return out


def _notify(progress, stage, done=0, total=0):
    if progress:
        progress(stage, done, total)


def _bilevel_rungs(profile, min_dpi):
    for scale, blur, bint, speck, symthr in BILEVEL_LADDER:
        dpi = int(round(profile.dpi * scale))
        if dpi >= min_dpi:
            yield (scale, blur, bint, speck, symthr, dpi)


def _encode_bilevel(source, rung, workdir, dst, pts, progress):
    scale, blur, bint, speck, symthr, dpi = rung
    stage = os.path.join(workdir, "stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    fed, pbms = [], []
    for i, arr in enumerate(source):
        page = prep(arr, scale, blur, bint, speck)
        path = os.path.join(stage, "p-%04d.pbm" % i)
        write_pbm(page, path)
        fed.append(page)
        pbms.append(path)
        _notify(progress, "compress", i + 1, len(source))
    sym, streams = jbig2_encode(pbms, workdir, symthr)
    size = build_jbig2_pdf([f.shape for f in fed], sym, streams, dst, pts)
    return fed, size


def _shrink_bilevel(src, dst, target, profile, min_dpi, progress):
    workdir = tempfile.mkdtemp()
    try:
        source = load_bilevel_pages(src)
        rungs = list(_bilevel_rungs(profile, min_dpi))
        attempts = []

        for rung in rungs:
            fed, size = _encode_bilevel(source, rung, workdir, dst,
                                        profile.page_pts, progress)
            attempts.append((rung[5], rung[4], size))
            if size <= target:
                _notify(progress, "verify", 0, len(source))
                check = verify(fed, dst)
                if is_clean(check):
                    return Result(True, 0, profile, size=size, dpi=rung[5],
                                  check=check, attempts=attempts)
                # Fitting but corrupted is a refusal, not a result.
                break

        # Nothing clean fitted. Find the smallest rung that verifies clean
        # and leave that file in place for the page to offer.
        for rung in reversed(rungs):
            fed, size = _encode_bilevel(source, rung, workdir, dst,
                                        profile.page_pts, progress)
            _notify(progress, "verify", 0, len(source))
            if is_clean(verify(fed, dst)):
                return Result(False, 0, profile, best_safe_size=size,
                              best_safe_dpi=rung[5], reason="too_large",
                              attempts=attempts)
        return Result(False, 0, profile, reason="substitution_risk",
                      attempts=attempts)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _shrink_raster(src, dst, target, profile, min_dpi, progress):
    attempts = []
    usable = [(dpi, q) for dpi, q in RASTER_LADDER
              if dpi >= min_dpi and not (profile.dpi and dpi > profile.dpi)]
    smallest_size, smallest_dpi = None, None
    for dpi, quality in usable:
        _notify(progress, "compress", 0, profile.pages)
        pages = render_jpeg_pages(src, dpi, quality)
        size = build_jpeg_pdf(pages, dst, profile.page_pts)
        attempts.append((dpi, quality, size))
        smallest_size, smallest_dpi = size, dpi
        if size <= target:
            return Result(True, 0, profile, size=size, dpi=dpi, attempts=attempts)
    # The last rung is the smallest; it is already at dst.
    return Result(False, 0, profile, best_safe_size=smallest_size,
                  best_safe_dpi=smallest_dpi, reason="too_large",
                  attempts=attempts)


def _shrink_digital(src, dst, target, profile):
    size = lossless_save(src, dst)
    if size <= target:
        return Result(True, 0, profile, size=size, attempts=[(None, None, size)])
    return Result(False, 0, profile, best_safe_size=size,
                  reason="digital_floor", attempts=[(None, None, size)])


def shrink(src, dst, target, min_dpi=100, progress=None):
    _notify(progress, "inspect")
    profile = inspect(src)
    before = os.path.getsize(src)

    if profile.kind == "digital":
        result = _shrink_digital(src, dst, target, profile)
    elif profile.kind == "bilevel" and have_jbig2():
        result = _shrink_bilevel(src, dst, target, profile, min_dpi, progress)
    else:
        result = _shrink_raster(src, dst, target, profile, min_dpi, progress)

    result.before = before
    return result
