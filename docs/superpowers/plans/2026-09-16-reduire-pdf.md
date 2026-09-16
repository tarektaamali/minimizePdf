# Réduire PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A French-language localhost page that lets a non-technical user shrink a PDF to a size he types, refusing rather than delivering a file whose text may have been corrupted.

**Architecture:** The existing `pdfshrink.py` is reorganised into a package whose I/O layer uses `pypdfium2` and `pikepdf` instead of the Poppler and qpdf command-line tools, which unblocks Windows. Its compression logic — strategy selection, the quality ladder, `prep()` preprocessing, and the substitution check — is preserved. A thin Flask layer serves one page with five states and drives the engine through a progress callback.

**Tech Stack:** Python 3.9+, pikepdf, pypdfium2, Pillow, numpy, scipy, Flask, pytest. `jbig2enc` is an optional external binary. No other external binaries.

**Spec:** `docs/superpowers/specs/2026-09-16-pdf-shrink-web-design.md`

## Global Constraints

- **No subprocess may name `qpdf`, `pdfimages`, `pdftoppm`, or `pdffonts`.** `jbig2enc` (the `jbig2` binary) is the sole permitted external program, and must be optional at runtime. Task 1 adds a test enforcing this; it must stay green.
- Target Python is **3.9** (macOS system Python). Use `typing.Optional`/`List`/`Tuple`, not `X | Y` syntax.
- All user-facing text is **French**. Server APIs return machine-readable reason codes; the French sentences live in the page. Never surface a stack trace.
- Sizes display French style with U+202F narrow no-break space as thousands separator: `1 648 Ko`.
- `SUBSTITUTION_PIXELS = 120` is the substitution threshold, unchanged from the original.
- The original input file is never modified or overwritten.
- The server binds `127.0.0.1` on an ephemeral port. Port 5000 is taken by AirPlay Receiver on macOS.
- Golden numbers for `BA2.pdf` at a 200 Ko target, measured during the feasibility probe: result ≤ 204800 bytes (actual 203788), winning rung 150 dpi with `symthr` 0.78, verification largest clump 84 px on page 85.

---

### Task 1: Project scaffolding, size parsing, portability guard

**Files:**
- Create: `pyproject.toml`
- Create: `pdfshrink/__init__.py`
- Create: `pdfshrink/sizes.py`
- Create: `tests/test_sizes.py`
- Create: `tests/test_portability.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_size(text: str) -> int` (raises `ValueError`), `format_size(n: int) -> str` (always Ko, e.g. `"1 648 Ko"`), `describe_size(n: int) -> str` (largest sensible unit, e.g. `"1,5 Mo"`, `"200 Ko"`).

- [ ] **Step 1: Create the virtual environment and install dependencies**

```bash
cd /Users/macbook/Desktop/Ghassen
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pikepdf pypdfium2 pillow numpy scipy flask pytest
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "pdfshrink"
version = "1.0.0"
requires-python = ">=3.9"
dependencies = [
    "pikepdf", "pypdfium2", "pillow", "numpy", "scipy", "flask",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create the empty package**

```bash
mkdir -p pdfshrink tests
touch pdfshrink/__init__.py
```

- [ ] **Step 4: Write the failing size tests**

Create `tests/test_sizes.py`:

```python
import pytest
from pdfshrink.sizes import parse_size, format_size, describe_size

KO = 1024
MO = 1024 * 1024


@pytest.mark.parametrize("text,expected", [
    ("200", 200 * KO),          # a bare number means Ko
    ("200 Ko", 200 * KO),
    ("200ko", 200 * KO),
    ("200 KB", 200 * KO),
    ("200kb", 200 * KO),
    ("200 K", 200 * KO),
    ("1,5 Mo", int(1.5 * MO)),  # French decimal comma
    ("1.5MB", int(1.5 * MO)),
    ("0,5 mo", int(0.5 * MO)),
    ("  200   ko  ", 200 * KO),
])
def test_parse_accepts(text, expected):
    assert parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "200 Go", "-5 Ko", "0", "Ko", "1,2,3 Ko"])
def test_parse_rejects(text):
    with pytest.raises(ValueError):
        parse_size(text)


def test_format_size_uses_narrow_space():
    assert format_size(1648 * KO) == "1 648 Ko"
    assert format_size(199 * KO) == "199 Ko"


def test_describe_size_picks_unit():
    assert describe_size(200 * KO) == "200 Ko"
    assert describe_size(int(1.5 * MO)) == "1,5 Mo"
    assert describe_size(2 * MO) == "2 Mo"
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sizes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.sizes'`

- [ ] **Step 6: Implement `pdfshrink/sizes.py`**

```python
"""Parse and display file sizes in French or English units."""

import re

KO = 1024
MO = 1024 * 1024

_UNITS = {"": KO, "KO": KO, "KB": KO, "K": KO, "MO": MO, "MB": MO, "M": MO}
_PATTERN = re.compile(r"^(\d+(?:[.,]\d+)?)\s*([A-Z]*)$")


def parse_size(text):
    """Return bytes. A bare number means Ko. Raises ValueError on junk."""
    if not isinstance(text, str):
        raise ValueError("size must be text")
    cleaned = text.strip().upper().replace(" ", "").replace("\xa0", "")
    match = _PATTERN.match(cleaned)
    if not match:
        raise ValueError("cannot read size: %r" % text)
    number, unit = match.groups()
    if unit not in _UNITS:
        raise ValueError("unknown unit: %r" % unit)
    value = int(float(number.replace(",", ".")) * _UNITS[unit])
    if value <= 0:
        raise ValueError("size must be positive")
    return value


def _french_number(value):
    """1648 -> '1 648' with a narrow no-break space; 1.5 -> '1,5'."""
    if isinstance(value, float) and not value.is_integer():
        return ("%.1f" % value).replace(".", ",")
    return "{:,}".format(int(value)).replace(",", " ")


def format_size(n):
    """Always Ko, for showing document sizes: '1 648 Ko'."""
    return "%s Ko" % _french_number(round(n / KO))


def describe_size(n):
    """Largest sensible unit, for echoing what the user typed."""
    if n >= MO:
        return "%s Mo" % _french_number(round(n / MO, 1))
    return "%s Ko" % _french_number(round(n / KO))
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sizes.py -v`
Expected: PASS, 19 tests.

- [ ] **Step 8: Write the portability guard test**

Create `tests/test_portability.py`:

```python
"""The Windows build dies the moment a Poppler or qpdf binary reappears."""

import pathlib

FORBIDDEN = ("qpdf", "pdfimages", "pdftoppm", "pdffonts", "pdftocairo")
PACKAGE = pathlib.Path(__file__).parent.parent / "pdfshrink"


def test_no_unix_binaries_referenced():
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf8")
        for name in FORBIDDEN:
            if '"%s"' % name in text or "'%s'" % name in text:
                offenders.append("%s references %s" % (path.name, name))
    assert not offenders, (
        "These break the Windows build; use pikepdf/pypdfium2 instead:\n"
        + "\n".join(offenders)
    )


def test_jbig2_is_optional():
    """The engine must import and run with no external binary present."""
    from pdfshrink import sizes  # noqa: F401
```

