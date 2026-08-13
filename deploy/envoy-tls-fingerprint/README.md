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

When Cloudflare terminates client TLS, this direct-termination sample must not
be placed behind it unchanged: Envoy would fingerprint Cloudflare rather than
the visitor. Cloudflare does not automatically add JA3/JA4 origin headers. Use
the Worker and origin-authentication design in
`docs/tls_fingerprint_attestation.md`, or make a trusted ingress adapter
translate those Worker-derived values into overwritten `X-ASD-TLS-*` fields.
