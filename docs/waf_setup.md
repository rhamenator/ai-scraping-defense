# Web Application Firewall

This project supports an optional ModSecurity-based Web Application Firewall (WAF) for inspecting incoming HTTP requests. When enabled, Nginx loads rule files from the `waf/` directory and applies them before requests reach your application.

## Prerequisites

1. **OWASP Core Rule Set** – Download the latest [OWASP CRS](https://coreruleset.org/).
2. Extract `crs-setup.conf` and the `rules` folder into the repository's `waf/` directory.
3. Optionally add custom ModSecurity rules in the same folder.

Alternatively, you can provide a `RULES_DOWNLOAD_URL` environment variable to fetch a remote rules file at startup. The URL must begin with `https://`. To restrict which hosts can be used, set `RULES_ALLOWED_DOMAINS` to a comma-separated list of permitted domains.

### Should I pin a digest?

Both choices are supported; pick the one that matches how you want to run it.

| | Pinned (`RULES_SHA256` / `CRS_SHA256` set) | Not pinned (the default) |
| --- | --- | --- |
| What you get | Only the exact file you reviewed is ever installed | Whatever the host serves at that URL today |
| If the host is compromised or the file changes | The download is refused and nothing changes | The new content is installed if it passes the safety checks below |
| Updating | A deliberate step: new URL or file, new digest | Automatic |
| Good for | Production, and anywhere a rule change should be reviewed | Trying things out, or rules you control at both ends |

Compute the digest of what you reviewed with `sha256sum rules-file` (or the archive). `RULES_REQUIRE_DIGEST=true` turns a
missing pin into a refusal instead of a warning, so a setting can't be left off by accident. The default stays "not
pinned, with a warning" so existing setups keep working; the safety checks below apply either way.

### Downloaded rules are verified before they are used

Downloaded rules (`RULES_DOWNLOAD_URL`) and the OWASP CRS archive (`CRS_DOWNLOAD_URL`) are treated as untrusted input:

- **Pin what you reviewed.** Set `RULES_SHA256` (or `CRS_SHA256`) to the SHA-256 of the file or archive. A different download is refused and nothing is installed. Pinning means an update is a deliberate change of the pin; to follow a moving URL, leave the pin unset (a warning is logged) and accept that the content is whatever the host serves. `RULES_REQUIRE_DIGEST=true` refuses unpinned downloads. Digests are not signatures: they prove the bytes match what you pinned, not who produced them.
- **No redirects, HTTPS only, public addresses only**, and the exact hosts in `RULES_ALLOWED_DOMAINS` when set. Use the final download URL; for the CRS that means a direct archive URL such as the `codeload.github.com` tag archive, not a `github.com/.../archive/...` link that redirects.
- **Bounded.** Size limits apply to the download, each extracted file, the total, the number of members and the expansion ratio (see `sample.env`). Only `crs-setup.conf[.example]` and `*.conf`/`*.data`/`*.example` files under `rules/` are extracted.
- **Validated before activation.** Downloaded custom rules must be ModSecurity text and may not use `Include`, `SecRuleScript`, `SecRemoteRules`, `@inspectFile`, `exec:` or directives that change where the engine writes. CRS files get the same check for those constructs.
- **Staged and reversible.** The CRS is extracted next to the live rules and swapped in with a rename; the previous generation is kept as `rules.previous` (and `crs-setup.conf.previous`). If Nginx will not reload, the previous rules are restored. Custom rules are written to a temporary file, replaced atomically, kept as `<file>.previous` and restored if the reload fails. Invalid or unverifiable downloads never touch the live files.

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