- [ ] **Step 9: Run the guard and confirm it passes on the empty package**

Run: `.venv/bin/pytest tests/test_portability.py -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml pdfshrink/ tests/
git commit -m "feat: size parsing in French units, plus portability guard"
```

---

### Task 2: Document inspection without Poppler

**Files:**
- Create: `pdfshrink/render.py`
- Create: `tests/conftest.py`
- Create: `tests/test_render.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Profile` dataclass with fields `pages: int`, `kind: str` (`"bilevel"`/`"raster"`/`"digital"`), `dpi: Optional[int]`, `page_pts: Tuple[float, float]`, `has_text_layer: bool`; and `inspect(path: str) -> Profile`.

**Note on a deliberate behaviour change.** The original decided "digital" whenever any font existed. OCR'd scans carry an invisible text layer *and* a full-page image, so that rule sends a scan down the lossless path, where it cannot shrink. This task classifies by image geometry first: a document whose every page is one 1-bit image covering at least 90% of the page is bilevel even if fonts exist. `has_text_layer` records that a searchable layer was present, so the page can warn that rasterising drops it.

- [ ] **Step 1: Write the fixtures**

Create `tests/conftest.py`:

```python
import io
import pathlib

import pikepdf
import pytest
from PIL import Image
from pikepdf import Dictionary, Name

ROOT = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="session")
def ba2():
    """The real 101-page bilevel scan used as the golden fixture."""
    path = ROOT / "BA2.pdf"
    if not path.exists():
        pytest.skip("BA2.pdf not present")
    return str(path)


@pytest.fixture
def digital_pdf(tmp_path):
    """Real fonts, no images. Must never be rasterised."""
    pdf = pikepdf.new()
    font = pdf.make_indirect(Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))
    for n in range(3):
        page = pdf.add_blank_page(page_size=(595, 842))
        page.Resources = Dictionary(Font=Dictionary(F1=font))
        page.Contents = pdf.make_stream(
            b"BT /F1 24 Tf 72 700 Td (Bonjour page %d) Tj ET" % n)
    out = tmp_path / "digital.pdf"
    pdf.save(str(out))
    return str(out)


@pytest.fixture
def colour_scan_pdf(tmp_path):
    """Full-page 8-bit colour images, no fonts."""
    pdf = pikepdf.new()
    for n in range(2):
        im = Image.new("RGB", (1240, 1754))
        im.paste((200, 30 + n * 40, 90), (0, 0, 600, 900))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=80)
        stream = pdf.make_stream(buf.getvalue())
        stream.Type = Name.XObject
        stream.Subtype = Name.Image
        stream.Width, stream.Height = im.size
        stream.ColorSpace = Name.DeviceRGB
        stream.BitsPerComponent = 8
        stream.Filter = Name.DCTDecode
        page = pdf.add_blank_page(page_size=(595, 842))
        page.Contents = pdf.make_stream(b"q 595 0 0 842 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    out = tmp_path / "colour.pdf"
    pdf.save(str(out))
    return str(out)
```

- [ ] **Step 2: Write the failing inspection tests**

Create `tests/test_render.py`:

```python
from pdfshrink.render import inspect


def test_inspect_bilevel_scan(ba2):
    p = inspect(ba2)
    assert p.pages == 101
    assert p.kind == "bilevel"
    assert p.dpi == 300
    assert round(p.page_pts[0]) == 595
    assert round(p.page_pts[1]) == 841


def test_inspect_digital(digital_pdf):
    p = inspect(digital_pdf)
    assert p.kind == "digital"
    assert p.pages == 3
    assert p.has_text_layer is True


def test_inspect_colour_scan(colour_scan_pdf):
    p = inspect(colour_scan_pdf)
    assert p.kind == "raster"
    assert p.pages == 2
    assert p.dpi == 150  # 1240 px across 595 pt
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.render'`

- [ ] **Step 4: Implement `inspect` in `pdfshrink/render.py`**

```python
"""Page inspection and rasterisation, built on pikepdf and pypdfium2.

This module exists to keep Poppler out of the project: every fact the
engine needs about a document is obtained through a pip-installable
library, so the same code runs on macOS and Windows.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

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
```

- [ ] **Step 5: Run to verify the tests pass**

Run: `.venv/bin/pytest tests/test_render.py tests/test_portability.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pdfshrink/render.py tests/conftest.py tests/test_render.py
git commit -m "feat: classify documents with pikepdf instead of pdffonts/pdfimages"
```

---

### Task 3: Page extraction and rasterisation

**Files:**
- Modify: `pdfshrink/render.py`
- Modify: `tests/test_render.py`

**Interfaces:**
- Consumes: `Profile`, `inspect` from Task 2.
- Produces:
  - `load_bilevel_pages(path: str) -> List[np.ndarray]` — one `uint8` array per page where `1` means ink, at the embedded image's native resolution. Replaces `pdfimages` + the original `load_ink`.
  - `render_jpeg_pages(path: str, dpi: int, quality: int) -> List[Tuple[bytes, int, int]]` — JPEG bytes plus pixel width and height per page. Replaces `pdftoppm -jpeg`.
  - `decode_pages_ink(path: str, shapes: List[Tuple[int, int]]) -> List[np.ndarray]` — render a produced PDF back to ink arrays at the given `(height, width)` shapes. Used by verification in Task 5, replacing `pdfimages` on the output side.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render.py`:

```python
import numpy as np

from pdfshrink.render import (decode_pages_ink, load_bilevel_pages,
                              render_jpeg_pages)


def test_load_bilevel_pages_shape_and_polarity(ba2):
    pages = load_bilevel_pages(ba2)
    assert len(pages) == 101
    assert pages[0].shape == (3506, 2480)
    assert pages[0].dtype == np.uint8
    ink = pages[0].mean()
    # A page of text is mostly blank, so ink must be the minority.
    assert 0.0 < ink < 0.5


def test_render_jpeg_pages(colour_scan_pdf):
    out = render_jpeg_pages(colour_scan_pdf, dpi=72, quality=60)
    assert len(out) == 2
    data, w, h = out[0]
    assert data[:2] == b"\xff\xd8"      # JPEG SOI marker
    assert (w, h) == (595, 842)


def test_decode_pages_ink_roundtrip(ba2):
    pages = load_bilevel_pages(ba2)[:2]
    shapes = [p.shape for p in pages]
    got = decode_pages_ink(ba2, shapes)
    assert len(got) == 2
    assert got[0].shape == shapes[0]
    # Same document in, same document out: agreement must be near total.
    assert (got[0] == pages[0]).mean() > 0.98
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_render.py -k "bilevel_pages or jpeg_pages or roundtrip" -v`
Expected: FAIL — `ImportError: cannot import name 'load_bilevel_pages'`

- [ ] **Step 3: Implement the three functions**

Append to `pdfshrink/render.py`:

```python
import io

