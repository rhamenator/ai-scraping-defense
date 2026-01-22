# Error Handling Contract

Services built with `create_app()` emit a consistent error envelope that includes
stable error codes and a request ID for correlation. Existing `detail` fields are
preserved for backwards compatibility.

## Response envelope

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Invalid payload",
    "details": []
  },
  "request_id": "e9e5f5cf-3c3c-4a6d-9ed3-93a2d5358c74",
  "detail": "Invalid payload"
}
```

## Standard error codes

- `invalid_request` (400)
- `unauthorized` (401)
- `forbidden` (403)
- `not_found` (404)
- `method_not_allowed` (405)
- `conflict` (409)
- `payload_too_large` (413)
- `validation_error` (422)
- `rate_limited` (429)
- `internal_error` (500)
- `bad_gateway` (502)
- `service_unavailable` (503)
- `gateway_timeout` (504)

Other HTTP status codes map to `http_<status>`.

## Request IDs

The request ID is sourced from `X-Request-ID` if the client provides one; otherwise
it is generated per request. The same ID is returned in the response header and
in the body (`request_id`) to enable log correlation.
