# Réduire PDF — a local web page for shrinking PDFs

**Date:** 2026-09-16
**Status:** approved design, ready for planning

## Purpose

A non-technical user needs to shrink PDFs to fit an upload portal's size cap,
typically 200 Ko. He must be able to do this alone, without a terminal, without
reading documentation, and without the risk of sending a document in which
compression has silently altered a character.

The compression engine already exists as `pdfshrink.py`, a command-line tool. This
project wraps that capability in a page he can use, and removes the platform
dependencies that would prevent it from ever running on Windows.

The primary user is on Windows. The developer is on macOS. Neither has access to
the other's machine for testing. This asymmetry drives several decisions below.

## Decisions

| Question | Decision |
|---|---|
| How it starts | Double-click a Desktop icon; server and browser open together |
| Interface language | French |
| Target size | A text box he types into, pre-filled `200 Ko` |
| Where the result goes | Saved to a folder *and* offered as a download |
| When the target is unreachable | Refuse, explain, offer the best size that verified clean |
| Platform | macOS built and verified now; Windows unblocked, delivered later |
| Dependencies | `pip` only — no Unix binaries except optional `jbig2enc` |

## Evidence from the feasibility probe

Measured on `BA2.pdf` (1648 Ko, 101 pages, bilevel, 300 dpi, already CCITT G4).
These numbers justify the design and become regression fixtures.

**The existing tool performs as documented.** Running its real ladder end to end
produced 203788 bytes (199.0 Ko) at 150 dpi, `symthr` 0.78, with a largest changed
pixel clump of 84 px on page 85 — matching the SKILL.md claim exactly.

**The pure-pip stack works.** `pikepdf`, `pillow`, `pypdfium2`, `numpy` and `scipy`
install and run on stock macOS Python 3.9 with no Homebrew and no PATH changes.

**Verification ports to `pypdfium2`.** Re-running the substitution check with
`pypdfium2` instead of `pdfimages` reproduced the same result — 84 px, page 85.
The safety guarantee does not depend on Poppler.

**It is much faster than documented.** The winning rung took about 10 seconds for
101 pages, not the 1–3 minutes SKILL.md warns about, because `pypdfium2` renders
far faster than `pdftoppm`.

**There is no pure-Python substitute for JBIG2.** Full-document measurements:

| dpi | JBIG2 | CCITT G4 | JPEG |
|---:|---:|---:|---:|
| 200 | 420 Ko | 1123 Ko | — |
| 150 | 293 Ko¹ | 845 Ko | 5549 Ko |
| 120 | 249 Ko | 689 Ko | 3938 Ko |
| 100 | 215 Ko | 591 Ko | 2928 Ko |

¹ naive thresholding; the existing `prep()` (blur before threshold, then despeckle)
takes this same rung to 199 Ko.

G4 never drops below 591 Ko even at an illegible 100 dpi, and JPEG is an order of
magnitude worse. An earlier proposal to add a CCITT G4 rung as a JBIG2 replacement
was abandoned on this evidence.

**But the gap is bounded, because what matters is cost per page.** G4 costs roughly
8.4 Ko/page at 150 dpi. Within a 200 Ko budget and without JBIG2, a Windows build
handles about 12 pages at 300 dpi, 18 at 200 dpi, 24 at 150 dpi, 34 at 100 dpi.
Everyday documents fit. Only long scans like `BA2.pdf` fail, and those receive an
honest refusal.

## Architecture

```
pdfshrink/
  sizes.py    parse and format sizes, French and English units
  render.py   pypdfium2: page rasterisation, font and image inspection
  encode.py   JBIG2 (when available), JPEG, lossless restructure
  core.py     strategy selection, quality ladder, verification
  web.py      Flask application
  static/     one HTML page, one stylesheet, one script
tests/
docs/superpowers/specs/
```

`core.py` keeps the existing tool's logic: the three-way strategy choice, the walk
down a quality ladder stopping at the first rung that fits, the `prep()`
preprocessing, the `SUBSTITUTION_PIXELS = 120` clump test, and the refusal to
rasterise a digital text PDF.

### Removing the Unix dependency

| Was | Becomes |
|---|---|
| `pdffonts` | `pypdfium2` font enumeration |
| `pdfimages -list` | `pikepdf` image XObject inspection |
| `pdfimages` | `pikepdf` image extraction, `pypdfium2` fallback |
| `pdftoppm -jpeg` | `pypdfium2` render, Pillow JPEG encode |
| `qpdf` | `pikepdf.save()` — pikepdf is libqpdf |
| `jbig2` | unchanged, and optional |

**This is a hard constraint, not a preference.** A test asserts that no subprocess
invocation names `qpdf`, `pdfimages`, `pdftoppm` or `pdffonts`. If one reappears,
the Windows build becomes impossible again. `jbig2enc` is the sole permitted
external binary: used when present, cleanly absent when not.

### Engine changes beyond porting

1. **Report the best safe size on failure.** Today the ladder verifies only rungs
   that fit the budget, and returns nothing useful when none does. It must also
   determine the smallest size that verified clean, so the page can offer it.
   For bilevel, verify candidates in increasing order of size and take the first
   clean one; every rung is by definition above the requested target, since none
   fitted. Each verification decodes the whole document, so this costs roughly one
   extra pass per candidate examined and must only run on the refusal path. For
   raster and digital there is no substitution risk, so the smallest rung at or
   above `min_dpi` is the answer.
