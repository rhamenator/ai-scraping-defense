# Prompt Router

The prompt router is a lightweight FastAPI service that decides whether a request
should be handled by a local LLM container or forwarded to the cloud proxy. The
Escalation Engine sends all classification prompts to this service rather than
talking to the models directly.

The router counts the tokens in the prompt and, if the count exceeds
`MAX_LOCAL_TOKENS`, it forwards the payload to the cloud proxy. Otherwise it
targets the local LLM endpoint.

## Configuration

Set the following variables in `.env`:

- `PROMPT_ROUTER_HOST` – hostname or container name running the router.
- `PROMPT_ROUTER_PORT` – port the router listens on.
- `PROXY_KEY` – shared secret sent to the cloud proxy via the `X-Proxy-Key` header.

```env
# excerpt from sample.env
PROMPT_ROUTER_PORT=8009
```

The Escalation Engine uses `http://<PROMPT_ROUTER_HOST>:<PROMPT_ROUTER_PORT>/route`
as the request URL.

When forwarding a prompt to the cloud proxy, the router includes `X-Proxy-Key`
with the value of `PROXY_KEY`. Requests missing this header or providing the
wrong key are rejected with **401 Unauthorized**.

To route oversized prompts to a Model Context Protocol tool instead of the
cloud proxy, set `CLOUD_PROXY_URL` to an MCP URI such as
`mcp://risk-scorer/classify`. The router will invoke the configured MCP tool and
return its response when the token threshold is exceeded.
