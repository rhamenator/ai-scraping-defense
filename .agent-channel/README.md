# Agent Channel (AI Scraping Defense workspace)

A live, bidirectional message log between Codex and Claude Code while both are
working in this four-repo workspace:

- `e:\ai-scraping-defense` (Python reference implementation — channel lives here)
- `e:\ai-scraping-defense-iis` (.NET)
- `e:\ai-scraping-defense-rust` (Rust)
- `e:\request-guard-mcp` (MCP server)

This is the single shared channel for all four repos. The other three repos
contain a `.agent-channel/POINTER.md` that redirects here — never start a
separate log in them.

There is no push mechanism between the two CLIs, so "live" means "checked and
updated every turn." Each agent reads new messages at the start of its turn
(or before picking new work / after finishing a slice) and can append a
message any time. Don't rely on this for anything sub-second or blocking; the
human operator is still the fallback for anything urgent.

## Files

- `log.jsonl` — append-only, one JSON object per line, line number is `seq`:
  `{"seq": <int>, "ts": "<ISO8601>", "from": "codex"|"claude", "to": "codex"|"claude"|"both", "type": "note"|"question"|"answer"|"finding"|"handoff"|"ack", "repo": "<repo dir name or 'workspace'>", "text": "<message>"}`
- `claude.cursor` / `codex.cursor` — single integer: highest `seq` that agent has read. Starts at `0`.

## Protocol

1. Read `log.jsonl`, skip lines with `seq` <= your cursor value, process entries addressed `to` you or `"both"`.
2. Write the highest `seq` you just processed into your cursor file.
3. To send a message: read the last line's `seq`, append one new line to `log.jsonl` with `seq + 1`. Never edit or delete existing lines — this is a log, not shared mutable state.
4. Keep messages short and actionable. Include `repo` so findings route to the right codebase. Durable results still go in each repo's CHANGELOG/docs as usual.
