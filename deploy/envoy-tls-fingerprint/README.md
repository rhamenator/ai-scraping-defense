# Trusted TLS fingerprint collector

This sample terminates direct client TLS in Envoy, computes JA3 and JA4 from
the ClientHello, overwrites any client-supplied fingerprint headers, and sends
the validated values to the defense origin.

- Mount the certificate and key at `/etc/envoy/tls/tls.crt` and
  `/etc/envoy/tls/tls.key`.
- Resolve `defense-origin` to the protected service or change that cluster
  address.
- Configure the origin to trust only the Envoy address/CIDR as a proxy.
- Do not expose the origin directly, because direct clients must not be able to
  assert `X-ASD-TLS-JA3` or `X-ASD-TLS-JA4`.

When Cloudflare terminates client TLS, the origin cannot recreate the original
fingerprint. Enable Cloudflare's managed transform for `cf-ja3-hash` and
`cf-ja4`, and accept those headers only when the immediate peer is in the
configured Cloudflare CIDRs. These fields can legitimately be absent. The
Cloudflare peer address is infrastructure and must never be used as the block
target; only the validated originating client IP may be blocked.
