# Réduire PDF

A local web page that shrinks a PDF to a size you type, and refuses rather than
hand back a file whose text may have been corrupted.

It exists for one person: a non-technical Windows user who has to fit scanned
documents under an upload portal's 200 Ko cap, without a terminal, without
reading documentation, and without the risk of sending a document in which
compression silently altered a character.

Measured on a real 101-page bilevel scan: **1 648 Ko → 199 Ko**, verified clean.

## For the person using it

Unzip the folder anywhere, then:

1. Double-click **`Installer.bat`** once. It takes about five minutes, needs no
   administrator rights, and ends with *« Installation terminée »*. It puts a
   **« Réduire PDF »** icon on the Desktop.
2. Double-click that icon. No window appears; the browser opens by itself.
3. Drag a PDF onto the page, type the size you need, and wait. A long scan takes
   a few minutes.

Results are saved to a **`PDF-réduits`** folder on the Desktop and offered as a
download. The original file is never modified.

If the target is impossible, the page says so in plain French and offers the
smallest size that verified clean — it never quietly hands back something worse.

**Always open the result before sending it.** The software can prove no character
was substituted; only you can judge whether the resolution is still legible.

## Building the archive

```bash
python scripts/package.py
```

Produces `dist/Reduire-PDF.zip` — 21 files, about 27 Ko — from an explicit
allow-list. This matters: the project folder also holds test documents, a 65 MB
`uv.exe` and a 214 MB virtualenv. A deny-list runs as a second net and the test
suite proves it fires, so a personal document cannot ship by accident.

## Development

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt pytest
.venv/Scripts/python.exe -m pytest -q           # Windows
.venv/bin/pytest -q                             # macOS
```

Run it directly:

```bash
python -m pdfshrink.web                         # the page
python -m pdfshrink IN.pdf OUT.pdf --target "200 Ko" --json
python scripts/contact_sheet.py IN.pdf sheet.png   # legibility at every rung
```

Source targets **Python 3.9 syntax** so macOS system Python keeps working; the
Windows installer pins 3.12.

## How it works

`inspect()` classifies the document, then one of four strategies runs:

| Document | Strategy |
|---|---|
| digital text | lossless restructure only — never rasterised |
| bilevel scan, `jbig2enc` present | JBIG2 symbol coding |
| bilevel scan, no `jbig2enc` | CCITT G4 |
| colour or greyscale scan | JPEG |

Each walks a quality ladder best-first and stops at the first rung that fits, so
the result is the best quality meeting the budget rather than the smallest file.

**The verification gate.** JBIG2's symbol coder can replace one glyph with a
similar one. After encoding, the document is decoded again and compared with what
the encoder was fed; the largest connected clump of changed pixels is measured.
Edge softening is thin and scattered, a substituted character is one compact blob
about the size of a glyph, so a clump at or above `SUBSTITUTION_PIXELS = 120`
means the file is refused, never offered.

G4, JPEG and lossless paths are not substitution-checked: they cannot swap a
glyph, only degrade one, and checking them would cause false refusals from
resampling noise alone.

**No Poppler, no qpdf.** Everything goes through `pikepdf` and `pypdfium2`, which
is what makes a Windows build possible. A test patches `subprocess.Popen` during a
real run and fails if anything spawns `qpdf`, `pdfimages`, `pdftoppm`, `pdffonts`
or `jbig2dec` — including from inside a dependency, which is how `jbig2dec` went
unnoticed for a while.

## jbig2enc

Optional, and the difference between reaching 200 Ko and not.

| 101-page scan | floor |
|---|---:|
| with `jbig2enc` | **199 Ko** |
| CCITT G4 only | 585 Ko |
| JPEG fallback | 3 827 Ko |

The installer fetches it from conda-forge — 13 packages pinned by filename and
MD5, extracted to a `jbig2/` folder beside the application. It is fetched, never
redistributed. If the fetch fails the installer warns and carries on, because the
program still works without it.

```bash
python scripts/fetch_jbig2.py        # fetch it into ./jbig2
```

Costs per page at 150 dpi, measured: **8,1 Ko** for G4, so a 200 Ko budget holds
about 24 pages without `jbig2enc`. Below 100 dpi characters break apart, which is
why `min_dpi` is 100.

## Testing

```
pytest -q                 # everything
pytest -q -m "not slow"   # skip the 101-page runs
```

The golden tests need a `BA2.pdf` that is not in this repository — it is a
personal document. When present it must be the exact original (1 687 366 bytes,
101 pages, 300 dpi); a different file with that name fails loudly rather than
producing a confusing regression.

Tests that need `jbig2enc` skip without it, and the G4 equivalents skip when it
is installed, so the suite is green either way.

## What is not done

- **Never installed on a second machine.** Everything was verified on the machine
  it was built on.
- **Windows 10 untested**; only Windows 11.
- **Needs four hosts reachable** at install time: `github.com`, Astral's Python
  index, `pypi.org` and `conda.anaconda.org`. A proxy blocking the last one
  degrades quietly to "long scans refused".
- **No way to quit.** The server runs until the machine restarts, and clicking the
  icon again starts another one on another port.
- **If the browser fails to open**, the user sees nothing; the URL is only in
  `journal.txt`.
- **macOS is now the unverified platform.** Every platform difference lives in
  `platform_paths.py`, but the macOS launcher was never built.

## Layout

```
pdfshrink/
  sizes.py            parse and format sizes, French and English units
  render.py           page inspection and rasterisation
  encode.py           JBIG2, CCITT G4, JPEG, lossless
  verify.py           the substitution check
  core.py             strategy selection and the ladders
  output.py           where results are written
  platform_paths.py   every Windows/macOS difference, and nowhere else
  cli.py              command line, with --json
  web.py              Flask layer
  static/             the page
scripts/
  package.py          build the archive that ships
  fetch_jbig2.py      fetch the encoder from conda-forge
  contact_sheet.py    render every rung for a human to judge
  make_jbig2_fixture.py
docs/superpowers/     design documents and implementation plans
```

Design documents are in `docs/superpowers/specs/`; they carry the measurements
and the reasoning behind the decisions above.
