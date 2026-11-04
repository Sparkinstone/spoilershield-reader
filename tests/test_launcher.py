"""Tests for the one-click launcher's readiness logic."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from scripts import launch as launcher
from scripts.launch import build_url, is_app_ready, wait_for_ready


class FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9



def test_build_url_maps_wildcard_hosts_to_localhost():
    assert build_url("0.0.0.0", 8000) == "http://127.0.0.1:8000"
    assert build_url("::", 8000) == "http://127.0.0.1:8000"
    assert build_url("127.0.0.1", 8123) == "http://127.0.0.1:8123"
    assert build_url("192.168.1.5", 8000) == "http://192.168.1.5:8000"


def test_wait_for_ready_returns_true_once_probe_succeeds():
    state = {"now": 0.0}
    answers = iter([False, False, True])

    def clock():
        return state["now"]

    def sleep(seconds):
        state["now"] += seconds

    assert (
        wait_for_ready(
            "http://127.0.0.1:8000",
            timeout=5,
            interval=1,
            probe=lambda _url: next(answers),
            clock=clock,
            sleep=sleep,
        )
        is True
    )


def test_wait_for_ready_returns_false_on_timeout():
    state = {"now": 0.0}

    def clock():
        return state["now"]

    def sleep(seconds):
        state["now"] += seconds

    assert (
        wait_for_ready(
            "http://127.0.0.1:8000",
            timeout=2,
            interval=1,
            probe=lambda _url: False,
            clock=clock,
            sleep=sleep,
        )
        is False
    )


def test_is_app_ready_checks_the_ping_endpoint():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            body = b'{"status": "ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - stdlib API
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert is_app_ready(f"http://127.0.0.1:{server.server_port}")
        assert not is_app_ready("http://127.0.0.1:1", timeout=0.2)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_is_app_ready_rejects_an_unrelated_service():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - stdlib API
            body = b"<html>some other app</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - stdlib API
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert not is_app_ready(f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_main_opens_browser_only_after_the_server_is_ready(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "is_app_ready", lambda url, timeout=1.0: False)
    monkeypatch.setattr(launcher, "wait_for_ready", lambda url, timeout: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: FakeProcess(0))

    assert launcher.main(["--port", "8123"]) == 0
    assert opened == ["http://127.0.0.1:8123"]


def test_main_does_not_open_browser_when_startup_fails(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "is_app_ready", lambda url, timeout=1.0: False)
    monkeypatch.setattr(launcher, "wait_for_ready", lambda url, timeout: False)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *a, **k: FakeProcess(1))

    assert launcher.main(["--port", "8123"]) == 1
    assert opened == []


def test_main_reuses_an_already_running_instance(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "is_app_ready", lambda url, timeout=1.0: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url) or True)

    def fail_popen(*args, **kwargs):
        raise AssertionError("should not start a second server")

    monkeypatch.setattr(launcher.subprocess, "Popen", fail_popen)

    assert launcher.main(["--port", "8123"]) == 0
    assert opened == ["http://127.0.0.1:8123"]
