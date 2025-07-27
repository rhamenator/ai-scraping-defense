# Prompt Router

The prompt router is a lightweight FastAPI service that decides whether a request
should be handled by a local LLM container or forwarded to the cloud proxy. The
Escalation Engine sends all classification prompts to this service rather than
talking to the models directly.

The router reads the length of the prompt and, if it exceeds `MAX_LOCAL_TOKENS`,
it forwards the payload to the cloud proxy. Otherwise it targets the local LLM
endpoint.

## Configuration

Set the following variables in `.env`:

- `PROMPT_ROUTER_HOST` – hostname or container name running the router.
- `PROMPT_ROUTER_PORT` – port the router listens on.

```env
# excerpt from sample.env
PROMPT_ROUTER_PORT=8009
```

The Escalation Engine uses `http://<PROMPT_ROUTER_HOST>:<PROMPT_ROUTER_PORT>/route`
as the request URL.
