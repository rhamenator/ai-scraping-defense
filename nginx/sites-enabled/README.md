# Protected site configurations

Place one NGINX `*.conf` server configuration per protected website in this
directory. Docker Compose mounts the directory read-only at
`/etc/nginx/sites-enabled`.

When Cloudflare integration is enabled, use `$remote_addr` for rate-limit and
blocklist keys. The generated trusted-proxy configuration restores
`CF-Connecting-IP` before these site configurations run, but only when the
immediate peer belongs to `SECURITY_CDN_TRUSTED_PROXY_CIDRS`.
