import http.client
import json
import threading
import unittest

import app
from helpers import example_text
import scoring


class LocalAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.LocalServer(0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, *, host=None, origin=None, token=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        headers = {"Host": host or f"localhost:{self.port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json", "Origin": origin or f"http://localhost:{self.port}",
                            "X-Session-Token": self.server.token if token is None else token})
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, response.getheader("Content-Type", ""), data

    def post(self, path, body, **kw):
        status, _, data = self.request("POST", path, body, **kw)
        return status, json.loads(data)

    def test_page_assets_and_security_headers(self):
        status, kind, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), page)
        for path in ("/app.js", "/app.css", "/api/defaults", "/api/example", "/templates/settings.csv"):
            self.assertEqual(self.request("GET", path)[0], 200, path)
        self.assertEqual(self.request("GET", "/../app.py")[0], 404)
        self.assertEqual(self.request("GET", "/", host="evil.example")[0], 403)

    def test_posts_need_origin_and_token(self):
        body = {"survey": example_text()}
        self.assertEqual(self.post("/api/analyse", body, token="wrong")[0], 403)
        self.assertEqual(self.post("/api/analyse", body, origin="http://evil.example")[0], 403)
        status, data = self.post("/api/analyse", body)
        self.assertEqual(status, 200)
        self.assertEqual(data["counts"], {"internationals": 20, "locals": 28})
        self.assertEqual(len(data["impact"]), len(data["rules"]))

    def test_compute_export_and_import(self):
        settings = dict(scoring.default_settings(), weight_hobbies=6)
        _, analysed = self.post("/api/analyse", {"survey": example_text()})
        status, result = self.post("/api/compute", {"survey": example_text(), "settings": settings,
                                                    "rules": analysed["rules"], "iteration": 3})
        self.assertEqual(status, 200)
        self.assertEqual(result["iteration"], 3)
        self.assertTrue(result["result_csv"].startswith("student_id,local_id"))
        _, exported = self.post("/api/export", {"settings": settings, "rules": analysed["rules"]})
        _, imported = self.post("/api/import-settings", {"csv": exported["settings_csv"]})
        self.assertEqual(imported["settings"], settings)
        _, rules = self.post("/api/import-rules", {"csv": exported["rules_csv"], "survey": example_text()})
        self.assertEqual([r["id"] for r in rules["rules"]], [r["id"] for r in analysed["rules"]])
        status, error = self.post("/api/compute", {"survey": example_text(), "settings": {"weight_age": 0}})
        self.assertEqual(status, 422)
        self.assertIn("weight_age", error["error"])
        self.assertEqual(self.post("/api/analyse", {"survey": ""})[0], 422)


if __name__ == "__main__":
    unittest.main()
