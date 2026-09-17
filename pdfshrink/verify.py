"""Detect whether compression replaced a character.

Counting differing pixels is useless: every stroke edge moves slightly on
a perfectly good file. What separates harmless edge softening from a glyph
having been swapped is the size of the single largest connected clump of
changed pixels.
"""

from .render import decode_pages_ink

try:
    import numpy as np
    from scipy import ndimage
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

# A substitution replaces a whole glyph, so changed pixels form one compact
# clump about the size of a character. Edge noise is thin and scattered.
SUBSTITUTION_PIXELS = 120


# TODO(verify-other-paths): only the JBIG2 path is checked. G4 is lossless per
# pixel and JPEG degrades a glyph without replacing it, so neither can produce
# the substitution this clump test looks for - but neither is measured for
# legibility either, and that would be a different instrument, not this one.
def verify(fed_arrays, dst):
    """Return (largest_clump, page) or (-1, None) if unreadable."""
    if not HAVE_SCIPY:
        return None
    try:
        got = decode_pages_ink(dst, [a.shape for a in fed_arrays])
    except Exception:
        return (-1, None)
    if len(got) != len(fed_arrays):
        return (-1, None)

    worst, where = 0, None
    for index, (fed, actual) in enumerate(zip(fed_arrays, got)):
        if actual.shape != fed.shape:
            return (-1, None)
        diff = fed != actual
        if not diff.any():
            continue
        labels, count = ndimage.label(diff, structure=np.ones((3, 3)))
        if not count:
            continue
        largest = int(ndimage.sum(diff, labels, range(1, count + 1)).max())
        if largest > worst:
            worst, where = largest, index + 1
    return (worst, where)


def is_clean(check):
    """No check performed is not the same as a failed check."""
    if check is None:
        return True
    largest, _ = check
    return 0 <= largest < SUBSTITUTION_PIXELS
