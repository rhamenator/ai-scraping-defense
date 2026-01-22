# Pay-Per-Crawl Blockchain Logging

Pay-per-crawl events can be written to a local, hash-chained audit log. This
provides tamper-evident ordering without requiring a full blockchain node.

## Enable logging

Set:

- `PAY_PER_CRAWL_BLOCKCHAIN_LOG_ENABLED=true`
- `PAY_PER_CRAWL_BLOCKCHAIN_LOG_PATH=logs/pay_per_crawl_blockchain.log`

## Output format

Each line is JSON with a hash chain:

```json
{
  "action": "charge",
  "timestamp": "2026-01-22T12:00:00+00:00",
  "data": {"token_hash": "...", "amount": 1},
  "prev_hash": "...",
  "hash": "..."
}
```

Sensitive fields like crawler tokens are hashed before logging.
