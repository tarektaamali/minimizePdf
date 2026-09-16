"""Fetch the JBIG2 encoder from conda-forge into a folder beside the app.

Without jbig2enc a 101-page scan floors at 585 Ko and a 200 Ko target is
refused; with it the same document reaches 199 Ko. The binary is fetched
rather than redistributed: every package is pinned by exact filename and
MD5, both published by conda-forge, so nothing unaudited is handed on.

jbig2.exe links against leptonica, which pulls a chain of image libraries.
All of them land in one folder because Windows resolves a DLL from the
directory of the executable that needs it.

Run: python scripts/fetch_jbig2.py [destination]
"""

import hashlib
import io
import os
import posixpath
import sys
import tarfile
import urllib.request
import zipfile

CHANNEL = "https://conda.anaconda.org/conda-forge/win-64/"

# Pinned 2026-09-16, every checksum taken from conda-forge's own index.
PACKAGES = [
    ("jbig2enc-0.32-h477610d_0.conda", "1f7e63f5e24f391924ebfe9e36502579"),
    ("leptonica-1.87.0-hb83fb89_1.conda", "5ad7a8e78890b427ae35f43f212ec4cf"),
    ("openjpeg-2.5.4-h90fa87c_2.conda", "d9b2cb1079cf59651722c09aa3a9f840"),
    ("libpng-1.6.58-hdc8cecf_1.conda", "5aa7348e73691187c81d51616f17e48a"),
    ("libzlib-1.3.2-hfd05255_3.conda", "5d2ff29d465097458cc3ff6569151991"),
    ("libtiff-4.7.2-h8f73337_1.conda", "970dbe48f843e7fbd179a9b6c22f865a"),
    ("lerc-4.2.0-hd936e49_0.conda", "add59e2b60ac9d4299d17c938185c75a"),
    ("libdeflate-1.26-h1a1d4e4_0.conda", "43e13c654b8489df50c2cb25f0f39470"),
    ("libjpeg-turbo-3.2.0-hfd05255_1.conda", "fc2c23bacefd1e733f1e1d6cd3b2aaeb"),
    ("liblzma-5.8.3-hfd05255_1.conda", "880a0c8549479b198af21ba5dc49b109"),
    ("zstd-1.5.7-h534d264_7.conda", "e4ac308c39d6d0e131154976da67cf3b"),
    ("libwebp-base-1.6.0-h4d5522a_1.conda", "35a9475e4cc999d52921f57c181979fc"),
    ("giflib-6.1.3-h918f4b6_2.conda", "7beb20b1028c32b4ab0cd9f3fc513a83"),
]

WANTED = "Library/bin/"

# Library/bin also holds cjpeg, fax2ps, the gif tools and leptonica's own
# converters. Only the encoder and the libraries it links against belong
# next to an application a non-technical person runs.
KEEP_EXACT = ("jbig2.exe", "jbig2")
KEEP_SUFFIX = (".dll",)


class ChecksumError(Exception):
    """A package did not match its pinned checksum and was discarded."""


def download(url):
    with urllib.request.urlopen(url) as response:
        return response.read()


def _decompress(data):
    """zstd, from the standard library where it exists and pip where not."""
    try:
        from compression import zstd            # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        import zstandard
        return zstandard.ZstdDecompressor().decompress(data, max_output_size=1 << 28)


def _wanted(leaf):
    return leaf in KEEP_EXACT or leaf.lower().endswith(KEEP_SUFFIX)


def _extract(blob, dest):
    """Take only Library/bin, flattened: the exe and its DLLs, nothing else."""
    taken = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for member in archive.namelist():
            if not (member.startswith("pkg-") and member.endswith(".tar.zst")):
                continue
            raw = _decompress(archive.read(member))
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                for entry in tar.getmembers():
                    name = entry.name.replace("\\", "/").lstrip("./")
                    if not entry.isfile() or not name.startswith(WANTED):
                        continue
                    leaf = posixpath.basename(name)
                    if not leaf or not _wanted(leaf):
                        continue
                    handle = tar.extractfile(entry)
                    if handle is None:
                        continue
                    target = os.path.join(dest, leaf)
                    with open(target, "wb") as out:
                        out.write(handle.read())
                    taken.append(leaf)
    return taken


def fetch(dest, log=print):
    """Download, verify and extract every pinned package into dest."""
    if not os.path.isdir(dest):
        os.makedirs(dest)

    taken = []
    for name, expected in PACKAGES:
        blob = download(CHANNEL + name)
        actual = hashlib.md5(blob).hexdigest()
        if actual != expected:
            raise ChecksumError(
                "%s: expected %s, got %s - refusing to install it"
                % (name, expected, actual))
        taken.extend(_extract(blob, dest))
        log("  %-40s ok" % name)
    return taken


def main():
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jbig2")
    try:
        taken = fetch(dest)
    except ChecksumError as error:
        print("ECHEC : %s" % error)
        return 1
    except Exception as error:                   # noqa: BLE001
        print("ECHEC : %s" % error)
        return 1

    from pdfshrink.encode import _executable
    if not _executable(dest):
        print("ECHEC : jbig2 est introuvable apres l'installation.")
        return 1
    print("OK : %d fichiers dans %s" % (len(taken), dest))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
