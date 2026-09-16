# Windows Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the compression engine work correctly on Windows without `jbig2enc` by adding a CCITT G4 ladder, fix three defects found while verifying it, and ship an installer a non-technical user can run without administrator rights.

**Architecture:** `encode.py` gains a G4 encoder built on Pillow's group 4 TIFF writer, whose single strip is lifted out and embedded as a `CCITTFaxDecode` stream. `core.py` gains a fourth strategy branch that uses it when `jbig2enc` is absent. `render.py` gains the `pypdfium2` fallback the parent design already specified, so a JBIG2-bearing input no longer crashes. A new `platform_paths.py` isolates every Windows/macOS difference behind two functions. Delivery is a zipped folder whose `Installer.bat` fetches `uv`, builds a virtual environment and proves itself before finishing.

**Tech Stack:** Python 3.9-compatible source, run on 3.12 in delivery. pikepdf, pypdfium2, Pillow, numpy, scipy, Flask, pytest. `uv` at install time only. `jbig2enc` remains optional and is not shipped.

**Spec:** `docs/superpowers/specs/2026-09-16-windows-delivery-design.md`

## Global Constraints

- **No subprocess may name `qpdf`, `pdfimages`, `pdftoppm`, `pdffonts`, `pdftocairo` or `jbig2dec`.** `jbig2` is the sole permitted external program and must stay optional at runtime. Task 5 enforces this against dependencies too, not just this project's source.
- **Source targets Python 3.9 syntax.** Use `typing.Optional`/`List`/`Tuple`, never `X | Y`. macOS runs on system Python 3.9; only the Windows delivery pins 3.12.
- `SUBSTITUTION_PIXELS = 120` is unchanged.
- **G4 rungs are never substitution-checked.** G4 cannot substitute a glyph; checking would cause false refusals from resampling noise measured at up to 88 px.
- All user-facing text is **French**. Engine returns machine-readable reason codes only. Never surface a stack trace.
- The original input file is never modified or overwritten.
- Sizes display French style with U+202F narrow no-break space: `1 648 Ko`.

## Sequencing note

Tasks 1–8 are independently testable against the code that exists today. **Task 10 depends on `pdfshrink/web.py`**, which belongs to the parent plan (`2026-09-16-reduire-pdf.md`, Task 8) and does not yet exist. Task 9's installer therefore proves itself against the *engine*; Task 10 adds the launcher and upgrades that proof to an HTTP check, and its tests skip while `web.py` is absent. Do not treat Task 10 as blocked — implement it, and its skipped tests will turn green when the parent plan's Flask task lands.

---

### Task 1: Test fixtures — golden guard and a generated bilevel scan

A file named `BA2.pdf` was present during design, three tests failed, and the cause was neither broken code nor a missing fixture but a *different document* — the 197 Ko JBIG2 output rather than the 1 648 Ko original. A present-but-wrong fixture costs more than a missing one, so it must fail loudly. This task also adds the generated bilevel fixture that Tasks 3–6 need.

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: nothing.
- Produces: pytest fixtures `ba2` (unchanged name, now guarded), `bilevel_pdf` (path to a generated 3-page 1-bit PDF at 150 dpi), and the module-level helper `check_golden(path)` which raises `AssertionError` on a mismatch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixtures.py`:

```python
"""A fixture that is silently the wrong document is worse than a missing one."""

import pytest

from conftest import GOLDEN_BYTES, GOLDEN_PAGES, check_golden


def test_check_golden_rejects_the_wrong_document(digital_pdf):
    with pytest.raises(AssertionError) as caught:
        check_golden(digital_pdf)
    assert "BA2.pdf" in str(caught.value)


def test_golden_constants_match_the_measured_original():
    assert GOLDEN_BYTES == 1687366
    assert GOLDEN_PAGES == 101


def test_bilevel_fixture_is_seen_as_bilevel(bilevel_pdf):
    from pdfshrink.render import inspect
    profile = inspect(bilevel_pdf)
    assert profile.kind == "bilevel"
    assert profile.pages == 3
    assert profile.dpi == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fixtures.py -v`
Expected: FAIL with `ImportError: cannot import name 'GOLDEN_BYTES' from 'conftest'`

- [ ] **Step 3: Add the guard and the bilevel fixture to conftest**

Add to `tests/conftest.py`, after the existing imports:

```python
GOLDEN_BYTES = 1687366
GOLDEN_PAGES = 101


def check_golden(path):
    """Fail loudly when a present BA2.pdf is not the measured original."""
    path = pathlib.Path(path)
    size = path.stat().st_size
    assert abs(size - GOLDEN_BYTES) <= GOLDEN_BYTES * 0.05, (
        "BA2.pdf is present but is not the golden original: %d bytes, "
        "expected about %d. The 197 Ko file is this tool's OUTPUT, not its "
        "input. Remove it or replace it with the 1648 Ko, 300 dpi scan."
        % (size, GOLDEN_BYTES))
    with pikepdf.open(str(path)) as pdf:
        pages = len(pdf.pages)
    assert pages == GOLDEN_PAGES, (
        "BA2.pdf is present but has %d pages, expected %d; this is not the "
        "golden original." % (pages, GOLDEN_PAGES))
```

Replace the existing `ba2` fixture body with:

```python
@pytest.fixture(scope="session")
def ba2():
    """The real 101-page bilevel scan used as the golden fixture."""
    path = ROOT / "BA2.pdf"
    if not path.exists():
        pytest.skip("BA2.pdf not present")
    check_golden(path)
    return str(path)
