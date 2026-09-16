# Windows delivery — design

**Date:** 2026-09-16
**Status:** approved design, ready for planning
**Extends:** `2026-09-16-pdf-shrink-web-design.md`

## Purpose

The original design deferred Windows for one reason: the developer worked on macOS
and had no Windows machine to verify against. That constraint is gone. Development
now happens on Windows 11, so the platform the user actually runs can be built and
tested directly instead of guessed at through CI.

This document covers what changes as a result. It does not restate the parent
design; the page, its five states, the French copy, the localhost binding and the
non-goals are unchanged.

Verifying the parent design on Windows also uncovered three defects. Two are not
Windows-specific and are fixed here because they are cheap to fix while the engine
is open, and because one of them makes the refusal state absurd.

## Decisions

| Question | Decision |
|---|---|
| Delivery targets | Windows built and verified now; macOS kept working |
| How it reaches the user | A zipped folder, `Installer.bat` run once, then a Desktop shortcut |
| Python | `uv`, fetched by the installer and pinned by version and SHA-256, `--python 3.12` |
| Administrator rights | Not required, and not requested |
| Bilevel without `jbig2enc` | A new CCITT G4 ladder, not the JPEG path |
| `jbig2enc` | Still optional, still the only tolerated external binary; not shipped |
| G4 substitution check | Not performed — G4 cannot substitute a glyph |
| Fallback size offer | Only when it saves at least 10 % of the original |

## Evidence

Measured on this Windows 11 machine, Python 3.14.0, against a 101-page bilevel
fixture. These numbers become regression fixtures.

**The pure-pip stack works on Windows.** `pikepdf 10.13.0.post1`, `pypdfium2
5.13.0`, `pillow 12.3.0`, `numpy 2.5.3`, `scipy 1.18.1` and `flask 3.1.3` all
install as wheels in about 70 seconds — no compiler, no MSYS2, no PATH changes.
The existing suite runs 34 passed, 1 skipped, 5 failed, and every failure is
explained below. The parent design's headline risk — "nothing in this design is
confirmed on the target platform" — is retired for the engine.

The Python 3.9 pin in the parent plan was an artefact of macOS system Python. It
does not bind here.

**CCITT G4 is feasible with pure pip, and the parent design's estimate was right.**
Pillow writes a group 4 TIFF, the single strip is lifted out and embedded as a
`CCITTFaxDecode` stream with `BlackIs1=true`. Measured, with the engine's own
substitution check run for information only:

| dpi | measured | parent design's table | largest clump |
|---:|---:|---:|---:|
| 300 | 1 468,6 Ko | — | 30 |
| 200 | 1 051,5 Ko | 1 123 Ko | 14 |
| 150 | 839,7 Ko | 845 Ko | 88 |
| 120 | 701,0 Ko | 689 Ko | 7 |
| 100 | 614,7 Ko | 591 Ko | 7 |

Within about 6 % of figures produced by an entirely different toolchain. At
**8,31 Ko/page at 150 dpi**, a 200 Ko budget holds 24 pages at 150 dpi, 19 at 200,
32 at 100, 13 at 300. Encoding 101 pages takes 2–7 seconds.

**Legibility sets the floor, not size.** Rendered side by side, 300 and 200 dpi are
indistinguishable from the source; 150 dpi is marginally softer and fully crisp;
120 dpi thins strokes and smears punctuation while staying readable; 100 dpi breaks
characters apart and reads like a bad fax. `min_dpi = 100` is the right floor and
is now justified by inspection rather than convention.

**Without a G4 rung, bilevel documents fall to JPEG, which is catastrophic.**
`core.py` routes `bilevel and have_jbig2()` to JBIG2 and *everything else* to the
raster path. On a machine without `jbig2enc` the measured ladder for the fixture is
7 840 395 B at 150 dpi, 5 406 377 at 120, 3 918 342 at 100 — a floor of 3 827 Ko.
The parent design's "about 24 pages at 150 dpi" was computed from its G4 column,
a rung that was never implemented. Real capability without this work is one to two
pages.

**`jbig2enc` for Windows exists only as unofficial builds.** There is no
pip-installable JBIG2 encoder (`jbig2`, `jbig2enc`, `pyjbig2`, `jbig2-encoder` are
all absent from PyPI), confirming the parent design's claim. `unpins/jbig2`, which
advertises CI-built static binaries, has zero releases, zero stars, no licence and
was first pushed on 2026-09-15. `anotatta/jbig2enc` offers a single 1,6 MB
`jbig2.exe` from 2021, a fork of a fork, unsigned, 1 171 downloads. Neither is
shipped to a non-technical user.