import pypdfium2 as pdfium

INK_THRESHOLD = 128


def _to_ink(image):
    """1 = ink. PIL gives white as True, hence the inversion."""
    return (~np.array(image.convert("1")).astype(bool)).astype(np.uint8)


def load_bilevel_pages(path):
    """Ink arrays at the embedded images' own resolution."""
    out = []
    with pikepdf.open(path) as pdf:
        for page in pdf.pages:
            images = _page_images(page)
            if not images:
                raise ValueError("page without an image in a bilevel document")
            pil = pikepdf.PdfImage(images[0]).as_pil_image()
            out.append(_to_ink(pil))
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
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/render.py tests/test_render.py
git commit -m "feat: extract and rasterise pages via pikepdf and pypdfium2"
```

---

### Task 4: Encoders and PDF assembly

**Files:**
- Create: `pdfshrink/encode.py`
- Create: `tests/test_encode.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `have_jbig2() -> bool`
  - `jbig2_encode(pbm_paths: List[str], workdir: str, symthr: float) -> Tuple[bytes, List[bytes]]`
  - `write_pbm(arr: np.ndarray, path: str) -> None`
  - `build_jbig2_pdf(shapes, sym, streams, dst, pts) -> int` — returns bytes written
  - `build_jpeg_pdf(jpegs: List[Tuple[bytes, int, int]], dst: str, pts) -> int`
  - `lossless_save(src: str, dst: str) -> int` — replaces the `qpdf` invocation

- [ ] **Step 1: Write the failing tests**

Create `tests/test_encode.py`:

```python
import os

import numpy as np
import pikepdf
import pytest

from pdfshrink.encode import (build_jbig2_pdf, build_jpeg_pdf, have_jbig2,
                              jbig2_encode, lossless_save, write_pbm)
from pdfshrink.render import inspect


def test_lossless_save_preserves_text(digital_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    size = lossless_save(digital_pdf, dst)
    assert size == os.path.getsize(dst)
    assert inspect(dst).kind == "digital"
    with pikepdf.open(dst) as pdf:
        assert len(pdf.pages) == 3


def test_build_jpeg_pdf(tmp_path):
    from pdfshrink.render import render_jpeg_pages
    src = str(tmp_path / "src.pdf")
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    pdf.save(src)
    pages = render_jpeg_pages(src, dpi=72, quality=50)
    dst = str(tmp_path / "out.pdf")
    size = build_jpeg_pdf(pages, dst, (595, 842))
    assert size > 0
    with pikepdf.open(dst) as out:
        assert len(out.pages) == 1


@pytest.mark.skipif(not have_jbig2(), reason="jbig2enc not installed")
def test_build_jbig2_pdf(tmp_path):
    arr = np.zeros((200, 150), dtype=np.uint8)
    arr[50:150, 40:110] = 1
    paths = []
    for i in range(2):
        p = str(tmp_path / ("p-%04d.pbm" % i))
        write_pbm(arr, p)
        paths.append(p)
    sym, streams = jbig2_encode(paths, str(tmp_path), 0.85)
    assert sym and len(streams) == 2
    dst = str(tmp_path / "out.pdf")
    size = build_jbig2_pdf([arr.shape, arr.shape], sym, streams, dst, (595, 842))
    assert size > 0
    with pikepdf.open(dst) as out:
        assert len(out.pages) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_encode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.encode'`

- [ ] **Step 3: Implement `pdfshrink/encode.py`**

```python
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


def have_jbig2():
    return shutil.which(JBIG2) is not None


def write_pbm(arr, path):
    Image.fromarray(np.where(arr, 0, 255).astype(np.uint8), "L").convert("1").save(path)


def jbig2_encode(pbm_paths, workdir, symthr):
    """Symbol-code a batch so repeated glyphs are stored once for all pages."""
    d = os.path.join(workdir, "enc")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for p in pbm_paths:
        shutil.copy(p, d)
    names = sorted(os.path.basename(p) for p in pbm_paths)
    subprocess.run([JBIG2, "-s", "-p", "-t", str(symthr)] + names,
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
```

- [ ] **Step 4: Run to verify the tests pass**

Run: `.venv/bin/pytest tests/test_encode.py tests/test_portability.py -v`
Expected: PASS (the JBIG2 test skips if `jbig2enc` is absent).

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/encode.py tests/test_encode.py
git commit -m "feat: JBIG2, JPEG and lossless encoders without qpdf"
```

---

### Task 5: Substitution verification

**Files:**
- Create: `pdfshrink/verify.py`
- Create: `tests/test_verify.py`

**Interfaces:**
- Consumes: `decode_pages_ink` from Task 3.
- Produces: `SUBSTITUTION_PIXELS = 120`; `verify(fed_arrays: List[np.ndarray], dst: str) -> Optional[Tuple[int, Optional[int]]]` returning `(largest_clump_pixels, page_number_1_based)`, `(-1, None)` when the output is unreadable or the page count changed, and `None` when scipy is missing; `is_clean(check) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_verify.py`:

```python
import numpy as np
import pikepdf
import pytest

from pdfshrink.verify import SUBSTITUTION_PIXELS, is_clean, verify


def test_is_clean_thresholds():
    assert is_clean((84, 85)) is True
    assert is_clean((SUBSTITUTION_PIXELS, 3)) is False
    assert is_clean((SUBSTITUTION_PIXELS + 500, 1)) is False
    assert is_clean((-1, None)) is False
    assert is_clean(None) is True      # unverifiable is not the same as dirty


def test_verify_detects_page_count_change(tmp_path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(595, 842))
    dst = str(tmp_path / "one.pdf")
    pdf.save(dst)
    fed = [np.zeros((100, 70), dtype=np.uint8) for _ in range(2)]
    assert verify(fed, dst) == (-1, None)


@pytest.mark.slow
def test_verify_reproduces_golden_clump(ba2, tmp_path):
    """The known-good BA2 run: 84px on page 85, below the threshold."""
    from pdfshrink.core import shrink
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=200 * 1024)
    assert result.ok
    assert result.check == (84, 85)
    assert is_clean(result.check)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_verify.py -v -m "not slow"`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.verify'`

