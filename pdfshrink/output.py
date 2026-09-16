"""Where results are written, and how to show them to the user.

Locating the Desktop and opening a folder are platform questions, so both
are delegated to platform_paths. A second implementation here would put
the saved file and the Desktop shortcut on different Desktops whenever
OneDrive redirects the folder.
"""

import os

from .platform_paths import OUTPUT_FOLDER, output_dir
from .platform_paths import reveal as _reveal

FOLDER_NAME = OUTPUT_FOLDER


def output_folder():
    """The PDF-réduits folder, or whatever PDFSHRINK_OUTPUT points at."""
    override = os.environ.get("PDFSHRINK_OUTPUT")
    if not override:
        return output_dir()
    if not os.path.isdir(override):
        os.makedirs(override)
    return override


def unique_path(folder, filename):
    """Never replace a file that is already there."""
    stem, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, "%s (%d)%s" % (stem, counter, ext))
        counter += 1
    return candidate


def reveal(path):
    _reveal(path if os.path.isdir(path) else os.path.dirname(path))
