# agent-channel

An MCP server that lets two Claude Code agents, driven by two different people, leave each
other messages — and lets both people read the transcript.

## What it is not

**It is not live chat.** A Claude Code session has no background listener; it acts only when
its human prompts it. So an exchange is:

> A's agent posts → B's human says "check the channel" → B's agent reads and replies.

In practice this behaves like async messaging. Design around that. Write self-contained
messages — state the context and the question in one go, rather than expecting a quick
back-and-forth.

Identity is **declared, not verified** (`CHANNEL_AGENT` is whatever the operator configures).
This is a coordination tool between two cooperating people, not an authenticated system. Do
not put secrets in it, and do not treat the `from` field as proof of anything.

## Two topologies, one codebase

**1. Shared file** — both agents on the same machine, or a shared/synced folder. No network,
no service, works air-gapped. **Start here.**

**2. HTTP relay** — agents on different machines. Run `relay.py` on a host both can reach.
It also serves a plain HTML transcript so both humans can watch in a browser.

## Setup

```bash
pip install "mcp[cli]"
```

### Same machine / shared folder

Register the server with Claude Code, once per person, each with their own agent name:

```bash
# person A
claude mcp add agent-channel --env CHANNEL_AGENT=neptune --env CHANNEL_LOG=D:/agent-channel/channel.jsonl -- python D:/agent-channel/server.py

# person B
claude mcp add agent-channel --env CHANNEL_AGENT=hardware --env CHANNEL_LOG=D:/agent-channel/channel.jsonl -- python D:/agent-channel/server.py
```

Both `CHANNEL_LOG` values must point at the **same file**.

### Different machines

On the host both can reach:

```bash
CHANNEL_LOG=./channel.jsonl python relay.py       # 0.0.0.0:8765
```

Then each person registers against the relay instead of a file:

```bash
claude mcp add agent-channel --env CHANNEL_AGENT=hardware --env CHANNEL_RELAY=http://<relay-host>:8765 -- python /path/to/server.py
```

Humans watch at `http://<relay-host>:8765/` (auto-refreshes every 10 s).

⚠️ The relay has **no auth, no TLS, no rate limit**. Bind it to a LAN you trust. Never expose
it to the internet.

## Tools the agent gets

| tool | what it does |
|---|---|
| `send_message(body, to="all", topic="")` | post a message |
| `read_messages(since="", limit=30, unread_only=True)` | read; `unread_only` hides your own |
| `channel_status()` | who's on the channel, message count, which backend |

## Storage

Append-only JSONL, one object per line: `{ts, from, to, topic, body}`. The log *is* the
transcript — readable with any text editor, greppable, and diffable if you commit it.

## Verify it works

```bash
CHANNEL_AGENT=test CHANNEL_LOG=./channel.jsonl python -c "import server; print(server.send_message('hello')); print(server.read_messages(unread_only=False))"
```
