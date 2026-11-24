"""Localhost-only, token-gated pre-boot Web UI for interactive setup."""

from __future__ import annotations

import hmac
import html
import secrets
import threading
import urllib.parse
import webbrowser
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

_PAGE_CSS = (
    "body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; margin: 0; padding: 2rem; }\n"
    ".wrap { max-width: 760px; margin: 0 auto; background: #1e293b; padding: 1.5rem 2rem; border-radius: 10px; }\n"
    "h1, h2 { margin-top: 0; color: #f8fafc; }\n"
    "label { display: block; margin-top: 0.75rem; font-weight: 600; font-size: 0.9rem; }\n"
    "input[type=text], input[type=password] { width: 100%; box-sizing: border-box; padding: 0.5rem; margin-top: 0.25rem; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #f8fafc; }\n"
    "fieldset.feature-card { border: 1px solid #334155; border-radius: 8px; padding: 0.75rem 1rem 1rem; margin-top: 1rem; }\n"
    "button { margin-top: 1.25rem; padding: 0.7rem 1.4rem; background: #2563eb; color: #fff; border: 0; border-radius: 6px; font-weight: 600; cursor: pointer; }\n"
    ".notice { background: #065f46; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; }\n"
    ".error { background: #991b1b; padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; }"
)


def _is_loopback(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


def _render_field_html(key: str, label: str, value: str, is_secret: bool, required: bool) -> str:
    esc_key = html.escape(key, quote=True)
    esc_label = html.escape(label)
    req_attr = " required" if required and not (is_secret and value) else ""
    if is_secret:
        placeholder = "Saved (leave blank to keep)" if value else "Enter secret value"
        return (
            f'<label for="f-{esc_key}">{esc_label}</label>'
            f'<input id="f-{esc_key}" name="cfg_{esc_key}" type="password" '
            f'autocomplete="new-password" placeholder="{html.escape(placeholder, quote=True)}"{req_attr}>'
        )
    esc_val = html.escape(value, quote=True)
    return (
        f'<label for="f-{esc_key}">{esc_label}</label>'
        f'<input id="f-{esc_key}" name="cfg_{esc_key}" type="text" value="{esc_val}"{req_attr}>'
    )


def _render_feature_html(
    feature: str, info: dict[str, Any], env: dict[str, str], is_secret_fn: Callable[[str], bool]
) -> str:
    esc_feat = html.escape(feature, quote=True)
    enabled = env.get(feature, "false").strip().lower() == "true"
    checked = " checked" if enabled else ""
    parts = [
        '<fieldset class="feature-card">',
        f'<legend><label><input type="checkbox" name="feat_{esc_feat}" value="true"{checked}> '
        f'{html.escape(info["prompt"])} (<code>{esc_feat}</code>)</label></legend>',
    ]
    for extra in info.get("extras", []):
        key = extra["key"]
        val = env.get(key, extra.get("default", ""))
        parts.append(_render_field_html(key, extra.get("label", key), val, is_secret_fn(key), False))
    parts.append("</fieldset>")
    return "\n".join(parts)


def render_setup_page(
    env: dict[str, str],
    key_settings: list[str],
    optional_features: dict[str, dict[str, Any]],
    is_secret_fn: Callable[[str], bool],
    csrf_token: str,
    message: str = "",
) -> str:
    """Render the pre-boot setup HTML form without exposing existing secret values."""
    key_inputs = "\n".join(
        _render_field_html(k, k, env.get(k, ""), is_secret_fn(k), False) for k in key_settings
    )
    feature_inputs = "\n".join(
        _render_feature_html(feat, info, env, is_secret_fn) for feat, info in optional_features.items()
    )
    banner = f'<div class="notice">{html.escape(message)}</div>' if message else ""
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        "<title>AI Scraping Defense - Pre-Boot Setup</title>"
        f"<style>{_PAGE_CSS}</style></head><body><div class=\"wrap\">"
        "<h1>AI Scraping Defense - Pre-Boot Setup</h1>"
        "<p>This temporary setup server is bound locally and protected by a one-time token. "
        "Submitting writes <code>.env</code> and generates required secrets before starting Docker Compose.</p>"
        f'{banner}<form method="post" action="/save" autocomplete="off">'
        f'<input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}">'
        f"<h2>Key Settings</h2>{key_inputs}<h2>Optional Features</h2>{feature_inputs}"
        '<button type="submit">Save Configuration &amp; Generate Secrets</button></form></div></body></html>'
    )


def _apply_feature_post_rules(feature: str, updates: dict[str, str]) -> None:
    if feature == "ENABLE_GLOBAL_CDN":
        updates["CLOUD_CDN_PROVIDER"] = "cloudflare"
        updates["REQUIRE_CLOUDFLARE_ACCOUNT"] = "true"
    elif feature == "ENABLE_MCP_MODEL":
        updates["MODEL_URI"] = "mcp://primary/classify"


def _extract_extra_value(
    extra: dict[str, Any], form: dict[str, list[str]], env: dict[str, str], is_secret_fn: Callable[[str], bool]
) -> tuple[str, str] | None:
    ekey = extra["key"]
    raw = (form.get(f"cfg_{ekey}") or [""])[0].strip()
    if is_secret_fn(ekey) and not raw:
        return None
    return ekey, raw or env.get(ekey, extra.get("default", ""))


