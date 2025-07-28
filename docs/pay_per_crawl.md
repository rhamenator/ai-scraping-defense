# Pay-Per-Crawl Proxy

This experimental proxy charges registered crawlers per request using HTTP 402 when payment is required. Pricing rules are loaded from `config/pricing.yaml`.

```yaml
# pricing.yaml
# path prefix : price in USD
/docs/: 0.01
/blog/: 0.005
/api/: 0.02
```

Crawlers register themselves via `POST /register-crawler` and receive a token. Credits are added with `POST /pay`. Each proxied request must include the token in the `X-API-Key` header. When a crawler's balance is insufficient the proxy responds with **402 Payment Required**.
