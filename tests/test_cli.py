import io
import json
import sys

from pdfshrink.cli import main


def test_json_output_on_success(digital_pdf, tmp_path, capsys):
    dst = str(tmp_path / "out.pdf")
    code = main([digital_pdf, dst, "--target", "1 Mo", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["output"] == dst


def test_json_output_on_refusal(colour_scan_pdf, tmp_path, capsys):
    """A bare --target is read as Ko, so 1 is the smallest expressible
    budget; a colour scan cannot reach it and must be refused."""
    dst = str(tmp_path / "out.pdf")
    code = main([colour_scan_pdf, dst, "--target", "1", "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["reason"] in ("too_large", "already_minimal")
    assert payload["size"] is None


def test_bad_target_is_a_clean_error(digital_pdf, tmp_path, capsys):
    code = main([digital_pdf, str(tmp_path / "o.pdf"), "--target", "banane"])
    assert code == 2
    assert "banane" in capsys.readouterr().err


def test_refuses_to_overwrite_input(digital_pdf, capsys):
    code = main([digital_pdf, digital_pdf, "--target", "1 Mo"])
    assert code == 2


def test_missing_input_is_a_clean_error(tmp_path, capsys):
    code = main([str(tmp_path / "nope.pdf"), str(tmp_path / "o.pdf")])
    assert code == 2
    assert "nope.pdf" in capsys.readouterr().err


def test_json_shape_is_complete(digital_pdf, tmp_path, capsys):
    """The web layer reads this instead of parsing printed text."""
    dst = str(tmp_path / "out.pdf")
    main([digital_pdf, dst, "--target", "1 Mo", "--json"])
    payload = json.loads(capsys.readouterr().out)
    for key in ("ok", "before", "size", "dpi", "check", "best_safe_size",
                "reason", "output"):
        assert key in payload, key


def test_output_survives_a_cp1252_console(digital_pdf, tmp_path, monkeypatch):
    """format_size emits U+202F. A French Windows console is cp1252, which
    cannot encode it, and printing a size would raise UnicodeEncodeError."""
    raw = io.BytesIO()
    monkeypatch.setattr(
        sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", newline=""))
    code = main([digital_pdf, str(tmp_path / "o.pdf"), "--target", "1 Mo"])
    sys.stdout.flush()
    assert code == 0
    assert b"Ko" in raw.getvalue() or b"Mo" in raw.getvalue()


def test_already_minimal_is_explained(colour_scan_pdf, tmp_path, capsys,
                                      monkeypatch):
    """A refusal with no worthwhile fallback must still say something."""
    import pdfshrink.cli as cli
    from pdfshrink.core import Result

    def minimal(src, dst, target, min_dpi=100, progress=None):
        return Result(False, 1000, None, reason="already_minimal")

    monkeypatch.setattr(cli, "shrink", minimal)
    code = main([colour_scan_pdf, str(tmp_path / "o.pdf"), "--target", "64"])
    assert code == 1
    out = capsys.readouterr().out
    assert "already" in out.lower() or "smaller" in out.lower()


def test_module_entry_point_runs(digital_pdf, tmp_path):
    """python -m pdfshrink is the documented entry point."""
    import subprocess
    done = subprocess.run(
        [sys.executable, "-m", "pdfshrink", digital_pdf,
         str(tmp_path / "o.pdf"), "--target", "1 Mo", "--json"],
        capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["ok"] is True