```

Append the generated bilevel fixture:

```python
@pytest.fixture
def bilevel_pdf(tmp_path):
    """Three 1-bit full-page images at 150 dpi, uncompressed.

    Uncompressed rather than G4 so it does not depend on the encoder it is
    used to test, and so pikepdf can extract it without any external binary.
    """
    import numpy as np

    w, h = 1240, 1754                      # 150 dpi A4, width divisible by 8
    pdf = pikepdf.new()
    for n in range(3):
        ink = np.zeros((h, w), dtype=bool)
        for row in range(120, h - 120, 46):
            ink[row:row + 14, 100:w - 100 - (n * 60)] = True
            ink[row:row + 14, 300::97] = False
        packed = np.packbits(~ink, axis=1).tobytes()   # 0 = black
        stream = pdf.make_stream(packed)
        stream.Type = Name.XObject
        stream.Subtype = Name.Image
        stream.Width, stream.Height = w, h
        stream.ColorSpace = Name.DeviceGray
        stream.BitsPerComponent = 1
        page = pdf.add_blank_page(page_size=(595.2, 841.44))
        page.Contents = pdf.make_stream(b"q 595.2 0 0 841.44 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    out = tmp_path / "bilevel.pdf"
    pdf.save(str(out))
    return str(out)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fixtures.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the whole suite to confirm nothing regressed**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: the 5 known failures remain; no new ones. If `BA2.pdf` is the 197 Ko output, the three `ba2` tests now fail with the explicit "this is the OUTPUT" message instead of a confusing assertion — that is the intended behaviour.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_fixtures.py
git commit -m "test: guard the golden fixture and add a generated bilevel scan"
```

---

### Task 2: The CCITT G4 encoder

Pillow writes group 4 TIFF; the single strip is lifted out and embedded as a `CCITTFaxDecode` stream. Two details are load-bearing and both were found the hard way: **the TIFF must be one strip**, because taking only `StripOffsets[0]` of a multi-strip image produces a smaller, entirely plausible, corrupt file; and **`BlackIs1` must be true**, because Pillow codes black as 1.

**Files:**
- Modify: `pdfshrink/encode.py`
- Test: `tests/test_encode.py`

**Interfaces:**
- Consumes: `tests/conftest.py::bilevel_pdf` from Task 1.
- Produces: `g4_encode(arr) -> bytes` taking a `1 = ink` `uint8` array; `build_g4_pdf(pages, dst, pts) -> int` where `pages` is a list of `(g4_bytes, width, height)` and the return is the written file's size in bytes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_encode.py`:

```python
def test_g4_encode_handles_a_tall_page_as_one_strip():
    """Pillow splits tall images into strips by default; a partial strip
    yields a smaller, plausible, corrupt file, so this must not happen."""
    from pdfshrink.encode import g4_encode
    arr = np.zeros((4000, 1240), dtype=np.uint8)
    arr[100:3900, 100:1100] = 1
    data = g4_encode(arr)
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_build_g4_pdf_roundtrips_with_correct_polarity(tmp_path):
    """A BlackIs1 regression shows up as near-total ink inversion."""
    import pypdfium2 as pdfium

    from pdfshrink.encode import build_g4_pdf, g4_encode

    h, w = 800, 624
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[100:140, 80:540] = 1
    arr[300:700, 200:240] = 1
    expected = float(arr.mean())

    dst = str(tmp_path / "g4.pdf")
    size = build_g4_pdf([(g4_encode(arr), w, h)], dst, (595.2, 841.44))
    assert size == os.path.getsize(dst)

    doc = pdfium.PdfDocument(dst)
    pil = doc[0].render(scale=w / doc[0].get_width(), grayscale=True).to_pil()
    doc.close()
    got = float((np.array(pil.convert("L")) < 128).mean())
    assert abs(got - expected) < 0.02, (
        "ink fraction %.4f vs expected %.4f - check BlackIs1" % (got, expected))


def test_build_g4_pdf_is_recognised_as_bilevel(tmp_path):
    from pdfshrink.encode import build_g4_pdf, g4_encode

    h, w = 1754, 1240
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[200:1500, 150:1100] = 1
    dst = str(tmp_path / "g4.pdf")
    build_g4_pdf([(g4_encode(arr), w, h)], dst, (595.2, 841.44))
    profile = inspect(dst)
    assert profile.kind == "bilevel"
    assert profile.dpi == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_encode.py -k g4 -v`
Expected: FAIL with `ImportError: cannot import name 'g4_encode'`

- [ ] **Step 3: Implement the encoder**

In `pdfshrink/encode.py`, extend the imports:

```python
import io
import os
import shutil
import subprocess

import numpy as np
import pikepdf
from PIL import Image, TiffImagePlugin
from pikepdf import Dictionary, Name
```

Add below the `JBIG2` constant:

```python
# Pillow splits a TIFF into strips once it exceeds this many bytes. A PDF
# CCITTFaxDecode stream must be one continuous G4 stream for the whole
# image, so strips are disabled outright: a partial strip decodes into a
# smaller file that looks entirely plausible and is silently corrupt.
TiffImagePlugin.STRIP_SIZE = 2 ** 28
```

Add the two functions after `write_pbm`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_encode.py -v`
Expected: all pass (the `jbig2enc` test still skips)

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/encode.py tests/test_encode.py
git commit -m "feat: CCITT G4 encoder without an external binary"
```

---

### Task 3: The G4 ladder and strategy routing

Without this, a bilevel document on a machine lacking `jbig2enc` falls to the JPEG path and floors at 3 827 Ko — measured. G4 is tried **only when `jbig2enc` is absent**, never as a fallback after the JBIG2 ladder, because JBIG2 beats G4 at every resolution (293 Ko against 845 Ko at 150 dpi) and so a G4 rung cannot rescue a target JBIG2 already missed.

**Files:**
- Modify: `pdfshrink/core.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `g4_encode`, `build_g4_pdf` from Task 2; `bilevel_pdf` from Task 1.
- Produces: `G4_LADDER`, `_g4_rungs(profile, min_dpi)`, `_shrink_bilevel_g4(src, dst, target, profile, min_dpi, progress) -> Result`. `Result.attempts` entries for this path are `(dpi, None, size)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core.py`:

```python
def test_bilevel_without_jbig2_uses_g4_not_jpeg(bilevel_pdf, tmp_path,
                                                monkeypatch):
    """The JPEG path floors around 3827 Ko for a scan; G4 must be used."""
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=200 * 1024)
    assert result.ok is True
    assert result.size <= 200 * 1024

    with __import__("pikepdf").open(dst) as pdf:
        image = pdf.pages[0]["/Resources"]["/XObject"]["/Im0"]
        assert str(image.Filter) == "/CCITTFaxDecode"


def test_g4_sizes_decrease_as_dpi_decreases(bilevel_pdf, tmp_path,
                                            monkeypatch):
    """An inverted size trend is the first sign of a broken encoder."""
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=1, min_dpi=50)
    sizes = [size for _, _, size in result.attempts]
    assert len(sizes) >= 3
    assert sizes == sorted(sizes, reverse=True), sizes


def test_g4_refuses_an_impossible_target(bilevel_pdf, tmp_path, monkeypatch):
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    dst = str(tmp_path / "out.pdf")
    result = core.shrink(bilevel_pdf, dst, target=1, min_dpi=50)
    assert result.ok is False
    assert result.reason == "too_large"
    assert result.best_safe_size == os.path.getsize(dst)


