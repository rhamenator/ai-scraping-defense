# Trusted TLS fingerprint attestation

JA3 and JA4 affect detection only after the service proves that the values came
from infrastructure which observed the client TLS handshake. Merely validating
their syntax is not proof of provenance.

## First trust hop

Choose one ingress path and keep the application origin unreachable from the
public Internet.

### Direct Envoy TLS termination

`deploy/envoy-tls-fingerprint/envoy.yaml` enables Envoy's TLS inspector JA3 and
JA4 collection. It overwrites `X-ASD-TLS-JA3`, `X-ASD-TLS-JA4`, and
`X-ASD-TLS-Source`; client values never survive the proxy. Configure the
application's `SECURITY_TRUSTED_PROXY_CIDRS` with only the Envoy workload CIDR
and enforce the same restriction with a firewall or Kubernetes NetworkPolicy.

Envoy fingerprinting is disabled unless `enable_ja3_fingerprinting` and
`enable_ja4_fingerprinting` are set. The sample uses Envoy's documented
`%TLS_JA3_FINGERPRINT%` and `%TLS_JA4_FINGERPRINT%` formatters.

### Cloudflare TLS termination

JA3/JA4 are Cloudflare Bot Management fields, not automatic origin request
headers. They require an Enterprise Bot Management plan. A Worker at the edge
must delete any visitor-supplied copies and populate the origin headers from
`request.cf.botManagement`:

```js
export default {
  async fetch(request) {
    const headers = new Headers(request.headers);
    headers.delete("cf-ja3-hash");
    headers.delete("cf-ja4");
    const bot = request.cf?.botManagement;
    if (bot?.ja3Hash) headers.set("cf-ja3-hash", bot.ja3Hash);
    if (bot?.ja4) headers.set("cf-ja4", bot.ja4);
    return fetch(new Request(request, { headers }));
  },
};
```

The origin must additionally enforce an account-scoped Authenticated Origin
Pull certificate, a Cloudflare Tunnel, or validated Cloudflare CIDRs. Global
Authenticated Origin Pulls prove only that traffic came from Cloudflare, not
from a particular account. If another ingress sits between Cloudflare and the
application, that ingress must validate the Cloudflare connection and translate
the fields into overwritten `X-ASD-TLS-*` headers. Do not run the direct-Envoy
sample unchanged behind Cloudflare: it would fingerprint Cloudflare's origin
connection rather than the visitor.

## Service-to-service binding

After the first hop, the tarpit signs normalized provenance for the escalation
engine using `TLS_FINGERPRINT_ATTESTATION_KEY` (at least 32 random bytes). The
token is:

```text
v1:<unix-seconds>:<hex HMAC-SHA256>
```

The HMAC message is eight newline-separated UTF-8 fields: version, issued-at,
lowercase client IP, uppercase method, exact path, JA3, JA4, and lowercase
source. Newlines, carriage returns, and NUL bytes are rejected. Consumers use a
constant-time comparison and reject tokens outside
`TLS_FINGERPRINT_ATTESTATION_MAX_AGE_SECONDS` (default 60). A token cannot be
replayed for another IP, method, path, fingerprint, or source.

Use the same secret in the tarpit, escalation engine, IIS/Rust forwarders, and
request-guard-mcp. For a rolling rotation, first deploy the new current key as
`TLS_FINGERPRINT_ATTESTATION_KEY` and the old key as
`TLS_FINGERPRINT_ATTESTATION_PREVIOUS_KEY` to downstream consumers, deepest
first (MCP before escalation). Only after every consumer accepts both should
upstream producers switch to the new current key. Producers sign only with the
current key; consumers accept either. After every producer has rolled and at
least the maximum token lifetime has elapsed, remove the previous key. Never
reuse an API bearer token as an attestation key.

## Detection and audit

`TLS_KNOWN_BAD_JA3` and `TLS_KNOWN_BAD_JA4` are comma-separated normalized
threat sets. Verified matches add a strong escalation signal. A verified JA4
whose transport/version prefix conflicts with a modern browser user-agent adds
a smaller mismatch signal. Unverified values add neither signal.

Every escalation decision stores normalized JA3, JA4, source, and the
server-derived verification status in both the decisions database and the
structured `security_decision` event. The short-lived signature is not stored.

References: [Envoy TLS inspector](https://www.envoyproxy.io/docs/envoy/latest/api-v3/extensions/filters/listener/tls_inspector/v3/tls_inspector.proto.html),
[Envoy substitution formatter](https://www.envoyproxy.io/docs/envoy/latest/configuration/advanced/substitution_formatter.html),
[Cloudflare Bot Management variables](https://developers.cloudflare.com/bots/reference/bot-management-variables/), and
[Cloudflare Authenticated Origin Pulls](https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/).
