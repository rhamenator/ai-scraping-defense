# Ubuntu Reverse Proxy Deployment

This guide covers the recommended Ubuntu Server topology when Apache or nginx
is already installed on the host and you want to run the defense stack without
stealing ports `80` and `443`.

## Recommended Topology

Use the repository's containerized `nginx_proxy` as the primary application
edge and keep the host web server as a thin front door:

1. Host nginx or Apache listens on `80` and `443`.
2. Host reverse proxy forwards traffic to the stack's `nginx_proxy` on
   `127.0.0.1:8088` and `127.0.0.1:8443`.
3. The stack's `nginx_proxy` applies the Lua/WAF/blocklist logic and forwards
   allowed traffic to `REAL_BACKEND_HOST` or `REAL_BACKEND_HOSTS`.

This keeps the defense logic in one place while avoiding collisions with
existing Ubuntu web services.

## Port Plan

- Host web server: `80` / `443`
- Stack `nginx_proxy`: `8088` / `8443`
- Optional stack `apache_proxy`: `8080`

If `8088`, `8443`, or `8080` are already in use, override them in `.env`.

## Minimal `.env` Checklist

```dotenv
NGINX_HTTP_PORT=8088
NGINX_HTTPS_PORT=8443
APACHE_HTTP_PORT=8080
REAL_BACKEND_HOST=http://127.0.0.1:8082
ENABLE_HTTPS=true
TLS_CERT_PATH=./nginx/certs/tls.crt
TLS_KEY_PATH=./nginx/certs/tls.key
```

For takeover or production mode, switch `NGINX_HTTP_PORT` / `NGINX_HTTPS_PORT`
to `80` / `443` only after disabling the host listener or putting the host
proxy in front of another address.

## Host Nginx Example

```nginx
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
    }
}
```

## Host Apache Example

```apache
ProxyPreserveHost On
ProxyPass / http://127.0.0.1:8088/
ProxyPassReverse / http://127.0.0.1:8088/
RequestHeader set X-Forwarded-Proto "http"
```

## Launch Sequence

1. Copy `sample.env` to `.env`.
2. Set `REAL_BACKEND_HOST` or `REAL_BACKEND_HOSTS`.
3. Generate secrets with `bash ./scripts/linux/generate_secrets.sh --update-env`.
4. Start the stack with `docker compose up --build -d`.
5. Run `bash ./scripts/linux/stack_smoke_test.sh`.

## Validation Checklist

- `docker compose ps` shows `nginx_proxy`, `admin_ui`, `tarpit_api`,
  `escalation_engine`, `postgres_markov_db`, and `redis_store` healthy.
- `curl -fsS http://127.0.0.1:8088/` returns a response.
- `curl -kfsS https://127.0.0.1:8443/` returns a response when HTTPS is enabled.
- The host reverse proxy forwards `Host`, `X-Forwarded-For`, and
  `X-Forwarded-Proto`.
- TLS is terminated either on the host proxy or inside the stack, but the
  choice is explicit and documented for the deployment.
- Any port collisions are resolved by changing `.env`, not by editing compose
  manifests directly.

## Apache Alternative

The repository still ships `apache_proxy`, and `scripts/linux/quick_proxy.sh`
supports `apache` for quick local tests. For Ubuntu production deployments,
prefer the Nginx-based stack path unless you specifically need Apache modules or
want Apache as the thin host-side reverse proxy example shown above.
