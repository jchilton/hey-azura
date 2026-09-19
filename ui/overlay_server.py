import os
import json
import time
import queue
import logging
import threading
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).resolve().parent
STAR_PNG_PATH = CURRENT_DIR / "azuras-star.png"
OVERLAY_HTML_PATH = CURRENT_DIR / "overlay.html"

class OverlayServer:
    """Threaded HTTP + SSE server for broadcasting Azura's animation states to OBS / browser."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8035):
        self.host = host
        self.port = port
        self.current_state = "idle"
        self._clients: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer = None
        self._thread: threading.Thread = None
        self._running = False

    def start(self):
        """Start the overlay server in a background daemon thread."""
        server_instance = self
        self._running = True

        class OverlayHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Suppress noisy HTTP request logging
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path in ["/", "/overlay.html", "/index.html"]:
                    self._serve_file(OVERLAY_HTML_PATH, "text/html; charset=utf-8")
                elif path == "/azuras-star.png":
                    self._serve_file(STAR_PNG_PATH, "image/png")
                elif path == "/events":
                    self._serve_sse()
                elif path == "/state":
                    qs = parse_qs(parsed.query)
                    new_state = qs.get("name", [None])[0] or qs.get("state", [None])[0]
                    if new_state:
                        server_instance.set_state(new_state)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"current_state": server_instance.current_state}).encode())
                else:
                    self.send_error(404, "Not Found")

            def _serve_file(self, filepath: Path, content_type: str):
                if not filepath.exists():
                    self.send_error(404, f"File not found: {filepath.name}")
                    return
                with open(filepath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)

            def _serve_sse(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                # Send initial state immediately
                initial_msg = f"data: {json.dumps({'state': server_instance.current_state})}\n\n"
                try:
                    self.wfile.write(initial_msg.encode())
                    self.wfile.flush()
                except Exception:
                    return

                # Register client queue
                q = queue.Queue()
                with server_instance._lock:
                    server_instance._clients.append(q)

                try:
                    while server_instance._running:
                        try:
                            msg = q.get(timeout=1.0)
                            if msg is None:  # Shutdown sentinel
                                break
                            self.wfile.write(msg.encode())
                            self.wfile.flush()
                        except queue.Empty:
                            # Send heartbeat comment to keep connection alive
                            try:
                                self.wfile.write(b": ping\n\n")
                                self.wfile.flush()
                            except Exception:
                                break
                except (BrokenPipeError, ConnectionResetError, Exception):
                    pass
                finally:
                    with server_instance._lock:
                        if q in server_instance._clients:
                            server_instance._clients.remove(q)

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), OverlayHandler)
            self._server.daemon_threads = True
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"Overlay server listening at http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start OverlayServer on port {self.port}: {e}")

    def set_state(self, state: str):
        """Update animation state and broadcast to all connected browsers/OBS."""
        valid_states = ["idle", "listening", "researching", "speaking"]
        target_state = state.lower().strip()
        if target_state not in valid_states:
            target_state = "idle"

        with self._lock:
            self.current_state = target_state
            payload = f"data: {json.dumps({'state': self.current_state})}\n\n"
            dead_clients = []
            for q in self._clients:
                try:
                    q.put_nowait(payload)
                except Exception:
                    dead_clients.append(q)
            for d in dead_clients:
                if d in self._clients:
                    self._clients.remove(d)

    def stop(self):
        """Immediately shut down overlay server without blocking."""
        self._running = False
        with self._lock:
            for q in self._clients:
                try:
                    q.put_nowait(None)
                except Exception:
                    pass
            self._clients.clear()
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass

if __name__ == "__main__":
    server = OverlayServer(port=8035)
    server.start()
    print("\n✦ Azura OBS Overlay Webpage running at: http://localhost:8035")
    print("  - State API: http://localhost:8035/state?name=listening|researching|speaking|idle")
    print("  - Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("\nOverlay server stopped.")
