# Blocklist storage

A blocked address is one Redis key in the blocklist database (`REDIS_DB_BLOCKLIST`, default 2):

```
<tenant>:blocklist:ip:<ip>      value: JSON {reason, source, timestamp_utc, details}
```

The edge (`nginx/lua/blocklist.lua`) answers 403 when that key exists for the connecting address. Every component that
blocks or unblocks goes through `src/shared/blocklist_store.py`, so they all agree on the key, the database and the rules:

| Writer | Expiry |
| --- | --- |
| Escalation engine, tarpit (automated) | `BLOCKLIST_TTL_SECONDS` |
| Admin UI `POST /block`, signed webhook `block_ip` (a person or a signed request asked for it) | none, until unblocked |

- IPv6 addresses are stored in their compressed form and IPv4-mapped IPv6 addresses (`::ffff:a.b.c.d`) as plain IPv4; the edge
  normalises the connecting address the same way.
- A block is reported as successful only after the key has been read back. A block that cannot be stored returns 503.
- `POST /unblock` and the webhook `allow_ip` remove that key and any legacy copy.
- The admin UI's blocklist and statistics count these keys; the "temporary" count is the ones with an expiry.

## Upgrading from earlier releases

Earlier releases stored admin and webhook blocks as members of the Redis set `<tenant>:blocklist` (the admin UI in the default
database) and tarpit blocks as `<tenant>:blocklist:<ip>`. The edge never read those, so they had no effect. The first time the
admin UI connects after the upgrade it moves them to the real key (permanent for set members, with the remaining TTL for tarpit
keys) and removes the old entries. Because those blocks now start to work, review the blocklist after upgrading.