- [ ] **Step 3: Register the `slow` marker**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = ["slow: full-document runs over the 101-page fixture"]
```

- [ ] **Step 4: Implement `pdfshrink/verify.py`**

```python
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
```

- [ ] **Step 5: Run the fast tests**

Run: `.venv/bin/pytest tests/test_verify.py -v -m "not slow"`
Expected: PASS, 2 tests. The golden test stays red until Task 6.

- [ ] **Step 6: Commit**

```bash
git add pdfshrink/verify.py tests/test_verify.py pyproject.toml
git commit -m "feat: substitution check via pypdfium2 instead of pdfimages"
```

---

### Task 6: The engine — ladders, strategy, and best safe size

**Files:**
- Create: `pdfshrink/core.py`
- Create: `tests/test_core.py`

**Interfaces:**
- Consumes: `inspect`, `load_bilevel_pages`, `render_jpeg_pages` (Tasks 2–3); all of `encode` (Task 4); `verify`, `is_clean`, `SUBSTITUTION_PIXELS` (Task 5).
- Produces:
  - `Result` dataclass: `ok: bool`, `size: Optional[int]`, `before: int`, `dpi: Optional[int]`, `profile: Profile`, `check: Optional[Tuple[int, Optional[int]]]`, `best_safe_size: Optional[int]`, `best_safe_dpi: Optional[int]`, `reason: Optional[str]`, `attempts: List[Tuple]`.
  - `shrink(src, dst, target, min_dpi=100, progress=None) -> Result`.
  - `prep(arr, scale, blur, bint, speck) -> np.ndarray`, `BILEVEL_LADDER`, `RASTER_LADDER`.
- `reason` is one of `"digital_floor"`, `"too_large"`, `"substitution_risk"`, or `None` when `ok`.
- **On refusal, `dst` holds the best clean file found**, and `best_safe_size` is its size. The page offers that file rather than paying for a second run.
- `progress(stage, done, total)` is called with `stage` in `{"inspect", "compress", "verify"}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_core.py`:

```python
import os

import pytest

from pdfshrink.core import shrink
from pdfshrink.verify import is_clean


def test_digital_pdf_is_never_rasterised(digital_pdf, tmp_path):
    from pdfshrink.render import inspect
    dst = str(tmp_path / "out.pdf")
    result = shrink(digital_pdf, dst, target=1024 * 1024)
    assert result.ok
    assert inspect(dst).kind == "digital"


