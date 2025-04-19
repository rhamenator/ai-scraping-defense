
# API Reference

This document provides reference documentation for the core HTTP endpoints exposed by the AI Scraping Defense Stack.

---

## 🔒 Tarpit API

### `GET /api/tarpit`

**Purpose:**  
Serves a slow-loading HTML response to bots and suspicious clients. Also triggers behavioral logging and optional escalation.

**Request Example:**

```bash
curl http://localhost/api/tarpit

```

Response:

200 OK

Slowly streamed or static HTML containing fake or misleading content

Side Effects:

Sends a POST to /escalate with client metadata

May rotate ZIP trap archives depending on access pattern

🧠 Escalation Engine
POST /escalate
Purpose:
Evaluates suspicious request metadata using either:

Local heuristics (e.g., user-agent, header patterns)

External or local lightweight LLMs

Optional webhook forwarding for alerts or bans

Request Body:

```json
{
  "ip": "203.0.113.42",
  "user_agent": "Mozilla/5.0 (compatible; BadBot/1.0)",
  "path": "/tarpit",
  "headers": {
    "accept": "*/*",
    "user-agent": "BadBot/1.0"
  }
}```

Response Example:

```json
{
  "status": "processed",
  "entry": {
    "ip": "203.0.113.42",
    "user_agent": "BadBot/1.0",
    "path": "/tarpit",
    "timestamp": "2024-04-17T15:30:00.000Z",
    "decision": "BLOCK"
  }
}```

Notes:

Decision logic can be extended to use Markov chains, entropy scores, or third-party classification APIs.

Decisions like "BLOCK" or "ALLOW" can be hooked into NGINX or fail2ban.

📊 Metrics API (Admin UI)
GET /admin/metrics
Purpose:
Returns cumulative stats tracked by the in-memory metrics engine.

Response Example:

```json
{
  "escalations": 42,
  "blocked_requests": 18,
  "allowed_requests": 24,
  "ai_decisions": {
    "BLOCK": 12,
    "ALLOW": 6
  }
}```

🔄 ZIP Trap Archive Generator
This is not exposed directly as an endpoint but triggered internally or via rotate_archives().

ZIP files contain multiple .js files with infinite loops, console.log noise, or tracking traps.

Archives are rotated to avoid static signature detection.

🧪 Detection Logic Triggers

Trigger	Outcome
"bot" in User-Agent	Redirects to /api/tarpit
curl or wget access	Escalates and delays response
Honeypot field hit	May escalate or log aggressively

🛡️ Security Notes
Tarpit endpoints are public by design but should be rate-limited externally.

Metrics and webhook endpoints should be IP-restricted or tokenized.

For deeper architecture integration, see docs/architecture.md.
