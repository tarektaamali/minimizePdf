"""The encoder is fetched, never redistributed.

Nothing here downloads anything: the network calls are patched. What is
tested is that a package failing its checksum is rejected outright, which
is the whole point of pinning them.
"""

import hashlib
import io
import pathlib
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

import fetch_jbig2  # noqa: E402


def _fake_conda(payload_name, payload):
    """Build a .conda file: a zip holding a zstd-compressed tar."""
    import zstandard

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(payload_name)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    compressed = zstandard.ZstdCompressor().compress(buf.getvalue())

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("pkg-test-1.0.tar.zst", compressed)
        z.writestr("info-test-1.0.tar.zst", compressed)
    return out.getvalue()


def test_every_package_is_pinned_with_a_checksum():
    assert fetch_jbig2.PACKAGES, "no packages pinned"
    for name, digest in fetch_jbig2.PACKAGES:
        assert name.endswith(".conda"), name
        assert len(digest) == 32, "%s: %s" % (name, digest)
        int(digest, 16)


def test_jbig2enc_itself_is_in_the_list():
    names = [n for n, _ in fetch_jbig2.PACKAGES]
    assert any(n.startswith("jbig2enc-") for n in names), names


def test_a_good_package_is_extracted(tmp_path, monkeypatch):
    blob = _fake_conda("Library/bin/jbig2.exe", b"binary contents")
    digest = hashlib.md5(blob).hexdigest()
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: blob)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES", [("fake-1.0-h0.conda", digest)])

    fetch_jbig2.fetch(str(tmp_path))
    landed = tmp_path / "jbig2.exe"
    assert landed.exists()
    assert landed.read_bytes() == b"binary contents"


def test_a_tampered_package_is_refused(tmp_path, monkeypatch):
    blob = _fake_conda("Library/bin/jbig2.exe", b"binary contents")
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: blob)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES",
                        [("fake-1.0-h0.conda", "0" * 32)])

    with pytest.raises(fetch_jbig2.ChecksumError) as caught:
        fetch_jbig2.fetch(str(tmp_path))
    assert "fake-1.0-h0.conda" in str(caught.value)
    assert not list(tmp_path.glob("*.exe")), "a bad package left files behind"


def test_only_library_bin_is_extracted(tmp_path, monkeypatch):
    """conda packages carry headers, licences and pkgconfig we do not want."""
    blob = _fake_conda("Library/include/leptonica/allheaders.h", b"noise")
    digest = hashlib.md5(blob).hexdigest()
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: blob)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES", [("fake-1.0-h0.conda", digest)])

    fetch_jbig2.fetch(str(tmp_path))
    assert not list(tmp_path.rglob("*.h")), "extracted files outside Library/bin"


def test_unrelated_executables_are_not_installed(tmp_path, monkeypatch):
    """Library/bin also carries cjpeg, fax2ps and the gif tools. None of
    them belong next to an application a non-technical person runs."""
    import hashlib as _h

    keep = _fake_conda("Library/bin/jbig2.exe", b"encoder")
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: keep)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES",
                        [("fake-1.0-h0.conda", _h.md5(keep).hexdigest())])
    fetch_jbig2.fetch(str(tmp_path))
    assert (tmp_path / "jbig2.exe").exists()

    drop = _fake_conda("Library/bin/cjpeg.exe", b"not wanted")
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: drop)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES",
                        [("fake-1.0-h0.conda", _h.md5(drop).hexdigest())])
    fetch_jbig2.fetch(str(tmp_path))
    assert not (tmp_path / "cjpeg.exe").exists()


def test_libraries_are_installed(tmp_path, monkeypatch):
    """The DLLs are not optional: jbig2.exe cannot start without them."""
    import hashlib as _h
    blob = _fake_conda("Library/bin/leptonica-1.87.0.dll", b"library")
    monkeypatch.setattr(fetch_jbig2, "download", lambda url: blob)
    monkeypatch.setattr(fetch_jbig2, "PACKAGES",
                        [("fake-1.0-h0.conda", _h.md5(blob).hexdigest())])
    fetch_jbig2.fetch(str(tmp_path))
    assert (tmp_path / "leptonica-1.87.0.dll").exists()
