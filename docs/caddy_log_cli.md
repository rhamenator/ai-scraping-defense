# Extract AI crawler IPs from Caddy logs

`scripts/extract_ai_bot_ips.py` reads Caddy's newline-delimited JSON access log
and prints a sorted, unique list of IP addresses whose User-Agent identifies a
known AI crawler. It streams the file, so it does not load a large log into
memory.

```bash
python scripts/extract_ai_bot_ips.py /var/log/caddy/access.log
```

Pipe logs through standard input with `-`, and add `--counts` to include the
number of matching requests:

```bash
journalctl -u caddy -o cat | python scripts/extract_ai_bot_ips.py - --counts
```

The command prefers Caddy's `request.client_ip`, then falls back to
`request.remote_ip`. Configure Caddy's `trusted_proxies` and `client_ip_headers`
before relying on a forwarded client address; otherwise a client can spoof
forwarding headers. Treat the output as an indicator rather than proof: a
User-Agent can be forged, and this offline command does not run the project's
behavioral, reputation, or rate-based detection layers.