def test_digital_pdf_refuses_impossible_target(digital_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(digital_pdf, dst, target=64)
    assert result.ok is False
    assert result.reason == "digital_floor"
    assert result.best_safe_size is not None


def test_colour_scan_uses_raster_ladder(colour_scan_pdf, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(colour_scan_pdf, dst, target=60 * 1024)
    assert result.ok
    assert result.size <= 60 * 1024
    assert result.dpi is not None


def test_progress_callback_reports_stages(colour_scan_pdf, tmp_path):
    seen = []
    shrink(colour_scan_pdf, str(tmp_path / "o.pdf"), target=60 * 1024,
           progress=lambda stage, done, total: seen.append(stage))
    assert "inspect" in seen
    assert "compress" in seen


@pytest.mark.slow
def test_ba2_golden_run(ba2, tmp_path):
    """Matches the measured probe exactly. Guards against regression."""
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=200 * 1024)
    assert result.ok is True
    assert result.size <= 200 * 1024
    assert os.path.getsize(dst) == result.size
    assert result.dpi == 150
    assert result.check == (84, 85)
    assert is_clean(result.check)
    assert result.before == 1687366


@pytest.mark.slow
def test_ba2_impossible_target_offers_best_safe(ba2, tmp_path):
    dst = str(tmp_path / "out.pdf")
    result = shrink(ba2, dst, target=50 * 1024)
    assert result.ok is False
    assert result.reason == "too_large"
    assert result.best_safe_size > 50 * 1024
    assert os.path.getsize(dst) == result.best_safe_size
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_core.py -v -m "not slow"`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.core'`

- [ ] **Step 3: Implement `pdfshrink/core.py`**

```python
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
    profile: Profile
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
    g = Image.fromarray(np.where(arr, 0, 255).astype(np.uint8), "L")
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
            fed, size = _encode_bilevel(source, rung, workdir, dst, profile.page_pts, progress)
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
            fed, size = _encode_bilevel(source, rung, workdir, dst, profile.page_pts, progress)
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
```

- [ ] **Step 4: Run the fast tests**

Run: `.venv/bin/pytest tests/test_core.py -v -m "not slow"`
Expected: PASS, 4 tests.

- [ ] **Step 5: Run the golden tests**

Run: `.venv/bin/pytest tests/ -v -m slow`
Expected: PASS. `test_ba2_golden_run` must report 150 dpi and `(84, 85)`. **If it does not, stop and investigate before continuing** — the probe established these numbers on this exact file.

- [ ] **Step 6: Commit**

```bash
git add pdfshrink/core.py tests/test_core.py
git commit -m "feat: engine with ladders, verification gate and best-safe-size"
```

---

### Task 7: Command-line interface with JSON output

**Files:**
- Create: `pdfshrink/cli.py`
- Create: `tests/test_cli.py`
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: `shrink`, `Result` (Task 6); `parse_size`, `format_size` (Task 1); `is_clean` (Task 5).
- Produces: `main(argv: Optional[List[str]] = None) -> int`; console entry `python -m pdfshrink`.
- JSON shape on stdout with `--json`: `{"ok": bool, "before": int, "size": int|null, "dpi": int|null, "check": [int, int]|null, "best_safe_size": int|null, "reason": str|null, "output": str}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:

```python
import json

from pdfshrink.cli import main


def test_json_output_on_success(digital_pdf, tmp_path, capsys):
    dst = str(tmp_path / "out.pdf")
    code = main([digital_pdf, dst, "--target", "1 Mo", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["output"] == dst


def test_json_output_on_refusal(digital_pdf, tmp_path, capsys):
    dst = str(tmp_path / "out.pdf")
    code = main([digital_pdf, dst, "--target", "64", "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["reason"] == "digital_floor"


def test_bad_target_is_a_clean_error(digital_pdf, tmp_path, capsys):
    code = main([digital_pdf, str(tmp_path / "o.pdf"), "--target", "banane"])
    assert code == 2
    assert "banane" in capsys.readouterr().err


def test_refuses_to_overwrite_input(digital_pdf, capsys):
    code = main([digital_pdf, digital_pdf, "--target", "1 Mo"])
    assert code == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.cli'`

- [ ] **Step 3: Implement `pdfshrink/cli.py`**

```python
"""Command-line entry point. The web layer uses core.shrink directly."""

import argparse
import json
import os
import sys

from .core import shrink
from .sizes import format_size, parse_size
from .verify import is_clean


def _payload(result, output):
    return {
        "ok": result.ok,
        "before": result.before,
        "size": result.size,
        "dpi": result.dpi,
        "check": list(result.check) if result.check else None,
        "best_safe_size": result.best_safe_size,
        "reason": result.reason,
        "output": output,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fit a PDF under a size budget.")
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--target", default="200 Ko", help="e.g. 200 Ko, 1,5 Mo")
    parser.add_argument("--min-dpi", type=int, default=100,
                        help="refuse to go below this resolution (default 100)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        print("no such file: %s" % args.input, file=sys.stderr)
        return 2
    if os.path.abspath(args.input) == os.path.abspath(args.output):
        print("refusing to overwrite the original", file=sys.stderr)
        return 2
    try:
        target = parse_size(args.target)
    except ValueError:
        print("cannot read --target %r; try 200 Ko or 1,5 Mo" % args.target,
              file=sys.stderr)
        return 2

    result = shrink(args.input, args.output, target, args.min_dpi)

    if args.json:
        print(json.dumps(_payload(result, args.output)))
        return 0 if result.ok else 1

    print(os.path.basename(args.input))
    if result.ok:
        pct = 100 - result.size * 100 // result.before
        line = "  %s -> %s  (-%d%%)" % (
            format_size(result.before), format_size(result.size), pct)
        if result.dpi:
            line += "  at %d dpi" % result.dpi
        print(line)
        if result.check:
            print("  verified: no character altered (largest change %dpx)"
                  % result.check[0])
        print("  written: %s" % args.output)
        return 0

    print("  COULD NOT reach %s." % format_size(target))
    if result.reason == "digital_floor":
        print("  This is a digital text PDF; it is already near its floor.")
    elif result.best_safe_size:
        print("  Smallest safe size: %s (already written to %s)"
              % (format_size(result.best_safe_size), args.output))
    else:
        print("  Every setting that fits risks altering a character.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Update SKILL.md's Requirements section**

Replace the `Requirements` section of `SKILL.md` with:

```markdown
## Requirements

```bash
pip install pikepdf pypdfium2 pillow numpy scipy flask
brew install jbig2enc      # macOS, optional but strongly recommended
```

`jbig2enc` is optional. Without it, black-and-white scans fall back to the
JPEG path and compress far worse — measured at roughly 8.4 Ko per page for
CCITT G4 versus about 2 Ko per page for JBIG2. No other external program is
required; Poppler and qpdf are no longer used.
```

- [ ] **Step 6: Commit**

```bash
git add pdfshrink/cli.py tests/test_cli.py SKILL.md
git commit -m "feat: CLI with --json and French size units"
```

---

### Task 8: Flask server

**Files:**
- Create: `pdfshrink/web.py`
- Create: `pdfshrink/output.py`
- Create: `tests/test_web.py`

**Interfaces:**
- Consumes: `shrink` (Task 6), `parse_size`/`describe_size`/`format_size` (Task 1).
- Produces:
  - `output.py`: `output_folder() -> str` (creates `~/Desktop/PDF-réduits`), `unique_path(folder, filename) -> str` (appends ` (2)`, ` (3)` on collision), `reveal(path) -> None` (`open` on macOS, `explorer` on Windows, `xdg-open` otherwise).
  - `web.py`: `create_app() -> Flask`, `serve() -> None` (binds `127.0.0.1` on port 0, prints and opens the URL).
- Routes: `GET /`; `POST /api/size` → `{"ok", "bytes", "label"}`; `POST /api/shrink` (multipart `file`, form `target`) → `{"job": id}`; `GET /api/job/<id>` → `{"state", "stage", "done", "total", ...result fields}`; `GET /api/download/<id>`; `POST /api/keep/<id>` (accept the best safe file); `POST /api/reveal/<id>`.
- Job states: `"working"`, `"done"`, `"refused"`, `"error"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web.py`:

```python
import io
import time

import pytest

from pdfshrink.web import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFSHRINK_OUTPUT", str(tmp_path / "out"))
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _wait(client, job, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get("/api/job/%s" % job).get_json()
        if data["state"] != "working":
            return data
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_page_loads(client):
    body = client.get("/").get_data(as_text=True)
    assert "Glissez votre PDF ici" in body


def test_size_endpoint_accepts_french(client):
    data = client.post("/api/size", json={"text": "1,5 Mo"}).get_json()
    assert data["ok"] is True
    assert data["label"] == "1,5 Mo"


def test_size_endpoint_rejects_junk(client):
    data = client.post("/api/size", json={"text": "banane"}).get_json()
    assert data["ok"] is False


def test_rejects_non_pdf(client):
    upload = {"file": (io.BytesIO(b"not a pdf"), "x.pdf"), "target": "200 Ko"}
    job = client.post("/api/shrink", data=upload,
                      content_type="multipart/form-data").get_json()["job"]
    assert _wait(client, job)["state"] == "error"


def test_successful_shrink_offers_download(client, digital_pdf):
    with open(digital_pdf, "rb") as fh:
        upload = {"file": (io.BytesIO(fh.read()), "doc.pdf"), "target": "1 Mo"}
    job = client.post("/api/shrink", data=upload,
                      content_type="multipart/form-data").get_json()["job"]
    data = _wait(client, job)
    assert data["state"] == "done"
    assert client.get("/api/download/%s" % job).status_code == 200


def test_refusal_has_no_download_until_accepted(client, digital_pdf):
    with open(digital_pdf, "rb") as fh:
        upload = {"file": (io.BytesIO(fh.read()), "doc.pdf"), "target": "64"}
    job = client.post("/api/shrink", data=upload,
                      content_type="multipart/form-data").get_json()["job"]
    data = _wait(client, job)
    assert data["state"] == "refused"
    assert data["reason"] == "digital_floor"
    assert client.get("/api/download/%s" % job).status_code == 409
    assert client.post("/api/keep/%s" % job).status_code == 200
    assert client.get("/api/download/%s" % job).status_code == 200
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_web.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pdfshrink.web'`

- [ ] **Step 3: Implement `pdfshrink/output.py`**

```python
"""Where results are written, and how to show them to the user."""

import os
import subprocess
import sys

FOLDER_NAME = "PDF-réduits"


def output_folder():
    override = os.environ.get("PDFSHRINK_OUTPUT")
    folder = override or os.path.join(os.path.expanduser("~"), "Desktop", FOLDER_NAME)
    os.makedirs(folder, exist_ok=True)
    return folder


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
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    if sys.platform == "darwin":
        subprocess.run(["open", folder], check=False)
    elif os.name == "nt":
        subprocess.run(["explorer", folder], check=False)
    else:
        subprocess.run(["xdg-open", folder], check=False)
```

- [ ] **Step 4: Implement `pdfshrink/web.py`**

```python
"""Flask layer. One page, one job at a time, localhost only.

The API returns machine-readable reason codes; every French sentence lives
in the page, so wording changes never touch the server.
"""

import os
import shutil
import tempfile
import threading
import uuid
import webbrowser

from flask import Flask, abort, jsonify, request, send_file

from .core import shrink
from .output import output_folder, reveal, unique_path
from .sizes import describe_size, parse_size

JOBS = {}
LOCK = threading.Lock()


def _set(job_id, **fields):
    with LOCK:
        JOBS[job_id].update(fields)


def _run(job_id, src, dst, target, original_name):
    def progress(stage, done, total):
        _set(job_id, stage=stage, done=done, total=total)

    try:
        result = shrink(src, dst, target, progress=progress)
    except Exception:
        _set(job_id, state="error", reason="unreadable")
        return
    finally:
        shutil.rmtree(os.path.dirname(src), ignore_errors=True)

    common = {
        "before": result.before,
        "pages": result.profile.pages,
        "kind": result.profile.kind,
        "lost_text_layer": result.profile.has_text_layer
                           and result.profile.kind != "digital",
    }
    if result.ok:
        saved = unique_path(output_folder(), original_name)
        shutil.copyfile(dst, saved)
        _set(job_id, state="done", size=result.size, dpi=result.dpi,
             saved=saved, **common)
    else:
        _set(job_id, state="refused", reason=result.reason,
             best_safe_size=result.best_safe_size,
             best_safe_dpi=result.best_safe_dpi, **common)


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.post("/api/size")
    def api_size():
        text = (request.get_json(silent=True) or {}).get("text", "")
        try:
            value = parse_size(text)
        except ValueError:
            return jsonify({"ok": False})
        return jsonify({"ok": True, "bytes": value, "label": describe_size(value)})

    @app.post("/api/shrink")
    def api_shrink():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            abort(400)
        try:
            target = parse_size(request.form.get("target", "200 Ko"))
        except ValueError:
            abort(400)

        job_id = uuid.uuid4().hex
        workdir = tempfile.mkdtemp()
        src = os.path.join(workdir, "in.pdf")
        upload.save(src)
        dst = os.path.join(tempfile.mkdtemp(), "out.pdf")

        name = os.path.basename(upload.filename)
        with LOCK:
            JOBS[job_id] = {"state": "working", "stage": "inspect",
                            "done": 0, "total": 0, "dst": dst,
                            "name": name, "accepted": False}
        threading.Thread(target=_run, args=(job_id, src, dst, target, name),
                         daemon=True).start()
        return jsonify({"job": job_id})

    @app.get("/api/job/<job_id>")
    def api_job(job_id):
        with LOCK:
            job = JOBS.get(job_id)
            if job is None:
                abort(404)
            return jsonify({k: v for k, v in job.items() if k != "dst"})

    @app.post("/api/keep/<job_id>")
    def api_keep(job_id):
        """Accept the best safe file the engine already produced."""
        with LOCK:
            job = JOBS.get(job_id)
            if job is None or job.get("state") != "refused":
                abort(409)
            job["accepted"] = True
            dst, name = job["dst"], job["name"]
        saved = unique_path(output_folder(), name)
        shutil.copyfile(dst, saved)
        _set(job_id, saved=saved)
        return jsonify({"ok": True, "saved": saved})

    @app.get("/api/download/<job_id>")
    def api_download(job_id):
        with LOCK:
            job = JOBS.get(job_id)
            if job is None:
                abort(404)
            if job["state"] != "done" and not job.get("accepted"):
                abort(409)
            dst, name = job["dst"], job["name"]
        return send_file(dst, as_attachment=True, download_name=name)

    @app.post("/api/reveal/<job_id>")
    def api_reveal(job_id):
        with LOCK:
            job = JOBS.get(job_id)
            if job is None or not job.get("saved"):
                abort(404)
            saved = job["saved"]
        reveal(saved)
        return jsonify({"ok": True})

    return app


def serve():
    import socket
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    url = "http://127.0.0.1:%d/" % port
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print("Réduire PDF : %s" % url)
    create_app().run(host="127.0.0.1", port=port, threaded=True)
```

- [ ] **Step 5: Create a placeholder page so the route tests can run**

```bash
mkdir -p pdfshrink/static
printf '<!doctype html><meta charset="utf-8"><p>Glissez votre PDF ici</p>' \
  > pdfshrink/static/index.html
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_web.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 7: Commit**

```bash
git add pdfshrink/web.py pdfshrink/output.py pdfshrink/static/ tests/test_web.py
git commit -m "feat: Flask server with job progress and refusal gate"
```

---

### Task 9: The page

**Files:**
- Modify: `pdfshrink/static/index.html`
- Create: `pdfshrink/static/style.css`
- Create: `pdfshrink/static/app.js`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes: every route from Task 8.
- Produces: no Python interface. The page owns all French wording.

Design constraints from the spec: five states; large type; one primary action visible at a time; state ④ renders no download control; the success state always shows *« Ouvrez le fichier pour le vérifier avant de l'envoyer. »*

- [ ] **Step 1: Write the failing copy tests**

Append to `tests/test_web.py`:

```python
REQUIRED_FRENCH = [
    "Glissez votre PDF ici",
    "ou cliquez pour choisir un fichier",
    "Taille souhaitée",
    "je ne comprends pas cette taille",
    "Analyse du document",
    "Vérification du texte",
    "Télécharger",
    "Ouvrir le dossier",
    "Ouvrez le fichier pour le vérifier avant de l'envoyer.",
    "Ce fichier ne peut pas descendre",
    "Réduire quand même",
    "Ce fichier n'est pas un PDF valide.",
]


def test_page_contains_all_french_copy(client):
    body = client.get("/").get_data(as_text=True)
    body += client.get("/static/app.js").get_data(as_text=True)
    missing = [s for s in REQUIRED_FRENCH if s not in body]
    assert not missing, "missing French copy: %s" % missing
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_web.py::test_page_contains_all_french_copy -v`
Expected: FAIL listing every missing string.

- [ ] **Step 3: Write `pdfshrink/static/index.html`**

```html
<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Réduire PDF</title>
<link rel="stylesheet" href="/static/style.css">

<main>
  <h1>Réduire un PDF</h1>

  <section id="waiting">
    <div id="drop" tabindex="0" role="button">
      <p class="big">Glissez votre PDF ici</p>
      <p class="small">ou cliquez pour choisir un fichier</p>
    </div>
    <input type="file" id="file" accept="application/pdf" hidden>

    <label for="target">Taille souhaitée</label>
    <input type="text" id="target" value="200 Ko" autocomplete="off">
    <p id="echo" class="small"></p>

    <button id="go" disabled>Réduire</button>
  </section>

  <section id="working" hidden>
    <p class="big" id="working-name"></p>
    <progress id="bar" max="100" value="0"></progress>
    <p class="small" id="working-stage">Analyse du document…</p>
  </section>

  <section id="done" hidden>
    <p class="big result" id="done-sizes"></p>
    <a id="download" class="button" href="#">Télécharger</a>
    <p class="small" id="done-saved"></p>
    <button id="reveal" class="link">Ouvrir le dossier</button>
    <p class="warn" id="done-textlayer" hidden>
      Le texte recherchable a été supprimé.
    </p>
    <p class="small">Ouvrez le fichier pour le vérifier avant de l'envoyer.</p>
    <button id="again" class="link">Réduire un autre fichier</button>
  </section>

  <section id="refused" hidden>
    <p class="big" id="refused-title"></p>
    <p id="refused-why"></p>
    <button id="keep" hidden>Réduire quand même</button>
    <button id="again2" class="link">Réduire un autre fichier</button>
  </section>

  <section id="failed" hidden>
    <p class="big" id="failed-why">Ce fichier n'est pas un PDF valide.</p>
    <button id="again3" class="link">Réduire un autre fichier</button>
  </section>
</main>

<script src="/static/app.js"></script>
</html>
```

- [ ] **Step 4: Write `pdfshrink/static/style.css`**

```css
:root { color-scheme: light; font-family: system-ui, -apple-system, sans-serif; }
body { margin: 0; background: #f6f6f4; color: #1b1b1b; }
main { max-width: 40rem; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
h1 { font-size: 1.6rem; font-weight: 600; }
.big { font-size: 1.35rem; margin: .4rem 0; }
.small { font-size: .95rem; color: #5a5a5a; }
.result { font-size: 2rem; font-weight: 600; color: #1d6f42; }
.warn { color: #8a5b00; }

#drop {
  border: 3px dashed #b8b8b2; border-radius: 14px; padding: 3rem 1.5rem;
  text-align: center; cursor: pointer; background: #fff;
}
#drop:focus-visible, #drop.over { border-color: #1d6f42; background: #f0f8f2; }

label { display: block; margin: 1.5rem 0 .4rem; font-weight: 600; }
input[type=text] {
  font-size: 1.2rem; padding: .6rem .7rem; width: 9rem;
  border: 2px solid #c4c4be; border-radius: 8px; background: #fff;
}
#echo.bad { color: #a11; }

button, .button {
  display: inline-block; margin-top: 1.4rem; padding: .85rem 1.6rem;
  font-size: 1.15rem; font-weight: 600; border: 0; border-radius: 10px;
  background: #1d6f42; color: #fff; cursor: pointer; text-decoration: none;
}
button:disabled { background: #c4c4be; cursor: not-allowed; }
.link {
  background: none; color: #33629c; text-decoration: underline;
  padding: .4rem 0; font-size: 1rem; font-weight: 400;
}
progress { width: 100%; height: 1.1rem; margin: 1rem 0; }
```

- [ ] **Step 5: Write `pdfshrink/static/app.js`**

```javascript
'use strict';

const $ = (id) => document.getElementById(id);
const SECTIONS = ['waiting', 'working', 'done', 'refused', 'failed'];

let chosen = null;
let targetOk = false;
let job = null;

function show(name) {
  SECTIONS.forEach((s) => { $(s).hidden = (s !== name); });
}

function ko(bytes) {
  const value = Math.round(bytes / 1024);
  return value.toLocaleString('fr-FR').replace(/ /g, ' ') + ' Ko';
}

/* ---- choosing a file ---------------------------------------------- */

$('drop').addEventListener('click', () => $('file').click());
$('drop').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); }
});
['dragenter', 'dragover'].forEach((e) =>
  $('drop').addEventListener(e, (ev) => {
    ev.preventDefault(); $('drop').classList.add('over');
  }));
['dragleave', 'drop'].forEach((e) =>
  $('drop').addEventListener(e, () => $('drop').classList.remove('over')));
$('drop').addEventListener('drop', (ev) => {
  ev.preventDefault();
  if (ev.dataTransfer.files.length) { pick(ev.dataTransfer.files[0]); }
});
$('file').addEventListener('change', (ev) => {
  if (ev.target.files.length) { pick(ev.target.files[0]); }
});

function pick(file) {
  chosen = file;
  $('drop').querySelector('.big').textContent = file.name;
  refresh();
}

/* ---- the size box -------------------------------------------------- */

let timer = null;
$('target').addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(checkTarget, 200);
});

async function checkTarget() {
  const response = await fetch('/api/size', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: $('target').value }),
  });
  const data = await response.json();
  targetOk = data.ok;
  $('echo').textContent = data.ok
    ? 'compris : ' + data.label
    : 'je ne comprends pas cette taille';
  $('echo').classList.toggle('bad', !data.ok);
  refresh();
}

function refresh() { $('go').disabled = !(chosen && targetOk); }

/* ---- running ------------------------------------------------------- */

$('go').addEventListener('click', async () => {
  const body = new FormData();
  body.append('file', chosen);
  body.append('target', $('target').value);
  $('working-name').textContent = chosen.name;
  $('bar').value = 0;
  $('working-stage').textContent = 'Analyse du document…';
  show('working');
  const response = await fetch('/api/shrink', { method: 'POST', body });
  job = (await response.json()).job;
  poll();
});

const STAGES = {
  inspect: () => 'Analyse du document…',
  compress: (d, t) => t ? `Compression (page ${d} sur ${t})…` : 'Compression…',
  verify: () => 'Vérification du texte…',
};

async function poll() {
  const data = await (await fetch('/api/job/' + job)).json();
  if (data.state === 'working') {
    const label = STAGES[data.stage] || STAGES.inspect;
    $('working-stage').textContent = label(data.done, data.total);
    if (data.total) { $('bar').value = (data.done / data.total) * 100; }
    setTimeout(poll, 300);
    return;
  }
  if (data.state === 'done') { finish(data); }
  else if (data.state === 'refused') { refuse(data); }
  else { show('failed'); }
}

function finish(data) {
  $('done-sizes').textContent = ko(data.before) + ' → ' + ko(data.size);
  $('download').href = '/api/download/' + job;
  $('done-saved').textContent =
    'Enregistré aussi dans le dossier PDF-réduits';
  $('done-textlayer').hidden = !data.lost_text_layer;
  show('done');
}

function refuse(data) {
  $('refused-title').textContent =
    'Ce fichier ne peut pas descendre à ' + $('target').value.trim()
    + ' sans risque pour le texte.';

  if (data.reason === 'digital_floor') {
    $('refused-why').textContent =
      "C'est un document de texte ; il est déjà à sa taille minimale. "
      + 'Essayez de le couper en deux fichiers.';
    $('keep').hidden = true;
  } else if (data.reason === 'substitution_risk') {
    $('refused-why').textContent =
      'À cette taille, des caractères risquent d’être remplacés. '
      + 'Demandez une taille plus grande.';
    $('keep').hidden = true;
  } else {
    $('refused-why').textContent =
      'C’est un document de ' + data.pages + ' pages ; à cette taille, '
      + 'les caractères deviendraient illisibles.';
    $('keep').textContent = 'Réduire quand même à ' + ko(data.best_safe_size);
    $('keep').hidden = false;
  }
  show('refused');
}

$('keep').addEventListener('click', async () => {
  await fetch('/api/keep/' + job, { method: 'POST' });
  const data = await (await fetch('/api/job/' + job)).json();
  $('done-sizes').textContent =
    ko(data.before) + ' → ' + ko(data.best_safe_size);
  $('download').href = '/api/download/' + job;
  $('done-saved').textContent = 'Enregistré aussi dans le dossier PDF-réduits';
  $('done-textlayer').hidden = !data.lost_text_layer;
  show('done');
});

$('reveal').addEventListener('click', () =>
  fetch('/api/reveal/' + job, { method: 'POST' }));

['again', 'again2', 'again3'].forEach((id) =>
  $(id).addEventListener('click', () => window.location.reload()));

checkTarget();
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/test_web.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 7: Check it by hand**

```bash
.venv/bin/python -c "from pdfshrink.web import serve; serve()"
```

Confirm in the browser: dropping `BA2.pdf` with `200 Ko` reaches the done state showing `1 648 Ko → 199 Ko`; typing `banane` disables the button and shows *« je ne comprends pas cette taille »*; asking for `50 Ko` produces the refusal with a working *« Réduire quand même »* button.

- [ ] **Step 8: Commit**

```bash
git add pdfshrink/static/
git commit -m "feat: French five-state page"
```

---

### Task 10: macOS launcher and first-run setup

**Files:**
- Create: `scripts/setup-mac.sh`
- Create: `scripts/Réduire PDF.command`
- Create: `README.md`
- Create: `tests/test_launcher.py`

**Interfaces:**
- Consumes: `pdfshrink.web.serve` (Task 8).
- Produces: a double-clickable Desktop launcher.

- [ ] **Step 1: Write the failing test**

Create `tests/test_launcher.py`:

```python
import pathlib
import stat

ROOT = pathlib.Path(__file__).parent.parent


def test_launcher_is_executable_and_self_locating():
    launcher = ROOT / "scripts" / "Réduire PDF.command"
    assert launcher.exists()
    assert launcher.stat().st_mode & stat.S_IXUSR
    text = launcher.read_text(encoding="utf8")
    # Double-clicking a .command starts in the user's home, so the script
    # must find its own directory rather than assume the working one.
    assert "BASH_SOURCE" in text
    assert "serve" in text


def test_setup_script_creates_venv_and_installs():
    setup = (ROOT / "scripts" / "setup-mac.sh").read_text(encoding="utf8")
    assert "python3 -m venv" in setup
    for package in ("pikepdf", "pypdfium2", "pillow", "numpy", "scipy", "flask"):
        assert package in setup
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_launcher.py -v`
Expected: FAIL — the files do not exist.

- [ ] **Step 3: Write `scripts/setup-mac.sh`**

```bash
#!/bin/bash
# One-time setup. Run once, then use the Desktop icon.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "Installation de Réduire PDF…"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install pikepdf pypdfium2 pillow numpy scipy flask

# Optional, but black-and-white scans compress far better with it.
if command -v brew >/dev/null 2>&1 && ! command -v jbig2 >/dev/null 2>&1; then
    echo "Installation de jbig2enc (facultatif)…"
    brew install jbig2enc || echo "jbig2enc non installé ; les scans compresseront moins."
fi

cp "scripts/Réduire PDF.command" "$HOME/Desktop/Réduire PDF.command"
chmod +x "$HOME/Desktop/Réduire PDF.command"
echo "Terminé. Double-cliquez sur « Réduire PDF » sur le Bureau."
```

- [ ] **Step 4: Write `scripts/Réduire PDF.command`**

```bash
#!/bin/bash
# Double-clicking opens Terminal in the user's home, so locate the project
# from this script's own path rather than the working directory.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$HERE"
[ -d "$PROJECT/pdfshrink" ] || PROJECT="$HERE/.."
[ -d "$PROJECT/pdfshrink" ] || PROJECT="$HOME/Desktop/Ghassen"

cd "$PROJECT" || { echo "Dossier introuvable."; read -r; exit 1; }

if [ ! -x .venv/bin/python ]; then
    echo "Première utilisation : installation en cours…"
    bash scripts/setup-mac.sh || { echo "Installation échouée."; read -r; exit 1; }
fi

exec .venv/bin/python -c "from pdfshrink.web import serve; serve()"
```

- [ ] **Step 5: Make both executable and install the launcher**

```bash
chmod +x scripts/setup-mac.sh "scripts/Réduire PDF.command"
cp "scripts/Réduire PDF.command" "$HOME/Desktop/Réduire PDF.command"
chmod +x "$HOME/Desktop/Réduire PDF.command"
```

- [ ] **Step 6: Write `README.md`**

```markdown
# Réduire PDF

Compresses a PDF to fit a size limit, and refuses rather than deliver a file
whose text may have been altered.

## Installation (macOS, once)

```bash
bash scripts/setup-mac.sh
```

This creates the virtual environment, installs the dependencies, installs the
optional `jbig2enc`, and puts **Réduire PDF** on the Desktop.

## Use

Double-click **Réduire PDF** on the Desktop. The browser opens by itself. Drop
a PDF, check the size, click *Réduire*. Results are saved in
`~/Desktop/PDF-réduits` and can also be downloaded from the page.

## Command line

```bash
.venv/bin/python -m pdfshrink in.pdf out.pdf --target "200 Ko"
```

## Windows

Not yet delivered. Nothing in the code requires Poppler or qpdf, so the engine
is expected to run, but it is **untested on Windows**. `jbig2enc` has no usable
Windows build, so without it black-and-white scans compress to roughly 8.4 Ko
per page instead of about 2 Ko — documents beyond roughly 24 pages will not
reach 200 Ko and will be refused with an alternative size offered.
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS, everything including the slow golden tests.

- [ ] **Step 8: Verify the launcher by double-clicking it**

Double-click **Réduire PDF** on the Desktop. Expected: a Terminal window opens, the browser opens on the page, and dropping `BA2.pdf` produces `1 648 Ko → 199 Ko`.

- [ ] **Step 9: Commit**

```bash
git add scripts/ README.md tests/test_launcher.py
git commit -m "feat: macOS launcher, setup script and README"
```

---

## Self-review notes

**Spec coverage.** Every spec section maps to a task: engine port (2–6), best-safe-size on failure (6), `--json` (7), French units (1), five states (9), output folder and reveal (8), launcher (10), portability guard (1), golden and strategy tests (5, 6), non-goals honoured — no batch, history, settings, or accounts anywhere.

**Two deliberate deviations from the spec, both flagged for review:**

1. **OCR'd scans.** The spec inherited the original's rule that any font means "digital". Task 2 changes this: a document whose every page is one full-page 1-bit image is bilevel even when an invisible OCR text layer exists, because the original rule would send ordinary OCR'd scans down the lossless path where they cannot shrink. The cost is that the searchable text layer is lost, so Task 8 reports `lost_text_layer` and Task 9 shows *« Le texte recherchable a été supprimé. »*
2. **A fourth refusal reason.** The spec names refusals for size and for the digital floor. Task 6 adds `substitution_risk` for the case where a rung fits the budget but fails verification — the spec requires that file never be offered, but did not name the state.