def test_g4_never_runs_the_substitution_check(bilevel_pdf, tmp_path,
                                              monkeypatch):
    """G4 cannot substitute a glyph; checking would cause false refusals."""
    import pdfshrink.core as core
    called = []
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    monkeypatch.setattr(core, "verify",
                        lambda *a, **k: called.append(a) or (0, None))
    core.shrink(bilevel_pdf, str(tmp_path / "out.pdf"), target=200 * 1024)
    assert called == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core.py -k g4 -v`
Expected: FAIL — the first test fails on `str(image.Filter) == "/DCTDecode"`

- [ ] **Step 3: Implement the ladder**

In `pdfshrink/core.py`, extend the encode import:

```python
from .encode import (build_g4_pdf, build_jbig2_pdf, build_jpeg_pdf,
                     g4_encode, have_jbig2, jbig2_encode, lossless_save,
                     write_pbm)
```

Add the ladder below `RASTER_LADDER`:

```python
# scale, blur, binary threshold, speck size. No symbol-match threshold:
# G4 has no lossy parameter to tune, so only resolution varies. Scales
# mirror BILEVEL_LADDER and reach 300/200/150/120/100 dpi from a 300 dpi
# source, the resolutions measured in the design.
G4_LADDER = [
    (1.00, 0.0, 186, 0),
    (1.00, 0.0, 186, 4),
    (0.67, 0.4, 195, 4),
    (0.50, 0.6, 205, 8),
    (0.40, 0.6, 205, 8),
    (0.34, 0.6, 205, 8),
]
```

Add the three functions after `_shrink_bilevel`:

```python
def _g4_rungs(profile, min_dpi):
    for scale, blur, bint, speck in G4_LADDER:
        dpi = int(round(profile.dpi * scale))
        if dpi >= min_dpi:
            yield (scale, blur, bint, speck, dpi)


def _encode_g4(source, rung, dst, pts, progress):
    scale, blur, bint, speck, dpi = rung
    pages = []
    for i, arr in enumerate(source):
        page = prep(arr, scale, blur, bint, speck)
        h, w = page.shape
        pages.append((g4_encode(page), w, h))
        _notify(progress, "compress", i + 1, len(source))
    return build_g4_pdf(pages, dst, pts)


def _shrink_bilevel_g4(src, dst, target, profile, min_dpi, progress):
    """Bilevel without jbig2enc. No substitution check: G4 stores the exact
    bitmap it is handed and cannot swap one glyph for another."""
    source = load_bilevel_pages(src)
    rungs = list(_g4_rungs(profile, min_dpi))
    if not rungs:
        return Result(False, 0, profile, reason="already_minimal", attempts=[])

    attempts = []
    size = None
    for rung in rungs:
        size = _encode_g4(source, rung, dst, profile.page_pts, progress)
        attempts.append((rung[4], None, size))
        if size <= target:
            return Result(True, 0, profile, size=size, dpi=rung[4],
                          attempts=attempts)
    # The last rung is the smallest and is already at dst.
    return Result(False, 0, profile, best_safe_size=size,
                  best_safe_dpi=rungs[-1][4], reason="too_large",
                  attempts=attempts)
```

Replace the strategy block in `shrink`:

```python
    if profile.kind == "digital":
        result = _shrink_digital(src, dst, target, profile)
    elif profile.kind == "bilevel" and have_jbig2():
        result = _shrink_bilevel(src, dst, target, profile, min_dpi, progress)
    elif profile.kind == "bilevel":
        result = _shrink_bilevel_g4(src, dst, target, profile, min_dpi,
                                    progress)
    else:
        result = _shrink_raster(src, dst, target, profile, min_dpi, progress)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core.py -v`
Expected: the four new tests pass; the two `ba2` tests still skip or fail on the fixture as before

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/core.py tests/test_core.py
git commit -m "feat: CCITT G4 ladder for bilevel documents without jbig2enc"
```

---

### Task 4: The jbig2dec fallback

`pikepdf.PdfImage(...).as_pil_image()` spawns **`jbig2dec`** when the embedded image is JBIG2 and raises `DependencyError` when it is absent. The ordinary trigger is the user re-shrinking a file he already shrank, and state ⑤ forbids showing him a stack trace. `pypdfium2` decodes JBIG2 itself, so it is the fallback — exactly as the parent design specified and never implemented.

**Files:**
- Create: `scripts/make_jbig2_fixture.py`
- Create: `tests/fixtures/jbig2_min.pdf` (generated by that script, committed)
- Modify: `pdfshrink/render.py:81-91`
- Modify: `tests/conftest.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: pytest fixture `jbig2_pdf` returning the path to the committed minimal JBIG2 PDF; `load_bilevel_pages` keeps its signature and return type.

- [ ] **Step 1: Write the fixture generator**

Create `scripts/make_jbig2_fixture.py`. This is the reproducible source of a committed binary fixture; the output is 917 bytes and was verified to render at ~11 % ink under `pypdfium2` while raising `DependencyError` in pikepdf.

```python
"""Build tests/fixtures/jbig2_min.pdf.

A minimal JBIG2 PDF, coded with MMR (T.6) so no arithmetic coder is needed.
The bitmap is inverted before encoding because JBIG2's MMR convention runs
opposite to what Pillow emits.

Run: python scripts/make_jbig2_fixture.py
"""

import io
import pathlib
import struct

import pikepdf
from PIL import Image, TiffImagePlugin
from pikepdf import Dictionary, Name

TiffImagePlugin.STRIP_SIZE = 2 ** 28
W = H = 64
OUT = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "jbig2_min.pdf"


def mmr_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format="TIFF", compression="group4")
    tif = Image.open(io.BytesIO(buf.getvalue()))
    offsets, counts = tif.tag_v2[273], tif.tag_v2[279]
    assert len(offsets) == 1, "expected one strip, got %d" % len(offsets)
    return buf.getvalue()[offsets[0]:offsets[0] + counts[0]]


def segment(number, seg_type, page, data):
    head = struct.pack(">I", number)
    head += struct.pack(">B", seg_type & 0x3F)   # bit 6 clear: 1-byte page
    head += b"\x00"                              # no referred-to segments
    head += struct.pack(">B", page)
    head += struct.pack(">I", len(data))
    return head + data


