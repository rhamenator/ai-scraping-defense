import base64  # Token encoding
import datetime  # Timestamp handling
import hashlib  # Signature hashing
import hmac
import json
import logging
import os
import secrets
import time

from fastapi import Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.shared.config import get_runtime_setting, get_secret
from src.shared.middleware import create_app
from src.shared.observability import (
    HealthCheckResult,
    register_health_check,
    trace_span,
)
from src.shared.request_identity import resolve_request_identity

from .access_requests import AccessRequestStore
from .challenge_store import ChallengeStore
from .questions import answers_match, generate_question, normalize_question_type

CAPTCHA_SECRET = get_secret("CAPTCHA_SECRET_FILE") or os.getenv("CAPTCHA_SECRET")
CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "builtin").strip().lower() or "builtin"
_INITIAL_CAPTCHA_PROVIDER = CAPTCHA_PROVIDER
CAPTCHA_SUCCESS_LOG = os.getenv("CAPTCHA_SUCCESS_LOG", "/app/logs/captcha_success.log")
TOKEN_EXPIRY = int(os.getenv("CAPTCHA_TOKEN_EXPIRY_SECONDS", 300))
# A challenge may be answered from the address it was issued to (set false for users whose address changes mid-flow).
BIND_IP = os.getenv("CAPTCHA_BIND_IP", "true").lower() == "true"
# Challenges and solve attempts per client address per minute; 0 disables the limit.
RATE_LIMIT_PER_MINUTE = int(os.getenv("CAPTCHA_RATE_LIMIT_PER_MINUTE", 30))
# A correct answer that arrives faster than a person could read and type it is a bot signal. Like a missing or wrong
# client proof, it never blocks anyone: the attempt fails and the visitor is asked again with a fresh challenge. Set to 0
# to disable.
MIN_SOLVE_SECONDS = float(os.getenv("CAPTCHA_MIN_SOLVE_SECONDS", 1.5))
# The page sends a small proof computed from the challenge id and the answer. The project is open source, so anyone can copy
# the function; it only filters clients that post the form without running the page. Set to false to disable.
REQUIRE_PROOF = os.getenv("CAPTCHA_REQUIRE_PROOF", "true").lower() == "true"
MANUAL_REQUESTS_ENABLED = os.getenv("CAPTCHA_MANUAL_REQUESTS_ENABLED", "false").lower() == "true"
_INITIAL_MANUAL_REQUESTS_ENABLED = MANUAL_REQUESTS_ENABLED
store = ChallengeStore()
request_store = AccessRequestStore()

app = create_app()


def _active_provider() -> str:
    if CAPTCHA_PROVIDER != _INITIAL_CAPTCHA_PROVIDER:
        return CAPTCHA_PROVIDER
    return get_runtime_setting("CAPTCHA_PROVIDER", CAPTCHA_PROVIDER).strip().lower() or "builtin"


def _manual_requests_enabled() -> bool:
    if MANUAL_REQUESTS_ENABLED != _INITIAL_MANUAL_REQUESTS_ENABLED:
        return MANUAL_REQUESTS_ENABLED
    return get_runtime_setting("CAPTCHA_MANUAL_REQUESTS_ENABLED", "true" if MANUAL_REQUESTS_ENABLED else "false").lower() == "true"


def _ensure_builtin_enabled() -> None:
    if _active_provider() != "builtin":
        raise HTTPException(
            status_code=404,
            detail="Built-in CAPTCHA is disabled when an external provider is configured",
        )


