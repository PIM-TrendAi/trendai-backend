"""
Local reverse proxy — stdlib only, no extra packages needed.
  /api/*  and  /admin/*  → Django  :8000
  everything else         → n8n     :5678

Point ngrok at port 9000 so both services share one tunnel.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.error import URLError
import urllib.parse

DJANGO_BASE = "http://127.0.0.1:8000"
N8N_BASE    = "http://127.0.0.1:5678"
LISTEN_PORT = 9000

SKIP_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {self.address_string()} {fmt % args}")

    def _target(self):
        p = self.path
        if p.startswith("/api/") or p.startswith("/admin/"):
            return DJANGO_BASE
        return N8N_BASE

    def do_request(self):
        url = self._target() + self.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in SKIP_HEADERS}

        req = Request(url, data=body, headers=headers, method=self.command)
        try:
            with urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in SKIP_HEADERS:
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except URLError as e:
            self.send_error(502, str(e))

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_request


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", LISTEN_PORT), ProxyHandler)
    print(f"Reverse proxy listening on port {LISTEN_PORT}")
    print(f"  /api/* /admin/*  → Django  {DJANGO_BASE}")
    print(f"  everything else  → n8n     {N8N_BASE}")
    server.serve_forever()