def main():
    image = Image.new("1", (W, H), 0)
    for y in range(12, 52):
        for x in range(12, 52):
            if 18 <= x <= 22 or 18 <= y <= 22 or (x + y) % 17 == 0:
                image.putpixel((x, y), 1)
    mmr = mmr_bytes(image)

    page_info = struct.pack(">IIIIBH", W, H, 0, 0, 0x01, 0)   # 19 bytes
    region_info = struct.pack(">IIIIB", W, H, 0, 0, 0)        # 17 bytes
    generic = region_info + b"\x01" + mmr                     # MMR = 1
    stream = segment(0, 48, 1, page_info) + segment(1, 39, 1, generic)

    pdf = pikepdf.new()
    img = pdf.make_stream(stream)
    img.Type, img.Subtype = Name.XObject, Name.Image
    img.Width, img.Height = W, H
    img.ColorSpace, img.BitsPerComponent = Name.DeviceGray, 1
    img.Filter = Name.JBIG2Decode
    page = pdf.add_blank_page(page_size=(72, 72))
    page.Contents = pdf.make_stream(b"q 72 0 0 72 0 0 cm /Im0 Do Q")
    page.Resources = Dictionary(XObject=Dictionary(Im0=img))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(OUT))
    print("written:", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixture and confirm it behaves as required**

```bash
.venv/Scripts/python.exe scripts/make_jbig2_fixture.py
```

Expected: `written: ... 917 bytes` (a few bytes either way is fine).

Confirm both properties:

```bash
.venv/Scripts/python.exe -c "
import numpy as np, pikepdf, pypdfium2 as pdfium
p = 'tests/fixtures/jbig2_min.pdf'
d = pdfium.PdfDocument(p)
a = np.array(d[0].render(scale=2).to_pil().convert('L'))
d.close()
print('ink fraction :', round(float((a < 128).mean()), 3))
with pikepdf.open(p) as pdf:
    xo = pdf.pages[0]['/Resources']['/XObject']['/Im0']
    print('filter       :', xo.Filter)
    try:
        pikepdf.PdfImage(xo).as_pil_image()
        print('pikepdf      : SUCCEEDED - jbig2dec is installed here')
    except Exception as e:
        print('pikepdf      :', type(e).__name__)
"
```

Expected: ink fraction around `0.11`, filter `/JBIG2Decode`, and `pikepdf : DependencyError`. If pikepdf succeeds, `jbig2dec` is installed on this machine and Task 4's fallback test will pass without exercising the fallback — uninstall it or trust Task 5's subprocess guard, which fails either way.

- [ ] **Step 3: Add the fixture to conftest and write the failing test**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def jbig2_pdf():
    """A minimal JBIG2 PDF. pikepdf cannot decode it without jbig2dec."""
    path = ROOT / "tests" / "fixtures" / "jbig2_min.pdf"
    if not path.exists():
        pytest.skip("run scripts/make_jbig2_fixture.py")
    return str(path)
```

Append to `tests/test_render.py`:

```python
def test_load_bilevel_pages_falls_back_when_jbig2dec_is_missing(jbig2_pdf):
    """Re-shrinking an already shrunk file must not raise DependencyError."""
    pages = load_bilevel_pages(jbig2_pdf)
    assert len(pages) == 1
    assert pages[0].shape == (64, 64)
    assert pages[0].dtype == np.uint8
    ink = float(pages[0].mean())
    assert 0.02 < ink < 0.4, ink


def test_load_bilevel_pages_still_uses_pikepdf_when_it_can(bilevel_pdf):
    pages = load_bilevel_pages(bilevel_pdf)
    assert len(pages) == 3
    assert pages[0].shape == (1754, 1240)
    assert 0.0 < float(pages[0].mean()) < 0.5
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -k fall -v`
Expected: FAIL with `pikepdf._exceptions.DependencyError: jbig2dec - not installed or not found`

- [ ] **Step 5: Implement the fallback**

Replace `load_bilevel_pages` in `pdfshrink/render.py`:

```python
def load_bilevel_pages(path):
    """Ink arrays at the embedded images' own resolution.

    pikepdf extracts the stored image directly, which is exact and cheap,
    but it shells out to jbig2dec for JBIG2 streams. That binary is not
    shipped, so any page it cannot decode is rendered with pypdfium2
    instead, which decodes JBIG2 itself.
    """
    out, deferred = [], []
    with pikepdf.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            images = _page_images(page)
            if not images:
                raise ValueError("page without an image in a bilevel document")
            image = images[0]
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_render.py -v`
Expected: the two new tests pass

- [ ] **Step 7: Commit**

```bash
git add scripts/make_jbig2_fixture.py tests/fixtures/jbig2_min.pdf \
        pdfshrink/render.py tests/conftest.py tests/test_render.py
git commit -m "fix: fall back to pypdfium2 when jbig2dec is absent"
```

---

### Task 5: A portability guard that sees through dependencies

The current guard greps this project's own source, which is why a `jbig2dec` subprocess *inside pikepdf* passed it green for the entire life of the project. The replacement watches `subprocess.Popen` during a real decode and fails on anything forbidden, whoever spawned it.

**Files:**
- Modify: `tests/test_portability.py`

**Interfaces:**
- Consumes: `jbig2_pdf` from Task 4, `bilevel_pdf` from Task 1.
- Produces: nothing importable.

- [ ] **Step 1: Write the failing test**

Replace the whole of `tests/test_portability.py`:

```python
"""The Windows build dies the moment a Poppler or qpdf binary reappears.

Grepping this project's source is not enough: jbig2dec is spawned from
inside pikepdf, which is how it went unnoticed until the engine was first
run on Windows. These tests watch what is actually executed.
"""

import os
import pathlib
import subprocess

FORBIDDEN = ("qpdf", "pdfimages", "pdftoppm", "pdffonts", "pdftocairo",
             "jbig2dec")
PERMITTED = ("jbig2",)
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


def _spy_on_subprocess(monkeypatch):
    seen = []
    original = subprocess.Popen.__init__

    def record(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        if argv:
            seen.append(os.path.basename(str(argv[0])).lower())
        return original(self, args, *rest, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", record)
    return seen


def _forbidden(seen):
    bad = []
    for name in seen:
        stem = name[:-4] if name.endswith(".exe") else name
        if stem in FORBIDDEN:
            bad.append(name)
    return bad


def test_decoding_jbig2_spawns_nothing_forbidden(jbig2_pdf, monkeypatch):
    """This is the case that slipped through: pikepdf spawning jbig2dec."""
    from pdfshrink.render import load_bilevel_pages
    seen = _spy_on_subprocess(monkeypatch)
    load_bilevel_pages(jbig2_pdf)
    assert not _forbidden(seen), "spawned: %s" % seen


def test_a_full_shrink_spawns_nothing_forbidden(bilevel_pdf, tmp_path,
                                                monkeypatch):
    import pdfshrink.core as core
    monkeypatch.setattr(core, "have_jbig2", lambda: False)
    seen = _spy_on_subprocess(monkeypatch)
    core.shrink(bilevel_pdf, str(tmp_path / "out.pdf"), target=200 * 1024)
    assert not _forbidden(seen), "spawned: %s" % seen
    for name in seen:
        stem = name[:-4] if name.endswith(".exe") else name
        assert stem in PERMITTED, "unexpected external program: %s" % name
```

- [ ] **Step 2: Run to verify the new tests pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_portability.py -v`
Expected: 5 passed. If `test_decoding_jbig2_spawns_nothing_forbidden` fails, Task 4's fallback is not working — fix that, not this test.

- [ ] **Step 3: Prove the guard actually catches a regression**

Temporarily revert the fallback by editing `pdfshrink/render.py` to remove the `try`/`except` around `as_pil_image()`, then:

Run: `.venv/Scripts/python.exe -m pytest tests/test_portability.py -k jbig2_spawns -v`
Expected: FAIL — either on `DependencyError` or listing `jbig2dec` in `spawned:`. Restore the fallback and confirm it passes again. A guard never observed failing is not a guard.

- [ ] **Step 4: Commit**

```bash
git add tests/test_portability.py
git commit -m "test: portability guard watches subprocesses, not source text"
```

---

### Task 6: Never offer a result larger than the input

Measured: `best_safe_size` reported 3 827 Ko for a 197 Ko input, so state ④ would have offered *« Réduire quand même à 3 827 Ko »* — proposing to make his file twenty times bigger. The rule applies to `too_large` only; `digital_floor` already means "at its floor" and the page never renders a button for it.

**Files:**
- Modify: `pdfshrink/core.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Consumes: `Result` from `core.py`.
- Produces: `MIN_SAVING = 0.10`, `_offerable(best_safe_size, before) -> bool`. New reason code `already_minimal`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_core.py`:

```python
def test_offerable_rejects_a_result_that_is_not_smaller():
    from pdfshrink.core import _offerable
    assert _offerable(100 * 1024, 200 * 1024) is True
    assert _offerable(3918342, 197231) is False     # the measured defect
    assert _offerable(190 * 1024, 200 * 1024) is False   # only 5% saved
    assert _offerable(None, 200 * 1024) is False
    assert _offerable(100 * 1024, 0) is False


def test_refusal_withholds_a_useless_fallback_size(colour_scan_pdf, tmp_path,
                                                   monkeypatch):
    """A refusal that offers a bigger file is worse than a plain refusal."""
    import pdfshrink.core as core
    from pdfshrink.core import Result

    def huge(src, dst, target, profile, min_dpi, progress):
        return Result(False, 0, profile, best_safe_size=3918342,
                      best_safe_dpi=100, reason="too_large",
                      attempts=[(100, 55, 3918342)])

    monkeypatch.setattr(core, "_shrink_raster", huge)
    result = core.shrink(colour_scan_pdf, str(tmp_path / "o.pdf"), target=1024)
    assert result.ok is False
    assert result.reason == "already_minimal"
    assert result.best_safe_size is None
    assert result.best_safe_dpi is None


def test_refusal_keeps_a_genuinely_useful_fallback_size(colour_scan_pdf,
                                                        tmp_path, monkeypatch):
    import pdfshrink.core as core
    from pdfshrink.core import Result

    before = os.path.getsize(colour_scan_pdf)

    def helpful(src, dst, target, profile, min_dpi, progress):
        return Result(False, 0, profile, best_safe_size=int(before * 0.5),
                      best_safe_dpi=100, reason="too_large", attempts=[])

    monkeypatch.setattr(core, "_shrink_raster", helpful)
    result = core.shrink(colour_scan_pdf, str(tmp_path / "o.pdf"), target=1024)
    assert result.reason == "too_large"
    assert result.best_safe_size == int(before * 0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core.py -k "offerable or fallback" -v`
Expected: FAIL with `ImportError: cannot import name '_offerable'`

- [ ] **Step 3: Implement the rule**

Add below `RASTER_LADDER` in `pdfshrink/core.py`:

```python
# A fallback size is only worth offering if it is meaningfully smaller than
# what he already has. Without this, a raster floor above the input size is
# offered as an improvement.
MIN_SAVING = 0.10
```

Add before `shrink`:

```python
def _offerable(best_safe_size, before):
    """Is this fallback size worth showing him at all?"""
    if best_safe_size is None or before <= 0:
        return False
    return best_safe_size <= before * (1.0 - MIN_SAVING)
```

Replace the tail of `shrink`:

```python
    result.before = before
    if (not result.ok and result.reason == "too_large"
            and not _offerable(result.best_safe_size, before)):
        result.best_safe_size = None
        result.best_safe_dpi = None
        result.reason = "already_minimal"
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_core.py -v`
Expected: all pass except the `ba2` tests, which skip or fail on the fixture

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/core.py tests/test_core.py
git commit -m "fix: never offer a fallback size that is not meaningfully smaller"
```

---

### Task 7: Platform paths

Every Windows/macOS difference lives here and nowhere else, which is what keeps macOS working as a property rather than an intention. Windows resolves Desktop through the shell known folder because OneDrive redirection makes `~/Desktop` wrong on managed machines, and `reveal()` ignores `explorer.exe`'s exit code, which is `1` even on success.

**Files:**
- Create: `pdfshrink/platform_paths.py`
- Test: `tests/test_platform_paths.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `desktop_dir() -> str`, `reveal(path) -> None` (never raises), `output_dir() -> str` returning the `PDF-réduits` folder path, created if absent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_platform_paths.py`:

```python
import os
import subprocess
import sys

import pytest

from pdfshrink import platform_paths


def test_desktop_dir_exists():
    path = platform_paths.desktop_dir()
    assert isinstance(path, str)
    assert os.path.isdir(path), path


def test_output_dir_is_created_and_named_in_french(tmp_path, monkeypatch):
    monkeypatch.setattr(platform_paths, "desktop_dir", lambda: str(tmp_path))
    created = platform_paths.output_dir()
    assert os.path.basename(created) == "PDF-réduits"
    assert os.path.isdir(created)
    assert platform_paths.output_dir() == created      # idempotent


def test_reveal_never_raises_on_a_missing_path():
    platform_paths.reveal(os.path.join(os.sep, "no", "such", "folder", "here"))


def test_reveal_uses_open_on_macos(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    platform_paths.reveal(str(tmp_path))
    assert seen and seen[0][0] == "open"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_reveal_uses_explorer_on_windows(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append(argv))
    platform_paths.reveal(str(tmp_path))
    assert seen and seen[0][0] == "explorer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_platform_paths.py -v`
Expected: FAIL with `ImportError: cannot import name 'platform_paths'`

- [ ] **Step 3: Implement the module**

Create `pdfshrink/platform_paths.py`:

```python
"""Where results go, and how to show them to the user.

Every platform difference in this project lives in this file. Nothing else
branches on sys.platform, which is what keeps the macOS build working while
development happens on Windows.
"""

import os
import subprocess
import sys

OUTPUT_FOLDER = "PDF-réduits"


def _windows_desktop():
    """Ask the shell, because OneDrive redirects Desktop on many machines."""
    import ctypes
    import ctypes.wintypes as wintypes
    import uuid

    class _GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                    ("d3", wintypes.WORD), ("d4", ctypes.c_byte * 8)]

    folder = uuid.UUID("B4BFCC3A-DB2C-424C-B029-7FE99A87C641")   # Desktop
    guid = _GUID()
    guid.d1, guid.d2, guid.d3 = folder.fields[0], folder.fields[1], \
        folder.fields[2]
    guid.d4 = (ctypes.c_byte * 8)(
        *[b - 256 if b > 127 else b for b in folder.bytes[8:]])

    out = ctypes.c_wchar_p()
    rc = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(out))
    if rc != 0 or not out.value:
        return os.path.expanduser("~/Desktop")
    return out.value


def desktop_dir():
    if sys.platform == "win32":
        return _windows_desktop()
    return os.path.expanduser("~/Desktop")


def output_dir():
    """The PDF-réduits folder, created if it does not exist."""
    path = os.path.join(desktop_dir(), OUTPUT_FOLDER)
    if not os.path.isdir(path):
        os.makedirs(path)
    return path


def reveal(path):
    """Show a folder to the user. Never raises: this is a convenience.

    explorer.exe returns 1 even when it succeeds, so its exit code is not
    checked and Popen is used rather than run().
    """
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_platform_paths.py -v`
Expected: 5 passed on Windows

- [ ] **Step 5: Commit**

```bash
git add pdfshrink/platform_paths.py tests/test_platform_paths.py
git commit -m "feat: isolate Windows and macOS paths behind two functions"
```

---

### Task 8: The contact sheet

Not a test — a tool. It renders one page from every rung side by side so a human can judge legibility, which is the one thing the substitution check cannot do. It is what established that `min_dpi = 100` is the floor rather than a round number.

**Files:**
- Create: `scripts/contact_sheet.py`

**Interfaces:**
- Consumes: `pdfshrink.encode.g4_encode`, `build_g4_pdf`; `pdfshrink.core.prep`, `G4_LADDER`.
- Produces: a PNG at a path given on the command line.

- [ ] **Step 1: Write the script**

Create `scripts/contact_sheet.py`:

```python
"""Render one page at every G4 rung so a human can judge legibility.

Usage:
    python scripts/contact_sheet.py INPUT.pdf OUT.png [PAGE]

PAGE is 1-based and defaults to the page carrying the most ink.
"""

import os
import sys

import numpy as np
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfshrink.core import G4_LADDER, prep                       # noqa: E402
from pdfshrink.encode import build_g4_pdf, g4_encode             # noqa: E402
from pdfshrink.render import inspect, load_bilevel_pages         # noqa: E402

DISPLAY_DPI = 300.0
BAND = 240


def _font():
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf",
                      "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, 26)
    return ImageFont.load_default()


def _busiest_page(path):
    doc = pdfium.PdfDocument(path)
    try:
        best, score = 0, -1
        for i in range(len(doc)):
            arr = np.array(doc[i].render(scale=50 / 72.0,
                                         grayscale=True).to_pil().convert("L"))
            ink = int((arr < 128).sum())
            if ink > score:
                best, score = i, ink
        return best
    finally:
        doc.close()


def _crop(path, page_index, window):
    doc = pdfium.PdfDocument(path)
    try:
        pil = doc[page_index].render(scale=DISPLAY_DPI / 72.0,
                                     grayscale=True).to_pil().convert("L")
    finally:
        doc.close()
    y0, y1 = window
    w, h = pil.size
    return pil.crop((int(0.08 * w), int(y0 * h), int(0.72 * w), int(y1 * h)))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, out = sys.argv[1], sys.argv[2]
    page_index = int(sys.argv[3]) - 1 if len(sys.argv) > 3 \
        else _busiest_page(src)

    profile = inspect(src)
    if profile.kind != "bilevel":
        print("not a bilevel document: %s" % profile.kind)
        return 1

    doc = pdfium.PdfDocument(src)
    probe = np.array(doc[page_index].render(scale=200 / 72.0,
                                            grayscale=True).to_pil().convert("L"))
    doc.close()
    rows = (probe < 128).sum(axis=1)
    top = max(range(0, max(1, probe.shape[0] - BAND), 20),
              key=lambda y: rows[y:y + BAND].sum())
    window = (top / probe.shape[0], (top + BAND) / probe.shape[0])

    samples = [("original", src)]
    source = load_bilevel_pages(src)
    workdir = os.path.dirname(os.path.abspath(out))
    for scale, blur, bint, speck in G4_LADDER:
        dpi = int(round(profile.dpi * scale))
        pages = []
        for arr in source:
            page = prep(arr, scale, blur, bint, speck)
            h, w = page.shape
            pages.append((g4_encode(page), w, h))
        dst = os.path.join(workdir, "_sheet_%d.pdf" % dpi)
        build_g4_pdf(pages, dst, profile.page_pts)
        samples.append(("G4 %d dpi" % dpi, dst))

    font, crops = _font(), []
    for label, path in samples:
        crop = _crop(path, page_index, window)
        crops.append(("%s  -  %.0f Ko" % (label, os.path.getsize(path) / 1024),
                      crop))

    cw = max(c.width for _, c in crops)
    ch = max(c.height for _, c in crops)
    pad, bar = 12, 40
    sheet = Image.new("L", (cw + pad * 2,
                            (ch + bar + pad) * len(crops) + pad), 255)
    draw = ImageDraw.Draw(sheet)
    for i, (label, crop) in enumerate(crops):
        y = pad + i * (ch + bar + pad)
        draw.rectangle([pad, y, pad + cw, y + bar], fill=30)
        draw.text((pad + 10, y + 7), label, fill=255, font=font)
        sheet.paste(crop, (pad, y + bar))
    sheet.save(out)
    print("written:", out, "page", page_index + 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run it against the generated bilevel fixture**

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'tests'); \
import pikepdf, numpy as np; from pikepdf import Dictionary, Name; \
w,h=1240,1754; pdf=pikepdf.new(); \
ink=np.zeros((h,w),dtype=bool); ink[200:1500:46,150:1100]=True; \
s=pdf.make_stream(np.packbits(~ink,axis=1).tobytes()); \
s.Type,s.Subtype=Name.XObject,Name.Image; s.Width,s.Height=w,h; \
s.ColorSpace,s.BitsPerComponent=Name.DeviceGray,1; \
p=pdf.add_blank_page(page_size=(595.2,841.44)); \
p.Contents=pdf.make_stream(b'q 595.2 0 0 841.44 0 0 cm /Im0 Do Q'); \
p.Resources=Dictionary(XObject=Dictionary(Im0=s)); pdf.save('sample.pdf')"
.venv/Scripts/python.exe scripts/contact_sheet.py sample.pdf sheet.png
```

Expected: `written: sheet.png page 1`, and `sheet.png` shows the original plus one row per rung with descending sizes. Delete `sample.pdf`, `sheet.png` and the `_sheet_*.pdf` files afterwards.

- [ ] **Step 3: Commit**

```bash
git add scripts/contact_sheet.py
git commit -m "tools: contact sheet for judging legibility at each rung"
```

---

### Task 9: Pinned dependencies and a self-proving installer

The install must need no administrator rights, because on a managed machine an install that prompts for elevation is an install that does not happen. It must also prove itself while someone who can fix it is still present.

**Files:**
- Create: `requirements.txt`
- Create: `Installer.bat`
- Create: `verify_install.py`
- Test: `tests/test_installer.py`

**Interfaces:**
- Consumes: `pdfshrink.core.shrink`.
- Produces: a `.venv` beside `Installer.bat`; `verify_install.py` exits 0 on success and prints a French failure line otherwise.

- [ ] **Step 1: Record the uv version and its checksum**

Pin the version that is known to work here:

```bash
.venv/Scripts/python.exe -c "import urllib.request, hashlib; \
u='https://github.com/astral-sh/uv/releases/download/0.11.19/uv-x86_64-pc-windows-msvc.zip'; \
d=urllib.request.urlopen(u).read(); \
print('bytes', len(d)); print('sha256', hashlib.sha256(d).hexdigest())"
```

Write the printed hash into `Installer.bat` at the `set UV_SHA256=` line in the next step. Do not invent a hash; use the one this command prints.

- [ ] **Step 2: Write `requirements.txt`**

```
pikepdf==10.13.0.post1
pypdfium2==5.13.0
pillow==12.3.0
numpy==2.5.3
scipy==1.18.1
flask==3.1.3
```

- [ ] **Step 3: Write `verify_install.py`**

```python
"""Prove the installation works, in French, before the installer exits."""

import os
import sys
import tempfile

import numpy as np
import pikepdf
from pikepdf import Dictionary, Name

from pdfshrink.core import shrink


def sample(path):
    w, h = 1240, 1754
    pdf = pikepdf.new()
    for _ in range(2):
        ink = np.zeros((h, w), dtype=bool)
        for row in range(150, h - 150, 44):
            ink[row:row + 13, 120:w - 120] = True
        stream = pdf.make_stream(np.packbits(~ink, axis=1).tobytes())
        stream.Type, stream.Subtype = Name.XObject, Name.Image
        stream.Width, stream.Height = w, h
        stream.ColorSpace, stream.BitsPerComponent = Name.DeviceGray, 1
        page = pdf.add_blank_page(page_size=(595.2, 841.44))
        page.Contents = pdf.make_stream(b"q 595.2 0 0 841.44 0 0 cm /Im0 Do Q")
        page.Resources = Dictionary(XObject=Dictionary(Im0=stream))
    pdf.save(path)


def main():
    folder = tempfile.mkdtemp()
    src = os.path.join(folder, "test.pdf")
    dst = os.path.join(folder, "out.pdf")
    try:
        sample(src)
        result = shrink(src, dst, target=200 * 1024)
        if not result.ok or not os.path.exists(dst):
            print("ECHEC : la compression n'a pas abouti.")
            return 1
        if os.path.getsize(dst) >= os.path.getsize(src):
            print("ECHEC : le fichier produit n'est pas plus petit.")
            return 1
        print("OK : %d octets -> %d octets"
              % (os.path.getsize(src), os.path.getsize(dst)))
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
```

- [ ] **Step 4: Write `Installer.bat`**

```bat
@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "APP=%~dp0"
set "UV_VERSION=0.11.19"
set "UV_SHA256=PASTE_THE_HASH_FROM_STEP_1_HERE"
set "UV_URL=https://github.com/astral-sh/uv/releases/download/%UV_VERSION%/uv-x86_64-pc-windows-msvc.zip"
set "UV=%APP%uv.exe"

echo.
echo   Installation de Reduire PDF
echo   ---------------------------
echo.

if not exist "%UV%" (
  echo   Telechargement des outils...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "Invoke-WebRequest -Uri '%UV_URL%' -OutFile '%APP%uv.zip';" ^
    "$h=(Get-FileHash '%APP%uv.zip' -Algorithm SHA256).Hash.ToLower();" ^
    "if ($h -ne '%UV_SHA256%') { Remove-Item '%APP%uv.zip'; throw 'somme de controle incorrecte' };" ^
    "Expand-Archive -Path '%APP%uv.zip' -DestinationPath '%APP%' -Force;" ^
    "Remove-Item '%APP%uv.zip'"
  if errorlevel 1 goto failed
)

echo   Preparation de Python...
"%UV%" venv --python 3.12 "%APP%.venv"
if errorlevel 1 goto failed

echo   Installation des composants...
"%UV%" pip install --python "%APP%.venv\Scripts\python.exe" -r "%APP%requirements.txt"
if errorlevel 1 goto failed

echo   Verification...
pushd "%APP%"
".venv\Scripts\python.exe" verify_install.py
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" goto failed

echo.
echo   Installation terminee.
echo.
pause
exit /b 0

:failed
echo.
echo   L'installation a echoue. Envoyez cette fenetre a votre contact.
echo.
pause
exit /b 1
```

- [ ] **Step 5: Write the installer test**

Create `tests/test_installer.py`:

```python
"""The installer is testable for the first time now that development is on
Windows; on macOS these skip."""

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent
windows_only = pytest.mark.skipif(sys.platform != "win32",
                                  reason="Windows installer")


def test_requirements_are_all_pinned():
    lines = (ROOT / "requirements.txt").read_text(encoding="utf8").split()
    assert lines, "requirements.txt is empty"
    for line in lines:
        assert "==" in line, "%s is not pinned" % line


@windows_only
def test_installer_pins_a_real_checksum():
    text = (ROOT / "Installer.bat").read_text(encoding="utf8")
    assert "PASTE_THE_HASH" not in text, "the uv checksum was never recorded"
    for line in text.splitlines():
        if line.strip().startswith("set \"UV_SHA256="):
            value = line.split("=", 1)[1].strip().strip('"')
            assert len(value) == 64, value
            int(value, 16)
            return
    pytest.fail("no UV_SHA256 line in Installer.bat")


@windows_only
def test_verify_install_succeeds_in_this_environment():
    """The same check the installer runs, against the dev virtualenv."""
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        pytest.skip("no .venv in the project")
    done = subprocess.run([str(python), str(ROOT / "verify_install.py")],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "OK :" in done.stdout
```

- [ ] **Step 6: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_installer.py -v`
Expected: 3 passed. `test_installer_pins_a_real_checksum` fails until Step 1's hash is pasted in — that is the point.

- [ ] **Step 7: Run the installer end to end in a clean folder**

Run these in **cmd.exe**, not Git Bash — the installer is a batch file and
must be exercised the way the user will run it:

```bat
mkdir "%TEMP%\rp-test"
copy Installer.bat "%TEMP%\rp-test\"
copy requirements.txt "%TEMP%\rp-test\"
copy verify_install.py "%TEMP%\rp-test\"
xcopy /E /I pdfshrink "%TEMP%\rp-test\pdfshrink"
"%TEMP%\rp-test\Installer.bat"
```

Expected: it downloads `uv`, builds `.venv`, installs the pinned wheels, prints
`OK : N octets -> M octets` and `Installation terminee.`

This must be run from an **ordinary, non-elevated** prompt. If it succeeds only
when run as administrator, the no-admin requirement has been broken and the task
is not done. Delete `%TEMP%\rp-test` afterwards with
`rmdir /S /Q "%TEMP%\rp-test"`.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt Installer.bat verify_install.py tests/test_installer.py
git commit -m "feat: no-admin Windows installer that proves itself"
```

---

### Task 10: Launcher, Desktop shortcut and the note to the user

**Depends on `pdfshrink/web.py`** from the parent plan's Task 8. Write this now; the launcher test skips while `web.py` is absent and turns green when it lands.

**Files:**
- Create: `Réduire PDF.bat`
- Create: `LISEZ-MOI.txt`
- Modify: `Installer.bat`
- Modify: `tests/test_installer.py`

**Interfaces:**
- Consumes: `pdfshrink.web` (parent plan), `pdfshrink.platform_paths` from Task 7.
- Produces: a Desktop `.lnk` named `Réduire PDF`.

- [ ] **Step 1: Write the launcher**

Create `Réduire PDF.bat`:

```bat
@echo off
chcp 65001 >nul
start "" "%~dp0.venv\Scripts\pythonw.exe" -m pdfshrink.web
```

`pythonw.exe` so no console window appears. The server writes `journal.txt` beside the application for diagnosis.

- [ ] **Step 2: Write the note**

Create `LISEZ-MOI.txt`:

```
Réduire PDF
===========

Première utilisation :
  double-cliquez sur Installer.bat, puis attendez le message
  « Installation terminée ».

Ensuite :
  double-cliquez sur l'icône « Réduire PDF » sur le Bureau.
  Votre navigateur s'ouvre ; déposez-y votre PDF.

Les fichiers réduits sont enregistrés dans le dossier
« PDF-réduits » sur votre Bureau. Le fichier d'origine
n'est jamais modifié.

Ouvrez toujours le fichier réduit pour le vérifier avant
de l'envoyer.

En cas de problème, envoyez le fichier journal.txt à votre contact.
```

- [ ] **Step 3: Create the shortcut from the installer**

In `Installer.bat`, insert before the `echo   Installation terminee.` line:

```bat
echo   Creation du raccourci...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$desk=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'Réduire PDF.lnk'));" ^
  "$s.TargetPath='%APP%Réduire PDF.bat';" ^
  "$s.WorkingDirectory='%APP%';" ^
  "$s.IconLocation='%APP%.venv\Scripts\pythonw.exe,0';" ^
  "$s.Description='Réduire la taille d''un PDF';" ^
  "$s.Save()"
if errorlevel 1 goto failed
```

`[Environment]::GetFolderPath('Desktop')` is the same shell known folder that `platform_paths.desktop_dir()` resolves, so the shortcut and the output folder never disagree.

- [ ] **Step 4: Write the launcher tests**

Append to `tests/test_installer.py`:

```python
def test_readme_is_french_and_mentions_the_output_folder():
    text = (ROOT / "LISEZ-MOI.txt").read_text(encoding="utf8")
    assert "PDF-réduits" in text
    assert "Installer.bat" in text
    assert "vérifier avant" in text


@windows_only
def test_launcher_uses_pythonw_so_no_console_appears():
    text = (ROOT / "Réduire PDF.bat").read_text(encoding="utf8")
    assert "pythonw.exe" in text
    assert "python.exe" not in text.replace("pythonw.exe", "")
    assert "chcp 65001" in text


@windows_only
def test_installer_creates_a_desktop_shortcut():
    text = (ROOT / "Installer.bat").read_text(encoding="utf8")
    assert "WScript.Shell" in text
    assert "Réduire PDF.lnk" in text
    assert "GetFolderPath('Desktop')" in text


@windows_only
def test_the_server_starts_and_serves_the_page():
    """Skips until pdfshrink/web.py exists (parent plan, Task 8)."""
    pytest.importorskip("pdfshrink.web")
    import socket
    import threading
    import time
    import urllib.request

    from pdfshrink import web

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    app = web.create_app()
    thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, use_reloader=False),
        daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/" % port) as r:
                assert r.status == 200
                return
        except Exception:
            time.sleep(0.1)
    pytest.fail("the server did not answer on 127.0.0.1:%d" % port)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_installer.py -v`
Expected: the shortcut, launcher and note tests pass; `test_the_server_starts_and_serves_the_page` skips with "No module named 'pdfshrink.web'"

- [ ] **Step 6: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: everything passes except the `ba2` tests, which skip when `BA2.pdf` is absent and fail with the explicit guard message when the wrong file is present

- [ ] **Step 7: Commit**

```bash
git add "Réduire PDF.bat" LISEZ-MOI.txt Installer.bat tests/test_installer.py
git commit -m "feat: launcher, Desktop shortcut and the note to the user"
```

---

## What this plan does not deliver

- **The page itself.** `pdfshrink/web.py`, `cli.py` and `static/` remain the parent plan's Tasks 7–9. Until they land, Task 10's launcher starts a module that does not exist.
- **`journal.txt`.** The launcher and `LISEZ-MOI.txt` both refer to it, but the logging that writes it belongs to `web.py`. Whoever implements the parent plan's Task 8 must configure Flask to log beside the application, or the note tells the user to send a file that is never created.
- **Output naming and collision handling.** `platform_paths.output_dir()` creates the `PDF-réduits` folder; the counter-appending rule from the parent design belongs to its `output.py`. **That module must call `platform_paths.desktop_dir()` rather than resolving Desktop itself** — a second implementation would reintroduce the OneDrive bug this plan exists to avoid, and would put the shortcut and the output folder on different Desktops.
- **The golden test.** It cannot run until the real 1 648 Ko, 300 dpi `BA2.pdf` is found. Task 1 makes its absence explicit rather than silent.
- **JBIG2 on Windows.** Deliberately. `have_jbig2()` picks up a `jbig2.exe` placed on PATH with no code change, so this stays available without being shipped.
