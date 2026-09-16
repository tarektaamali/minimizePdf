import io
import os
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


def _upload(client, path, target, name="doc.pdf"):
    with open(path, "rb") as fh:
        data = {"file": (io.BytesIO(fh.read()), name), "target": target}
    return client.post("/api/shrink", data=data,
                       content_type="multipart/form-data").get_json()["job"]


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


def test_rejects_non_pdf(client, tmp_path):
    junk = tmp_path / "x.pdf"
    junk.write_bytes(b"not a pdf")
    data = _wait(client, _upload(client, str(junk), "200 Ko"))
    assert data["state"] == "error"


def test_successful_shrink_offers_download(client, digital_pdf):
    job = _upload(client, digital_pdf, "1 Mo")
    data = _wait(client, job)
    assert data["state"] == "done"
    assert client.get("/api/download/%s" % job).status_code == 200
    assert os.path.exists(data["saved"])


def test_refusal_has_no_download_until_accepted(client, colour_scan_pdf):
    """A bare target is read as Ko, so 1 is the smallest expressible budget.
    A colour scan floors well above it and must be refused."""
    job = _upload(client, colour_scan_pdf, "1")
    data = _wait(client, job)
    assert data["state"] == "refused"
    assert data["reason"] == "too_large"
    assert data["best_safe_size"] > 1024
    assert client.get("/api/download/%s" % job).status_code == 409
    assert client.post("/api/keep/%s" % job).status_code == 200
    assert client.get("/api/download/%s" % job).status_code == 200


def test_job_reports_progress_stages(client, colour_scan_pdf):
    data = _wait(client, _upload(client, colour_scan_pdf, "20 Ko"))
    assert data["state"] == "done"
    assert data["pages"] == 2
    assert data["kind"] == "raster"


def test_saved_file_never_replaces_an_existing_one(client, digital_pdf):
    first = _wait(client, _upload(client, digital_pdf, "1 Mo"))["saved"]
    second = _wait(client, _upload(client, digital_pdf, "1 Mo"))["saved"]
    assert first != second
    assert os.path.exists(first) and os.path.exists(second)


def test_unknown_job_is_not_found(client):
    assert client.get("/api/job/nope").status_code == 404
    assert client.get("/api/download/nope").status_code == 404


def test_the_server_writes_a_journal(tmp_path, monkeypatch):
    """LISEZ-MOI tells the user to send journal.txt, so it must exist.
    pythonw has no console, so a traceback reaches nobody without it."""
    from pdfshrink import web
    journal = tmp_path / "journal.txt"
    monkeypatch.setenv("PDFSHRINK_JOURNAL", str(journal))
    web.configure_logging()
    web.LOG.warning("ceci est un test")
    assert journal.exists()
    assert "ceci est un test" in journal.read_text(encoding="utf8")
