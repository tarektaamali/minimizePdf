"""Flask layer. One page, one job at a time, localhost only.

The API returns machine-readable reason codes; every French sentence lives
in the page, so wording changes never touch the server.

The launcher runs pythonw, which has no console, so anything printed
reaches nobody. Everything worth diagnosing goes to journal.txt beside the
application instead - the file LISEZ-MOI tells the user to send on.
"""

import logging
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
LOG = logging.getLogger("pdfshrink")


def journal_path():
    override = os.environ.get("PDFSHRINK_JOURNAL")
    if override:
        return override
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "journal.txt")


def configure_logging():
    """Send the log to a file, because pythonw discards stderr."""
    path = journal_path()
    for existing in list(LOG.handlers):
        LOG.removeHandler(existing)
        existing.close()
    handler = logging.FileHandler(path, encoding="utf8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    return path


def _set(job_id, **fields):
    with LOCK:
        JOBS[job_id].update(fields)


def _run(job_id, src, dst, target, original_name):
    def progress(stage, done, total):
        _set(job_id, stage=stage, done=done, total=total)

    try:
        result = shrink(src, dst, target, progress=progress)
    except Exception:
        LOG.exception("shrink failed for %r", original_name)
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
        LOG.info("%s: %d -> %d bytes at %s dpi",
                 original_name, result.before, result.size, result.dpi)
        _set(job_id, state="done", size=result.size, dpi=result.dpi,
             saved=saved, **common)
    else:
        LOG.info("%s: refused (%s), best safe %s",
                 original_name, result.reason, result.best_safe_size)
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
        return jsonify({"ok": True, "bytes": value,
                        "label": describe_size(value)})

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
            if not job.get("best_safe_size"):
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

    configure_logging()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    url = "http://127.0.0.1:%d/" % port
    LOG.info("starting on %s", url)
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print("Réduire PDF : %s" % url)
    create_app().run(host="127.0.0.1", port=port, threaded=True)


if __name__ == "__main__":
    serve()
