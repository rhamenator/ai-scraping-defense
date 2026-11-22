import base64  # Token encoding
import datetime  # Timestamp handling
import hashlib  # Signature hashing
import hmac
import json
import logging
import os
import secrets

from fastapi import Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.shared.config import get_secret
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.request_identity import resolve_request_identity

from .challenge_store import ChallengeStore

CAPTCHA_SECRET = get_secret("CAPTCHA_SECRET_FILE") or os.getenv("CAPTCHA_SECRET")
CAPTCHA_SUCCESS_LOG = os.getenv("CAPTCHA_SUCCESS_LOG", "/app/logs/captcha_success.log")
TOKEN_EXPIRY = int(os.getenv("CAPTCHA_TOKEN_EXPIRY_SECONDS", 300))
# A challenge may be answered from the address it was issued to (set false for users whose address changes mid-flow).
BIND_IP = os.getenv("CAPTCHA_BIND_IP", "true").lower() == "true"
# Challenges and solve attempts per client address per minute; 0 disables the limit.
RATE_LIMIT_PER_MINUTE = int(os.getenv("CAPTCHA_RATE_LIMIT_PER_MINUTE", 30))
store = ChallengeStore()

app = create_app()


@register_health_check(app, "custom_captcha", critical=True)
async def _captcha_health() -> HealthCheckResult:
    if not CAPTCHA_SECRET:
        return HealthCheckResult.unhealthy({"reason": "captcha secret missing"})
    if store.backend == "memory":
        return HealthCheckResult.degraded({"store": "process memory (single replica only)"})
    return HealthCheckResult.healthy({"token_expiry": TOKEN_EXPIRY, "store": store.backend})


logger = logging.getLogger(__name__)