def _collect_feature_updates(
    feature: str,
    info: dict[str, Any],
    form: dict[str, list[str]],
    env: dict[str, str],
    is_secret_fn: Callable[[str], bool],
    updates: dict[str, str],
) -> None:
    enabled = (form.get(f"feat_{feature}") or [""])[0].lower() == "true"
    updates[feature] = "true" if enabled else "false"
    if not enabled:
        return
    for extra in info.get("extras", []):
        pair = _extract_extra_value(extra, form, env, is_secret_fn)
        if pair is not None:
            updates[pair[0]] = pair[1]
    _apply_feature_post_rules(feature, updates)


def collect_form_updates(
    form: dict[str, list[str]],
    env: dict[str, str],
    key_settings: list[str],
    optional_features: dict[str, dict[str, Any]],
    is_secret_fn: Callable[[str], bool],
) -> dict[str, str]:
    """Extract validated .env updates from submitted pre-boot form fields."""
    updates: dict[str, str] = {}
    for key in key_settings:
        field = f"cfg_{key}"
        if field not in form:
            continue
        raw = (form.get(field) or [""])[0].strip()
        if not (is_secret_fn(key) and not raw):
            updates[key] = raw
    for feature, info in optional_features.items():
        _collect_feature_updates(feature, info, form, env, is_secret_fn, updates)
    updates.setdefault("REQUIRE_CLOUDFLARE_ACCOUNT", env.get("REQUIRE_CLOUDFLARE_ACCOUNT", "false"))
    return updates


class SetupWebHandler(BaseHTTPRequestHandler):
    """HTTP handler for the temporary pre-boot setup Web UI."""

    setup_state: dict[str, Any] = {}

    def log_message(self, format: str, *args: Any) -> None:  # pylint: disable=redefined-builtin
        return

    def _is_authorized(self) -> bool:
        state = self.setup_state
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        q_token = (query.get("token") or [""])[0]
        if q_token and hmac.compare_digest(q_token, state["bootstrap_token"]):
            return True
        jar = cookies.SimpleCookie()
        jar.load(self.headers.get("Cookie", ""))
        morsel = jar.get("setup_session")
        return bool(morsel and hmac.compare_digest(morsel.value, state["session_token"]))

    def _send_html(self, status_code: int, body: str, set_session: bool = False) -> None:
        raw = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        if set_session:
            tok = self.setup_state["session_token"]
            self.send_header("Set-Cookie", f"setup_session={tok}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if not self._is_authorized():
            self._send_html(403, "<h1>403 Forbidden</h1><p>Valid setup token required.</p>")
            return
        state = self.setup_state
        env = state["parse_env"](state["env_file"])
        page = render_setup_page(
            env, state["key_settings"], state["optional_features"], state["is_secret"], state["csrf_token"]
        )
        self._send_html(200, page, set_session=True)

    def do_POST(self) -> None:
        if not self._is_authorized():
            self._send_html(403, "<h1>403 Forbidden</h1>")
            return
        state = self.setup_state
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(min(length, 262144)).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw_body, keep_blank_values=True)
        posted_csrf = (form.get("csrf_token") or [""])[0]
        if not hmac.compare_digest(posted_csrf, state["csrf_token"]):
            self._send_html(403, "<h1>403 Invalid CSRF token</h1>")
            return
        env = state["parse_env"](state["env_file"])
        updates = collect_form_updates(
            form, env, state["key_settings"], state["optional_features"], state["is_secret"]
        )
        state["apply_updates"](updates)
        page = render_setup_page(
            {**env, **updates},
            state["key_settings"],
            state["optional_features"],
            state["is_secret"],
            state["csrf_token"],
            message="Saved .env and generated secrets. You can now start Docker Compose and close this page.",
        )
        self._send_html(200, page)
        if state.get("shutdown_on_save"):
            threading.Thread(target=state["server"].shutdown, daemon=True).start()


def create_setup_handler(state: dict[str, Any]):
    """Bind a SetupWebHandler subclass to the provided server state."""
    return type("BoundSetupWebHandler", (SetupWebHandler,), {"setup_state": state})


def run_setup_web_server(
    root: Path,
    config: dict[str, Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """Launch the temporary pre-boot setup Web UI until saved or interrupted."""
    if not _is_loopback(host):
        print(
            f"WARNING: Binding pre-boot setup UI to non-loopback host '{host}'. "
            "Prefer 127.0.0.1 with an SSH tunnel."
        )
    state: dict[str, Any] = {
        "env_file": root / ".env",
        "bootstrap_token": secrets.token_urlsafe(24),
        "session_token": secrets.token_urlsafe(24),
        "csrf_token": secrets.token_urlsafe(24),
        "parse_env": config["parse_env_fn"],
        "apply_updates": config["apply_updates_fn"],
        "key_settings": config["key_settings"],
        "optional_features": config["optional_features"],
        "is_secret": config["is_secret_fn"],
        "shutdown_on_save": True,
    }
    server = ThreadingHTTPServer((host, port), create_setup_handler(state))
    state["server"] = server
    bound_port = server.server_address[1]
    url = urllib.parse.urlunparse(("http", f"{host}:{bound_port}", "/", "", f"token={state['bootstrap_token']}", ""))
    print(f"Pre-boot Setup UI listening at: {url}")
    print("Keep this URL private. Press Ctrl+C to cancel.")
    if open_browser and _is_loopback(host):
        try:
            webbrowser.open(url)
        except OSError as exc:
            print(f"Could not open browser automatically: {exc}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPre-boot setup server stopped.")
    finally:
        server.server_close()
