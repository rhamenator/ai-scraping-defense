# Cloud dashboard credentials

The cloud dashboard collects metrics from many installations. It has two kinds of caller, and they are kept apart:

| Credential | Header | May |
| --- | --- | --- |
| **Operator** (`CLOUD_DASHBOARD_API_KEY`) | `X-API-Key` | register installations and issue or rotate their credentials; read any installation's metrics and websocket |
| **Installation** (its own token) | `X-Installation-Token` | push its own metrics, read its own metrics and websocket, refresh its own registration; nothing for any other installation |

## Enrolling an installation

The operator registers the installation and receives its token once:

```bash
curl -X POST https://dashboard.example/register -H "X-API-Key: $OPERATOR_KEY" \
  -H "Content-Type: application/json" -d '{"installation_id": "site-42"}'
# {"status": "registered", "installation_id": "site-42", "token": "site-42.<secret>"}
```

Give that token to the installation. Only a hash of the secret is stored, so it cannot be shown again. Registering again
refreshes the registration (it lasts 24 hours unless refreshed) and does not change the token; send `"rotate": true` to issue a new
token, which invalidates the old one.

The installation id is taken from the token, never from the request. `POST /metrics` with another installation's id, or
`GET /metrics/<other>` or `/ws/<other>`, is refused with 403; a missing, wrong or unknown token is 401 and unknown ids fail
the same way as wrong secrets.

## Installations still using the shared key

Earlier releases let the one shared key act for every installation. That is now off. To give existing agents time to switch,
set `CLOUD_DASHBOARD_ALLOW_SHARED_KEY=true`: the operator key may then push metrics for any installation again, as before.
Turn it off once every installation has its own token, because with it on, anyone who holds the shared key can overwrite any
installation's data.
