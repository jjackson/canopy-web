import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from canopy_runner.client import Client, ClientError


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        assert self.headers["Authorization"] == "Bearer tok"
        if self.path.endswith("/claim"):
            if _Handler.claim_empty:
                self.send_response(204); self.end_headers(); return
            body = json.dumps({"id": "t-1", "status": "claimed"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.endswith("/heartbeat"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "online"}')
            return
        self.send_response(500); self.end_headers()

    def log_message(self, *a):  # quiet
        pass


@pytest.fixture()
def server():
    _Handler.claim_empty = False
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_claim_returns_turn(server):
    c = Client(server, "tok")
    turn = c.claim("r-1")
    assert turn["id"] == "t-1"


def test_claim_returns_none_on_204(server):
    _Handler.claim_empty = True
    c = Client(server, "tok")
    assert c.claim("r-1") is None


def test_error_raises(server):
    c = Client(server, "tok")
    with pytest.raises(ClientError):
        c.post_events("t-1", [{"kind": "status", "payload": {}}])  # handler 500s unknown paths
