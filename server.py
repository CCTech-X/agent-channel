"""agent-channel — an MCP server that lets two Claude Code agents leave each other messages.

WHAT THIS IS FOR. Two people, each driving their own Claude Code session, who need their
agents to exchange information without a human copy-pasting between windows. Each agent gets
`send_message` / `read_messages` as native tools; the transcript is an append-only log both
HUMANS can also read.

WHAT IT IS NOT. It is not live chat. A Claude Code session has no background listener — it
acts only when its human prompts it. So an exchange is: A's agent posts, B's human says
"check the channel", B's agent reads and replies. In practice this behaves like async
messaging, not like a chat room. Design around that rather than being surprised by it.

TWO TOPOLOGIES, ONE CODEBASE (pick with env vars):

  1. SHARED FILE  — both agents on the same machine, or a synced/shared folder.
     CHANNEL_LOG=/path/to/channel.jsonl
     No network, no service to keep alive, works air-gapped. Start here.

  2. HTTP RELAY   — agents on different machines.
     CHANNEL_RELAY=http://host:8765
     Run `python relay.py` on whichever host both can reach.

Identity is declared, NOT verified: CHANNEL_AGENT is whatever the operator configures. This
is a coordination tool between two cooperating people, not an authenticated system. Do not
put secrets in it and do not treat an author field as proof of anything.

Run:
  pip install "mcp[cli]"
  CHANNEL_AGENT=neptune CHANNEL_LOG=./channel.jsonl python server.py
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

# MCP Python SDK v2 renamed FastMCP -> MCPServer and moved it out of mcp.server.fastmcp.
# Import both ways so this works on either generation of the SDK rather than pinning one.
try:
    from mcp.server.mcpserver import MCPServer as _Server        # SDK >= 2.0
except ImportError:                                              # pragma: no cover
    from mcp.server.fastmcp import FastMCP as _Server            # SDK 1.x

AGENT = os.getenv("CHANNEL_AGENT", "unknown").strip() or "unknown"
LOG = Path(os.getenv("CHANNEL_LOG", "./channel.jsonl")).expanduser()
RELAY = os.getenv("CHANNEL_RELAY", "").strip()

mcp = _Server("agent-channel")


# ── storage ────────────────────────────────────────────────────────────────────
def _append(rec: dict[str, Any]) -> None:
    if RELAY:
        import urllib.request
        req = urllib.request.Request(
            f"{RELAY.rstrip('/')}/messages",
            data=json.dumps(rec).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
        return
    LOG.parent.mkdir(parents=True, exist_ok=True)
    # Append-only. Concurrent appends of one short line are atomic enough on both
    # Windows and Linux for two writers; this is a two-person channel, not a queue.
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_all() -> list[dict[str, Any]]:
    if RELAY:
        import urllib.request
        with urllib.request.urlopen(f"{RELAY.rstrip('/')}/messages", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue          # a torn line from a concurrent append; skip, don't crash
    return out


# ── tools ──────────────────────────────────────────────────────────────────────
@mcp.tool()
def send_message(body: str, to: str = "all", topic: str = "") -> str:
    """Post a message to the shared channel for the other agent to read.

    The other agent will NOT see this until its human prompts it to check — there is no
    push. Say what you need in full rather than expecting a quick back-and-forth.

    Args:
        body:  the message. Be self-contained: state context, not just a conclusion.
        to:    recipient agent name, or "all".
        topic: optional short subject, useful for filtering later.
    """
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "from": AGENT,
        "to": to,
        "topic": topic,
        "body": body,
    }
    _append(rec)
    return f"posted as {AGENT} -> {to} ({len(body)} chars)"


@mcp.tool()
def read_messages(since: str = "", limit: int = 30, unread_only: bool = True) -> str:
    """Read the channel.

    Args:
        since:       ISO timestamp; only messages strictly after it. Empty = from the start.
        limit:       max messages to return (newest kept if truncated).
        unread_only: when True, hide this agent's own messages so you see only what the
                     other side said. Set False to see the whole transcript in order.
    """
    msgs = _read_all()
    if since:
        msgs = [m for m in msgs if m.get("ts", "") > since]
    if unread_only:
        msgs = [m for m in msgs if m.get("from") != AGENT]
    if not msgs:
        return "(no messages)" + ("" if not since else f" after {since}")
    msgs = msgs[-limit:]
    lines = []
    for m in msgs:
        head = f"[{m.get('ts')}] {m.get('from')} -> {m.get('to')}"
        if m.get("topic"):
            head += f"  ({m['topic']})"
        lines.append(head + "\n" + (m.get("body") or ""))
    return "\n\n".join(lines)


@mcp.tool()
def channel_status() -> str:
    """Who is on the channel, how many messages, and which backend is in use."""
    msgs = _read_all()
    who: dict[str, int] = {}
    for m in msgs:
        who[m.get("from", "?")] = who.get(m.get("from", "?"), 0) + 1
    backend = f"relay {RELAY}" if RELAY else f"file {LOG}"
    parts = [f"me       : {AGENT}", f"backend  : {backend}", f"messages : {len(msgs)}"]
    if msgs:
        parts.append(f"last     : {msgs[-1].get('ts')} from {msgs[-1].get('from')}")
    parts.append("agents   : " + (", ".join(f"{k}({v})" for k, v in who.items()) or "none yet"))
    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run()