2. **A `--json` output mode**, so the web layer reads structured results rather
   than parsing printed text.
3. **French units in size parsing** (see below).

## Size parsing

Accepts, case-insensitively, with or without spaces: a bare number read as Ko;
`Ko`, `ko`, `KB`, `K`; `Mo`, `mo`, `MB`, `M`. Decimal comma and decimal point are
equivalent, so `1,5 Mo` and `1.5MB` are the same value.

Anything else is rejected without an exception, producing
*« je ne comprends pas cette taille »*.

Sizes are displayed French style: `1 648 Ko`, narrow space as thousands separator.

## The page

One page, five states. No menus, no settings, no history, no batch upload.

**① Waiting.** A large dashed drop area: *« Glissez votre PDF ici »*, beneath it
*« ou cliquez pour choisir un fichier »*. One text input labelled *« Taille
souhaitée »*, pre-filled `200 Ko`. As he types, a line beneath echoes the parsed
value — *« compris : 1,5 Mo »* — or *« je ne comprends pas cette taille »*, in
which case the action button is disabled. He learns the input is wrong before
committing, not after.

**② Working.** Filename, progress bar, and one changing line: *« Analyse du
document… »*, *« Compression (page 34 sur 101)… »*, *« Vérification du texte… »*.

**③ Done.** Prominently: `1 648 Ko → 199 Ko`. A primary button *« Télécharger »*.
Below it *« Enregistré aussi dans le dossier PDF-réduits »* with *« Ouvrir le
dossier »*. And, always: *« Ouvrez le fichier pour le vérifier avant de
l'envoyer. »* — the software can prove no character changed, but cannot judge
whether the chosen resolution is legible enough for the recipient.

**④ Refused.** No download control is rendered. *« Ce fichier ne peut pas descendre
à 200 Ko sans risque pour le texte. »* followed by the specific reason, for example
*« C'est un document de 101 pages ; à cette taille, les caractères deviendraient
illisibles. »* A digital text PDF that misses its target says instead that it is
already near its floor and suggests splitting it, never rasterisation. One button
offers the best clean size, computed per document — *« Réduire quand même à
340 Ko »*, where 340 is whatever that document actually achieved, not a constant.

This state is also what a verification warning produces. A file whose check reports
a clump at or above `SUBSTITUTION_PIXELS` is never offered for download.

**⑤ Error.** Plain French, never a stack trace: *« Ce fichier n'est pas un PDF
valide. »*, *« Le fichier est protégé par un mot de passe. »*

## Output handling

The original is never modified or overwritten. The result is written to a
`PDF-réduits` folder on the Desktop, created if absent, and is simultaneously
available through the *« Télécharger »* button. A name collision appends a counter
rather than replacing an existing file. *« Ouvrir le dossier »* uses `open` on
macOS and `explorer` on Windows.

## Running it

The server binds to `127.0.0.1` only. It is unreachable from the network, so there
is no authentication to build and nothing is exposed. It serves one user.

It binds an ephemeral port rather than a fixed one — port 5000 is taken by AirPlay
Receiver on macOS — and the launcher opens the browser at whichever port was
obtained.

**macOS:** a `Réduire PDF.command` file on the Desktop. Double-clicking starts the
server and opens the browser. A separate one-time setup script creates the
virtual environment and installs dependencies.

**Windows:** deferred by decision, not blocked by design. When it is built, the
intended route is a PyInstaller single-file executable produced and tested by a
GitHub Actions Windows runner, because PyInstaller cannot cross-compile from macOS
and because CI is the only way to verify the Windows build without a Windows
machine. An `installer.bat` using `winget` is the fallback. Nothing in this design
prevents either.

## Non-goals

Batch processing, file history, a settings screen, OCR, PDF editing, network
access, and user accounts. Each adds a way for the user to become confused in
exchange for something he has not asked for.

## Testing

Development is test-first.

- **Golden test:** `BA2.pdf` at a 200 Ko target yields at most 204800 bytes, wins
  at 150 dpi, and verifies clean with a largest clump of 84 px on page 85.
- **Strategy coverage:** generated fixtures for a digital text PDF (must remain
  lossless and never be rasterised) and a colour scan (JPEG path).
- **Size parser:** `200`, `200 Ko`, `1,5 Mo`, `0.5MB`, `200kb`, and malformed
  input that must produce a message rather than an exception.
- **Page states:** each of the five, particularly ④ — an impossible target must
  return no download link and a correct best-safe size.
- **Portability guard:** no subprocess call names `qpdf`, `pdfimages`, `pdftoppm`
  or `pdffonts`.

One test cannot be automated: watch the intended user shrink a PDF unaided. Any
hesitation is a defect in the page.

## Risks

**Windows is unverified.** Nothing in this design is confirmed on the target
platform. The portability guard and the pure-pip stack reduce the risk; they do not
eliminate it.

**Long scans will be refused on Windows.** Without `jbig2enc`, documents beyond
roughly 24 pages at 150 dpi cannot reach 200 Ko. The refusal is honest and offers
an alternative, but it is a genuine capability gap between the two platforms.

**Aggressive ladder rungs carry real substitution risk.** `BA2.pdf` only fits at
`symthr` 0.78, the most aggressive glyph-merging setting on the ladder, after three
gentler rungs overshoot. It verified clean here, but that is a per-document result,
not a guarantee. This is why the refusal path is enforced by the page rather than
left to the user's judgement.
