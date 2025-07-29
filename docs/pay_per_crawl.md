# Pay-Per-Crawl Proxy

This proxy charges registered crawlers per request using HTTP 402 when payment is required. Pricing rules are loaded from `config/pricing.yaml`.

This monetization approach is optional. You can continue blocking automated
traffic entirely, or allow certain bots to proceed only if they pay according to
your own policies. The system merely tracks usage and handles payments; whether
to grant paying bots access is ultimately your decision.

```yaml
# pricing.yaml
# path prefix : price in USD
/docs/: 0.01
/blog/: 0.005
/api/: 0.02
```

Crawlers register themselves via `POST /register-crawler` and receive a token. Credits are added with `POST /pay`. Each proxied request must include the token in the `X-API-Key` header. When a crawler's balance is insufficient the proxy responds with **402 Payment Required**.

### Payment Gateway

The optional payment gateway integration now supports multiple providers. Set
`PAYMENT_GATEWAY_PROVIDER` to `stripe`, `paypal`, `braintree`, `square`,
`adyen`, `authorizenet`, or `http` (default). Each provider reads API
credentials from environment variables (`STRIPE_API_KEY`, `PAYPAL_API_KEY`,
`BRAINTREE_API_KEY`, `SQUARE_API_KEY`, `ADYEN_API_KEY`,
`AUTHORIZE_NET_API_KEY`, or `PAYMENT_GATEWAY_KEY`). The gateway exposes helpers for
creating crawler accounts, charging or refunding credits, and retrieving
balances. Credentials are never logged in full—only a short prefix is retained
in error messages—and HTTPS endpoints are used by default.