@register_health_check(app, "custom_captcha", critical=True)
async def _captcha_health() -> HealthCheckResult:
    provider = _active_provider()
    if provider != "builtin":
        return HealthCheckResult.healthy({"provider": provider, "builtin_enabled": False})
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
  min-height: 100vh;
}}
.container {{
  background: #fff;
  color: #333;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 0 10px rgba(0,0,0,0.3);
  max-width: 460px;
}}
button{{padding:6px 12px;margin-top:8px;}}
.qtypes{{margin-bottom:12px;font-size:0.9rem;}}
.qtypes a{{margin-right:8px;}}
.request-box{{margin-top:18px;padding-top:12px;border-top:1px solid #ddd;}}
</style>
</head>
<body>
<div class='container'>
<h2>Prove you're human</h2>
<nav class='qtypes' aria-label='Question type'>
  Question type:
  <a href='/challenge?type=math'>Math</a>
  <a href='/challenge?type=color'>Colour word</a>
  <a href='/challenge?type=word'>Type a word</a>
</nav>
<p id='question-text'>{escaped_prompt}</p>
<button type='button' id='read-aloud'>Read question aloud</button>
<form id='cform'>
<input name='answer' required autofocus>
<input type='hidden' name='token' value='{escaped_token}'>
<button type='submit'>Submit</button>
</form>
<div id='result' role='status' aria-live='polite'></div>
{manual_request_html}
</div>
<script>
function proof(text) {{
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {{ h ^= text.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }}
  return h.toString(16).padStart(8, '0');
}}
document.getElementById('read-aloud').addEventListener('click', ()=>{{
  if ('speechSynthesis' in window) {{
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(document.getElementById('question-text').textContent));
  }}
}});
document.getElementById('cform').addEventListener('submit', async (e)=>{{
  e.preventDefault();
  const data = new FormData(e.target);
  data.set('proof', proof(data.get('token') + ':' + String(data.get('answer')).trim()));
  const res = await fetch('/solve', {{method: 'POST', body: data}});
  const js = await res.json();
  const result = document.getElementById('result');
  if (js.success) {{
    result.textContent = 'Passed! Token copied to clipboard';
    if (js.token){{navigator.clipboard.writeText(js.token);}}
  }} else if (js.retry) {{
    result.textContent = 'Please take a moment, then try again. Loading a new question...';
    setTimeout(()=>location.reload(), 3000);
  }} else {{
    // A challenge can be answered once, so a miss needs a fresh question.
    result.textContent = 'Not quite. Loading a new question...';
    setTimeout(()=>location.reload(), 1500);
  }}
}});
const reqForm = document.getElementById('reqform');
if (reqForm) {{
  reqForm.addEventListener('submit', async (e)=>{{
    e.preventDefault();
    const res = await fetch('/request-access', {{method: 'POST', body: new FormData(e.target)}});
    const js = await res.json();
    document.getElementById('req-result').textContent = js.message || 'Request updated.';
  }});
}}
</script>
<script src='/__fp.js' async></script>
</body>
</html>"""


def _manual_request_section() -> str:
    if not _manual_requests_enabled():
        return ""
    if request_store.is_paused():
        return "<div class='request-box'><p>Access requests are currently paused.</p></div>"
    return (
        "<div class='request-box'>"
        "<h3>Having trouble?</h3>"
        "<p>Ask an admin to review temporary access (optional note, max 200 characters, no personal data).</p>"
        "<form id='reqform'>"
        "<textarea name='note' maxlength='200' rows='2' cols='40' placeholder='Optional plain-text note'></textarea><br>"
        "<button type='submit'>Ask admin to let me in</button>"
        "</form>"
        "<div id='req-result' role='status' aria-live='polite'></div>"
        "</div>"
    )


def _challenge_html(prompt_text: str, token: str) -> str:
    from html import escape

    return _PAGE_TEMPLATE.format(
        escaped_prompt=escape(prompt_text),
        escaped_token=escape(token),
        manual_request_html=_manual_request_section(),
    )


def _proof(token: str, answer: str) -> str:
    """FNV-1a (32-bit) of ``token:answer`` as 8 hex digits; the page computes the same value in JavaScript."""
    value = 0x811C9DC5
    for char in f"{token}:{answer.strip()}":
        value = ((value ^ ord(char)) * 0x01000193) & 0xFFFFFFFF
    return f"{value:08x}"


def _rate_limited(request: Request, action: str) -> bool:
    ip = resolve_request_identity(request).client_ip
    return not store.allow(f"{action}:{ip}", RATE_LIMIT_PER_MINUTE)


@app.get("/challenge", response_class=HTMLResponse)
async def challenge_page(request: Request, type: str = "math", fp_id: str | None = Cookie(None)):
    _ensure_builtin_enabled()
    if not CAPTCHA_SECRET:
        raise HTTPException(status_code=500, detail="CAPTCHA not configured")
    if _rate_limited(request, "challenge"):
        raise HTTPException(status_code=429, detail="Too many challenges")
    qtype, prompt_text, expected = generate_question(normalize_question_type(type))
    # The page carries only a random id; the answer and the client it was issued to stay on the server.
    token = secrets.token_urlsafe(24)
    store.put(
        token,
        {
            "ans": expected,
            "type": qtype,
            "fp": fp_id or "",
            "ip": resolve_request_identity(request).client_ip,
            "iat": time.time(),
        },
        TOKEN_EXPIRY,
    )
    return HTMLResponse(_challenge_html(prompt_text, token))


def _answered_correctly(record: dict | None, answer: str, ip: str, fp_id: str | None) -> bool:
    """Whether the (already consumed) challenge ``record`` is answered correctly by the client it was issued to."""
    if not record:
        return False
    if BIND_IP and record.get("ip") != ip:
        return False
    if record.get("fp") and fp_id != record["fp"]:
        return False
    return answers_match(str(record.get("ans", "")), answer)


def _looks_automated(record: dict, token: str, answer: str, proof: str) -> bool:
    """A correct answer that came too fast, or without the page's proof: ask again, never block."""
    if MIN_SOLVE_SECONDS > 0 and time.time() - float(record.get("iat", 0)) < MIN_SOLVE_SECONDS:
        return True
    return REQUIRE_PROOF and not hmac.compare_digest(proof.strip().lower().encode("utf-8"), _proof(token, answer).encode("utf-8"))


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
    proof: str = Form(""),
    request: Request = None,
    fp_id: str | None = Cookie(None),
):
    _ensure_builtin_enabled()
    if _rate_limited(request, "solve"):
        return JSONResponse({"success": False}, status_code=429)
    ip = resolve_request_identity(request).client_ip
    with trace_span("captcha.consume_challenge"):
        record = store.take(token)  # consumed whether or not the answer is right: one attempt per challenge
    if not _answered_correctly(record, answer, ip, fp_id):
        return JSONResponse({"success": False})
    if _looks_automated(record, token, answer, proof):
        # The challenge is already consumed, so the visitor simply gets a new one; nothing is blocked or labelled.
        return JSONResponse({"success": False, "retry": True})
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
        CAPTCHA_SECRET and hmac.compare_digest(str(supplied_secret).encode("utf-8"), CAPTCHA_SECRET.encode("utf-8"))
    ):
        return None, None
    return token or form.get("response"), ip or form.get("remoteip")


@app.post("/verify")
async def verify(request: Request, token: str | None = None, ip: str | None = None):
    _ensure_builtin_enabled()
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


_REQUEST_MESSAGES = {
    "queued": ("Your request has been queued for admin review.", 200),
    "already_pending": ("You already have a pending access request.", 429),
    "cooldown": ("Please wait before submitting another access request.", 429),
    "paused": ("Access requests are currently paused; nothing was queued.", 503),
}


@app.post("/request-access")
async def request_access(request: Request, note: str = Form("")):
    _ensure_builtin_enabled()
    if not _manual_requests_enabled():
        raise HTTPException(status_code=404, detail="Manual access requests are disabled")
    ip = resolve_request_identity(request).client_ip
    ok, reason, rec = request_store.submit(ip, note)
    message, status_code = _REQUEST_MESSAGES[reason]
    payload = {"success": ok, "status": reason, "message": message}
    if rec:
        payload["id"] = rec["id"]
    return JSONResponse(payload, status_code=status_code)


if __name__ == "__main__":  # pragma: no cover - manual execution
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