**Desktop is not reliably `~/Desktop`.** `SHGetKnownFolderPath(FOLDERID_Desktop)`
resolves correctly on this machine and agrees with `~/Desktop`, but OneDrive is
installed, which puts folder redirection one settings toggle away and makes it the
norm on managed machines.

## Engine changes

### The G4 rung

`shrink()` gains one branch:

```
digital                    -> _shrink_digital      unchanged
bilevel and have_jbig2()   -> _shrink_bilevel      unchanged
bilevel                    -> _shrink_bilevel_g4   new
otherwise                  -> _shrink_raster       unchanged
```

G4 is tried **only when `jbig2enc` is absent**, never as a fallback after the JBIG2
ladder. JBIG2 beats G4 at every resolution — 293 Ko against 845 Ko at 150 dpi — so
a G4 rung cannot rescue a target that JBIG2 has already missed. One branch, no
interleaving.

The ladder is the dpi sequence 300, 200, 150, 120, 100 down to `min_dpi`, because
G4 has no lossy parameter to tune. It walks down and stops at the first rung that
fits. `prep()` — blur, threshold, despeckle — is reused unchanged; it took the
JBIG2 rung from 293 Ko to 199 Ko and should help G4 more, since isolated noise
pixels are expensive in run-length coding. The 839,7 Ko measurement above used
naive thresholding and is therefore a pessimistic bound.

### G4 rungs are not substitution-checked

Substitution is a property of JBIG2's `-s` symbol matching, where one glyph is
silently replaced by a similar one. G4 encodes the exact bitmap it is handed and
cannot substitute a character; only the shared render-and-threshold step degrades
it, which is a question of legibility, not of corruption. The parent design already
places the raster and digital paths in this category and G4 belongs there.

This is not an optimisation. Running the check would cause false refusals:
resampling noise alone produced clumps of 7 to 88 px in the measurements above, and
88 is uncomfortably close to the `SUBSTITUTION_PIXELS = 120` threshold. A document
refused because downsampling jittered some serifs would be a defect.

### The `jbig2dec` dependency

`load_bilevel_pages` extracts through `pikepdf.PdfImage(...).as_pil_image()`, which
spawns **`jbig2dec`** when the embedded image is JBIG2 and raises
`DependencyError: jbig2dec - not installed or not found` when it is absent. The
ordinary trigger is the user re-shrinking a file he already shrank — and state ⑤
forbids showing him a stack trace.

Each page's extraction is wrapped and falls back to a `pypdfium2` render at the
image's native resolution when decoding raises. This is the fallback the parent
design already specifies on that line; it was never written. `pypdfium2` renders
the affected file correctly, so the fallback is known to work.

### The refusal defect

`best_safe_size` offered 3 827 Ko for a 197 Ko input — state ④ would propose
making his file twenty times larger. State ④ now renders the *« Réduire quand
même »* button **only when the best safe result saves at least 10 % of the
original**. Otherwise it reports `already_minimal` and offers no button, reusing
the shape the parent design defines for a digital PDF at its floor.

This defect is not Windows-specific. It fires on macOS whenever a raster floor
exceeds the input size.

### The portability guard

The current guard greps this project's own source, which is why a `jbig2dec`
subprocess inside pikepdf passed it green. It is replaced by a test that patches
`subprocess.Popen` during a real shrink of a JBIG2-bearing fixture and asserts that
nothing anywhere — this code or its dependencies — spawns `qpdf`, `pdfimages`,
`pdftoppm`, `pdffonts` or `jbig2dec`. `jbig2` remains the only permitted name.

## Delivery

**What he receives.** One zipped folder containing `Installer.bat`, `Réduire
PDF.bat`, the `pdfshrink` package, a pinned `requirements.txt` and a five-line
`LISEZ-MOI.txt`. He unzips it, double-clicks `Installer.bat` once, and afterwards
uses a Desktop shortcut the installer creates — a `.lnk` with an icon and a French
name, so the thing he clicks every day is never a `.bat` file.

**Python comes from `uv`.** `Installer.bat` fetches `uv` from Astral's official
release URL, pinned to a version and checked against a SHA-256, then runs `uv venv
--python 3.12` and `uv pip install -r requirements.txt`. The decisive property is
that **no administrator rights are needed**: `uv` downloads a standalone CPython
into the user's profile and touches neither PATH nor the system. On a managed work
machine, an install that prompts for elevation is an install that does not happen.

`uv` is a signed, current, officially published tool, used at install time only and
pinned by checksum. It is not a runtime dependency of the engine, and the constraint
it must not weaken — no Unix binaries on the compression path — is unaffected.

