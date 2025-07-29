# Web Application Firewall

This project supports an optional ModSecurity-based Web Application Firewall (WAF) for inspecting incoming HTTP requests. When enabled, Nginx loads rule files from the `waf/` directory and applies them before requests reach your application.

## Prerequisites

1. **OWASP Core Rule Set** – Download the latest [OWASP CRS](https://coreruleset.org/).
2. Extract `crs-setup.conf` and the `rules` folder into the repository's `waf/` directory.
3. Optionally add custom ModSecurity rules in the same folder.

## Enabling with Docker Compose

1. Edit `.env` and set:
   ```bash
   ENABLE_WAF=true
   WAF_RULES_PATH=./waf
   ```
2. Start the stack (or restart Nginx) so it mounts the rules:
   ```bash
   docker compose up -d nginx
   ```

## Enabling on Kubernetes

1. Download the OWASP CRS as above.
2. Create a ConfigMap from the `waf/` directory:
   ```bash
   kubectl create configmap waf-rules --from-file=waf/ -n ai-defense
   ```
3. Deploy the manifests that mount `/etc/nginx/modsecurity` in the Nginx deployment.

## Customization Tips

- Review `waf/modsecurity.conf` for core settings such as anomaly scoring.
- You can disable individual rules by editing `crs-setup.conf` or adding your own `.conf` files.
- For troubleshooting, set `MODSECURITY_LOG_LEVEL=Debug` in `.env` and check the logs under `./nginx/logs/`.

A properly tuned WAF blocks common attack patterns like SQL injection and path traversal while letting benign traffic through. Start with the default CRS rules and adjust thresholds as you analyze your application's traffic.
