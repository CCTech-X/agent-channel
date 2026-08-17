"""Optional HTTP relay for agent-channel — only needed when the two agents are on
DIFFERENT machines. If you share a filesystem or a synced folder, skip this entirely and
point both servers at the same CHANNEL_LOG.

Deliberately dependency-free (stdlib http.server) so it runs on a bare Windows or Ubuntu box
with no pip install. It is a two-person coordination relay: no auth, no TLS, no rate limit.
Bind it to a LAN address you trust, never to a public interface.

  python relay.py                 # 0.0.0.0:8765, log ./channel.jsonl
  RELAY_PORT=9000 python relay.py

Endpoints:
  GET  /messages   -> JSON array of every message
  POST /messages   -> append one message (JSON object)
  GET  /           -> a plain HTML transcript, so BOTH HUMANS can watch it in a browser
"""
from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LOG = Path(os.getenv("CHANNEL_LOG", "./channel.jsonl")).expanduser()
PORT = int(os.getenv("RELAY_PORT", "8765"))


def read_all():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


PAGE_HEAD = """<!doctype html><meta charset="utf-8">
<title>agent-channel</title>
<meta http-equiv="refresh" content="10">
<style>
 body{font:14px/1.55 ui-monospace,Consolas,monospace;margin:0;padding:24px;
      background:#12141a;color:#e6e8ee}
 h1{font-size:15px;letter-spacing:.08em;text-transform:uppercase;color:#8b93a7;
    font-weight:600;margin:0 0 18px}
 .m{border-left:3px solid #2f3646;padding:10px 0 10px 14px;margin:0 0 16px}
 .h{color:#8b93a7;font-size:12px;margin-bottom:5px}
 .b{white-space:pre-wrap}
 .empty{color:#6b7280}
</style>
<h1>agent-channel &mdash; %d message(s), refreshes every 10s</h1>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                                        # noqa: N802
        msgs = read_all()
        if self.path.startswith("/messages"):
            self._send(200, json.dumps(msgs, ensure_ascii=False).encode("utf-8"))
            return
        parts = [PAGE_HEAD % len(msgs)]
        if not msgs:
            parts.append('<p class="empty">no messages yet</p>')
        for m in msgs:
            parts.append(
                '<div class="m"><div class="h">%s &nbsp;%s &rarr; %s%s</div>'
                '<div class="b">%s</div></div>' % (
                    html.escape(str(m.get("ts", ""))),
                    html.escape(str(m.get("from", "?"))),
                    html.escape(str(m.get("to", "all"))),
                    (" &nbsp;(" + html.escape(str(m["topic"])) + ")") if m.get("topic") else "",
                    html.escape(str(m.get("body", ""))),
                ))
        self._send(200, "".join(parts).encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):                                       # noqa: N802
        if not self.path.startswith("/messages"):
            self._send(404, b'{"error":"not found"}')
            return
        n = int(self.headers.get("Content-Length", "0"))
        try:
            rec = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:                                    # noqa: BLE001
            self._send(400, b'{"error":"bad json"}')
            return
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._send(200, b'{"ok":true}')

    def log_message(self, *a):                               # quieter console
        pass


if __name__ == "__main__":
    print(f"agent-channel relay on 0.0.0.0:{PORT}, log {LOG.resolve()}")
    print(f"  humans:  http://<this-host>:{PORT}/")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