def _sign(data: dict) -> str:
    if not CAPTCHA_SECRET:
        raise RuntimeError("CAPTCHA secret not configured")
    payload = json.dumps(data, separators=(",", ":"))
    sig = hmac.new(
        CAPTCHA_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()
    return token


def _unsign(token: str) -> dict | None:
    if not CAPTCHA_SECRET:
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = decoded.rsplit(".", 1)
        expected = hmac.new(
            CAPTCHA_SECRET.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected, sig):
            return json.loads(payload)
    except Exception:
        return None
    return None


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<title>Captcha Challenge</title>
<style>
body {{
  font-family: Arial, sans-serif;
  background: linear-gradient(120deg,#1e3c72,#2a5298);
  color: #fff;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
}}
.container {{
  background: #fff;
  color: #333;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 0 10px rgba(0,0,0,0.3);
}}
button{{padding:6px 12px;margin-top:8px;}}
</style>
</head>
<body>
<div class='container'>
<h2>Prove you're human</h2>
<p>What is {a} + {b}?</p>
<form id='cform'>
<input name='answer' required autofocus>
<input type='hidden' name='token' value='{escaped_token}'>
<button type='submit'>Submit</button>
</form>
<div id='result' role='status' aria-live='polite'></div>
</div>
<script>
document.getElementById('cform').addEventListener('submit', async (e)=>{{
  e.preventDefault();
  const data = new FormData(e.target);
  const res = await fetch('/solve', {{method: 'POST', body: data}});
  const js = await res.json();
  const result = document.getElementById('result');
  if (js.success) {{
    result.textContent = 'Passed! Token copied to clipboard';
    if (js.token){{navigator.clipboard.writeText(js.token);}}
  }} else {{
    // A challenge can be answered once, so a miss needs a fresh question.
    result.textContent = 'Not quite. Loading a new question...';
    setTimeout(()=>location.reload(), 1500);
  }}
}});
</script>
<script src='/__fp.js' async></script>
</body>
</html>"""


def _challenge_html(a: int, b: int, token: str) -> str:
    from html import escape

    return _PAGE_TEMPLATE.format(a=a, b=b, escaped_token=escape(token))


def _rate_limited(request: Request, action: str) -> bool:
    ip = resolve_request_identity(request).client_ip
    return not store.allow(f"{action}:{ip}", RATE_LIMIT_PER_MINUTE)


@app.get("/challenge", response_class=HTMLResponse)
async def challenge_page(request: Request, fp_id: str | None = Cookie(None)):
    if not CAPTCHA_SECRET:
        raise HTTPException(status_code=500, detail="CAPTCHA not configured")
    if _rate_limited(request, "challenge"):
        raise HTTPException(status_code=429, detail="Too many challenges")
    a = secrets.randbelow(8) + 1
    b = secrets.randbelow(8) + 1
    # The page carries only a random id; the answer and the client it was issued to stay on the server.
    token = secrets.token_urlsafe(24)
    store.put(
        token,
        {"ans": a + b, "fp": fp_id or "", "ip": resolve_request_identity(request).client_ip},
        TOKEN_EXPIRY,
    )
    return HTMLResponse(_challenge_html(a, b, token))


def _challenge_ok(record: dict | None, answer: str, ip: str, fp_id: str | None) -> bool:
    """Whether the (already consumed) challenge ``record`` is answered correctly by the client it was issued to."""
    if not record:
        return False
    if BIND_IP and record.get("ip") != ip:
        return False
    if record.get("fp") and fp_id != record["fp"]:
        return False
    try:
        return hmac.compare_digest(str(int(answer)), str(record.get("ans")))
    except ValueError:
        return False


def _log_success(ip: str, fingerprint: str, ua: str) -> None:
    try:
        os.makedirs(os.path.dirname(CAPTCHA_SUCCESS_LOG), exist_ok=True)
        with open(CAPTCHA_SUCCESS_LOG, "a") as f:
            json.dump(
                {
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    "ip": ip,
                    "fingerprint": fingerprint,
                    "ua": ua,
                    "result": "success",
                    # Self-reported by an unauthenticated endpoint: telemetry, not trusted training feedback.
                    "source": "captcha_service",
                },
                f,
            )
            f.write("\n")
    except Exception as e:
        logger.error(f"Failed to log CAPTCHA success: {e}")


@app.post("/solve")
async def solve(
    answer: str = Form(...),
    token: str = Form(...),
    request: Request = None,
    fp_id: str | None = Cookie(None),
):
    if _rate_limited(request, "solve"):
        return JSONResponse({"success": False}, status_code=429)
    ip = resolve_request_identity(request).client_ip
    with trace_span("captcha.consume_challenge"):
        record = store.take(token)  # consumed whether or not the answer is right: one attempt per challenge
    if not _challenge_ok(record, answer, ip, fp_id):
        return JSONResponse({"success": False})
    fingerprint = fp_id or record.get("fp") or ""
    with trace_span(
        "captcha.issue_token",
        attributes={"ip": ip, "fingerprint": fingerprint},
    ):
        final_token = _sign(
            {
                "ip": ip,
                "fp": fingerprint,
                "ts": int(datetime.datetime.now(datetime.UTC).timestamp()),
                "jti": secrets.token_hex(8),
            }
        )
    _log_success(ip, fingerprint, request.headers.get("user-agent", "") if request else "")
    return JSONResponse({"success": True, "token": final_token})


async def _verification_inputs(request: Request, token: str | None, ip: str | None):
    """The token and address to verify, from query parameters or reCAPTCHA-style form fields (secret, response, remoteip)."""
    form = {}
    if "form" in request.headers.get("content-type", ""):
        form = await request.form()
    supplied_secret = form.get("secret")
    if supplied_secret is not None and not (
        CAPTCHA_SECRET and hmac.compare_digest(str(supplied_secret), CAPTCHA_SECRET)
    ):
        return None, None
    return token or form.get("response"), ip or form.get("remoteip")


@app.post("/verify")
async def verify(request: Request, token: str | None = None, ip: str | None = None):
    token, ip = await _verification_inputs(request, token, ip)
    data = _unsign(token) if token else None
    if not data or not ip or data.get("ip") != ip:
        return {"success": False}
    if (
        int(datetime.datetime.now(datetime.UTC).timestamp()) - data.get("ts", 0)
        > TOKEN_EXPIRY
    ):
        return {"success": False}
    return {"success": True}


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
