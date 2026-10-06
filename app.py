"""Local-only browser interface: interact (weights, must-haves), compute, review, iterate, save."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit
import webbrowser

import engine
import rules as rulebook
import scoring
from survey import decode

ASSETS = Path(__file__).resolve().parent
STATIC = {"/app.js": ("app.js", "text/javascript; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
MAX_REQUEST_BYTES = 10 * 1024 * 1024


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8766):
        # Never bind to the LAN, including in a packaged application.
        super().__init__(("127.0.0.1", port), RequestHandler)
        self.token = secrets.token_urlsafe(32)
        self.run_lock = threading.Lock()
        self.origin = f"http://localhost:{self.server_port}"
        self.allowed_hosts = {f"localhost:{self.server_port}", f"127.0.0.1:{self.server_port}"}


def settings_of(data) -> dict:
    return scoring.validate_settings(data.get("settings") or {})


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "PerfectMatchLFP26"
    sys_version = ""

    def log_message(self, *_):
        pass

    def reply(self, status, content, content_type="application/json; charset=utf-8"):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
        elif isinstance(content, str):
            content = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'none'")
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def valid_host(self):
        if self.headers.get("Host", "").lower() not in self.server.allowed_hosts:
            self.reply(403, {"error": "Open this application using its localhost address."})
            return False
        return True

    def do_GET(self):
        if not self.valid_host():
            return
        path = urlsplit(self.path).path
        if path == "/":
            page = (ASSETS / "static" / "index.html").read_text(encoding="utf-8")
            self.reply(200, page.replace("__SESSION_TOKEN__", self.server.token), "text/html; charset=utf-8")
        elif path in STATIC:
            name, kind = STATIC[path]
            self.reply(200, (ASSETS / "static" / name).read_bytes(), kind)
        elif path == "/api/defaults":
            self.reply(200, {"settings": scoring.default_settings(),
                             "spec": [{"name": n, "default": d, "type": t.__name__, "min": lo, "max": hi,
                                       "description": text} for n, (d, t, lo, hi, text) in scoring.SETTINGS.items()],
                             "criteria": scoring.CRITERIA, "grades": scoring.GRADES, "kinds": rulebook.KINDS})
        elif path == "/api/example":
            self.reply(200, {"name": "survey_example.csv",
                             "survey": decode((ASSETS / "examples" / "survey_example.csv").read_bytes())})
        elif path == "/templates/settings.csv":
            self.reply(200, scoring.settings_to_csv(scoring.default_settings()), "text/csv; charset=utf-8")
        elif path == "/favicon.ico":
            self.reply(204, b"", "image/x-icon")
        else:
            self.reply(404, {"error": "Page not found."})

    def do_POST(self):
        # Read the body before any refusal: closing a socket with unread data resets the connection
        # on Windows, and the page would show "cannot reach the app" instead of the refusal message.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.close_connection = True
            self.reply(413, {"error": "The files are too large (10 MB limit in total)."})
            return
        try:
            self.connection.settimeout(30)
            body = self.rfile.read(length)
        except OSError:
            return
        if not self.valid_host():
            return
        if self.headers.get("Origin", "") not in {f"http://{host}" for host in self.server.allowed_hosts}:
            self.reply(403, {"error": "Only this application's local page can send data."})
            return
        if not secrets.compare_digest(self.headers.get("X-Session-Token", ""), self.server.token):
            self.reply(403, {"error": "This session has changed. Reload the page and try again."})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.reply(415, {"error": "Expected JSON."})
            return
        try:
            data = json.loads(body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
        except (ValueError, UnicodeError, OSError) as exc:
            self.reply(400, {"error": f"Could not read the request: {exc}"})
            return
        path = urlsplit(self.path).path
        actions = {"/api/analyse": self.analyse, "/api/impact": self.impact, "/api/compute": self.compute,
                   "/api/import-settings": self.import_settings, "/api/import-rules": self.import_rules,
                   "/api/export": self.export, "/api/stop": self.stop}
        if path not in actions:
            self.reply(404, {"error": "Unknown action."})
            return
        try:
            self.reply(200, actions[path](data))
        except (ValueError, RuntimeError, OSError) as exc:
            self.reply(422, {"error": str(exc)})
        except Exception:
            self.reply(500, {"error": "The action could not finish. Restart the app and try again."})

    @staticmethod
    def survey_of(data) -> str:
        survey = data.get("survey")
        if not isinstance(survey, str) or not survey.strip():
            raise ValueError("Choose the survey CSV first.")
        return survey

    def analyse(self, data):
        return engine.analyse(self.survey_of(data), settings_of(data), data.get("rules"))

    def impact(self, data):
        return {"impact": engine.impact(self.survey_of(data), settings_of(data), data.get("rules") or [])}

    def compute(self, data):
        if not self.server.run_lock.acquire(blocking=False):
            raise ValueError("A computation is still running. Wait for it to finish.")
        try:
            pairs = lambda key: [tuple(map(str, p))[:2] for p in data.get(key) or [] if isinstance(p, list) and len(p) == 2]
            return engine.compute(self.survey_of(data), settings_of(data), data.get("rules") or [],
                                  pairs("locks"), pairs("forbids"), iteration=int(data.get("iteration") or 1),
                                  survey_name=str(data.get("survey_name") or "survey.csv")[:200])
        finally:
            self.server.run_lock.release()

    def import_settings(self, data):
        return {"settings": scoring.settings_from_csv(str(data.get("csv") or ""))}

    def import_rules(self, data):
        survey, settings = self.survey_of(data), settings_of(data)
        ids = set(engine.load(survey, settings)[1])
        rule_list = [rulebook.to_dict(r) for r in rulebook.rules_from_csv(str(data.get("csv") or ""), ids)]
        return {"rules": rule_list, "impact": engine.impact(survey, settings, rule_list)}

    def export(self, data):
        rule_list = [rulebook.from_dict(r) for r in data.get("rules") or []]
        return {"settings_csv": scoring.settings_to_csv(settings_of(data)),
                "rules_csv": rulebook.rules_to_csv(rule_list),
                "rules": [rulebook.to_dict(r) for r in rule_list]}

    def stop(self, _):
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        return {"stopped": True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766, help="Local port; 0 selects an available port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the default browser")
    args = parser.parse_args(argv)
    try:
        try:
            server = LocalServer(args.port)
        except OSError:
            if args.port != 8766:
                raise
            server = LocalServer(0)
        if sys.stdout is not None:
            print(f"PerfectMatchLFP26 is running at {server.origin}", flush=True)
        if not args.no_browser:
            webbrowser.open(server.origin)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except Exception as exc:
        message = f"PerfectMatchLFP26 could not start: {exc}"
        if getattr(sys, "frozen", False) and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "PerfectMatchLFP26", 16)
        else:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