**The install proves itself.** `Installer.bat` finishes by starting the server,
requesting the page, confirming a 200 and shutting down. A broken install announces
itself while someone who can fix it is still present, rather than five weeks later
as a shortcut that does nothing.

**Launching.** The shortcut runs `pythonw.exe -m pdfshrink.web`, so no console
window appears. The server writes `journal.txt` beside the application for
diagnosis. Ephemeral-port binding and browser opening are unchanged from the parent
design and behave identically on Windows.

**Platform differences live in one module.** `platform_paths.py` exposes exactly
two functions, `desktop_dir()` and `reveal(path)`, with a Windows and a macOS
implementation each. Windows resolves Desktop through
`SHGetKnownFolderPath(FOLDERID_Desktop)` rather than assuming `~/Desktop`, and
`reveal()` ignores `explorer.exe`'s exit code, which is `1` even on success. No
other file branches on platform, which is what keeps macOS working as a property
rather than an intention.

**Encoding.** Both `.bat` files set `chcp 65001` so that `PDF-réduits` and the
French text survive.

## Testing

Development is test-first.

**The fixture guard.** A file named `BA2.pdf` was present during this work, three
tests failed, and the cause was neither broken code nor a missing fixture but a
different document — the 197 Ko JBIG2 *output* rather than the 1 648 Ko original.
The `ba2` fixture keeps skipping when absent and gains an identity assertion: 101
pages, 300 dpi, a CCITT-encoded first image, and a file size within 5 % of
1 648 Ko. A present-but-wrong fixture must fail loudly, because it costs more than
a missing one.

**G4 encoder tests**, shaped by the two bugs found while measuring:

- **Single strip.** Assert `len(StripOffsets) == 1`. Taking only the first of
  several strips produced a smaller, entirely plausible file — 179,8 Ko, a number
  that looked like a breakthrough. Silent corruption that flatters the metric is
  the worst kind, and only the substitution check caught it.
- **Polarity.** Round-trip each encoded page and compare ink fraction. A
  `BlackIs1` regression appears as roughly 98 % mismatch.
- **Monotonicity.** Output size must strictly decrease as dpi decreases. The
  inverted trend — 180 Ko at 150 dpi against 358 Ko at 100 dpi — was the first
  sign that something was wrong.
- **Routing.** With `have_jbig2()` forced false, a bilevel document must take the
  G4 path and never the JPEG path.

**Defect regressions.** No fallback size is ever offered that saves under 10 %, and
in particular never one larger than the input. The `jbig2dec` fallback is tested
against a hand-built minimal JBIG2 generic-region blob of a few hundred bytes,
checked in as a permanent fixture, so the test is hermetic, contains no personal
document, and never depends on `jbig2dec` being installed.

**Delivery tests**, possible for the first time because development moved to
Windows. `Installer.bat` runs into a clean temporary directory; the test asserts
the virtual environment exists, the server starts, the page returns 200 and the
shortcut is created. `platform_paths` is tested directly on Windows and through a
patched `sys.platform` for its macOS logic, with the real macOS run marked manual.

**A contact-sheet script**, not a test: renders a chosen page from each rung side
by side so a human can judge legibility on any document in one command. It is what
established that `min_dpi = 100` is the floor.

**Two things stay manual.** Watching the intended user shrink a PDF unaided, and
opening the result before sending it. Neither can be automated, and the second is
why the page always says *« Ouvrez le fichier pour le vérifier avant de
l'envoyer. »*

## Non-goals

Unchanged from the parent design. Additionally: no PyInstaller executable, no code
signing, no auto-update, no CI Windows runner — development happens on Windows now,
so the runner exists to work around a problem that no longer exists.

## Risks

**The golden test cannot run until the true `BA2.pdf` is found.** The 1 648 Ko,
300 dpi original is not on this machine; only its output is. Until it appears, the
199 Ko / 84 px result is a claim in a document rather than a green test.

**G4 does not close the gap for long scans.** A 101-page scan floors at 614,7 Ko,
three times over a 200 Ko target, and the ugliest rung anyone would accept still
misses. Long scans are refused on Windows. The refusal is correct and honest, but
it is a real capability difference from a macOS machine with `jbig2enc`.

**`prep()`'s effect on G4 is unmeasured.** It is expected to help and cannot hurt,
but the pages-per-budget figures above assume it does nothing.

**macOS is now the unverified platform.** The asymmetry has simply reversed. The
single `platform_paths` module and the patched-`sys.platform` tests reduce the risk;
they do not eliminate it.
