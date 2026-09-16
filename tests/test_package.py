"""What leaves this machine is an allow-list, and the suite enforces it.

The project folder holds the developer's own scanned documents, a 65 MB
uv.exe, a 214 MB virtualenv and the test suite. Zipping the folder by hand
would hand all of it to a non-technical user along with the application.
"""

import pathlib
import sys
import zipfile

import pytest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import package  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return package.build(str(tmp_path_factory.mktemp("dist")))


def _names(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        return z.namelist()


def test_the_archive_is_built(built):
    assert pathlib.Path(built).exists()
    assert built.endswith(".zip")


def test_everything_sits_inside_one_folder(built):
    """Unzipping must not scatter loose files across his Downloads."""
    tops = {name.split("/")[0] for name in _names(built)}
    assert tops == {package.FOLDER}, tops


def test_the_user_gets_what_he_needs(built):
    inside = {name.split("/", 1)[1] for name in _names(built)}
    for needed in ("Installer.bat", "Réduire PDF.bat", "LISEZ-MOI.txt",
                   "requirements.txt", "verify_install.py",
                   "scripts/fetch_jbig2.py", "pdfshrink/__init__.py",
                   "pdfshrink/core.py", "pdfshrink/web.py",
                   "pdfshrink/static/index.html", "pdfshrink/static/app.js",
                   "pdfshrink/static/style.css"):
        assert needed in inside, "missing from the archive: %s" % needed


def test_no_personal_document_can_ever_ship(built):
    """The whole reason this test exists."""
    offenders = [n for n in _names(built) if n.lower().endswith(".pdf")]
    assert not offenders, offenders


def test_no_binaries_ship(built):
    offenders = [n for n in _names(built)
                 if n.lower().endswith((".exe", ".dll", ".zip", ".conda"))]
    assert not offenders, offenders


def test_no_development_files_ship(built):
    inside = _names(built)
    for unwanted in ("tests/", "docs/", ".venv", "__pycache__", ".git",
                     "journal.txt", "jbig2/", ".pytest_cache"):
        offenders = [n for n in inside if unwanted in n]
        assert not offenders, "%s leaked: %s" % (unwanted, offenders)


def test_the_archive_is_small(built):
    """If this grows past a megabyte something unintended got in."""
    size = pathlib.Path(built).stat().st_size
    assert size < 1024 * 1024, "%d bytes is too big to be only the app" % size


def test_batch_files_keep_crlf_inside_the_archive(built):
    """cmd.exe mis-parses LF-only batch files; the zip must not convert."""
    with zipfile.ZipFile(built) as z:
        for name in z.namelist():
            if name.endswith(".bat"):
                data = z.read(name)
                crlf = data.count(b"\r\n")
                assert data.count(b"\n") - crlf == 0, name
                assert crlf > 0, name


def test_extracted_tree_is_runnable(built, tmp_path):
    """Extract it and confirm the engine imports from the extracted copy."""
    import subprocess

    with zipfile.ZipFile(built) as z:
        z.extractall(tmp_path)
    app = tmp_path / package.FOLDER
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); "
         "import pdfshrink.core, pdfshrink.web, pdfshrink.cli; "
         "print('imports ok')" % str(app)],
        capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "imports ok" in done.stdout


def test_allowlist_and_denylist_agree():
    """Every listed source must exist, or the archive silently ships less."""
    missing = [p for p in package.iter_sources() if not p.exists()]
    assert not missing, missing


def test_the_deny_list_actually_refuses():
    """Proven to fire, not merely present."""
    for bad in ("Réduire PDF/BA2.pdf", "Réduire PDF/uv.exe",
                "Réduire PDF/tests/test_core.py", "Réduire PDF/journal.txt",
                "Réduire PDF/pdfshrink/__pycache__/core.pyc",
                "Réduire PDF/jbig2/jbig2.exe"):
        with pytest.raises(ValueError):
            package._check(bad)


def test_adding_a_document_to_the_allowlist_fails_the_build(tmp_path,
                                                            monkeypatch):
    """The realistic mistake: someone adds a sample file to FILES."""
    monkeypatch.setattr(package, "FILES", package.FILES + ["BA2.pdf"])
    if not (ROOT / "BA2.pdf").exists():
        pytest.skip("BA2.pdf not present")
    with pytest.raises(ValueError) as caught:
        package.build(str(tmp_path))
    assert "BA2.pdf" in str(caught.value)
