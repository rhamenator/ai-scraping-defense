import base64
import datetime
import hashlib
import hmac
import json
import logging
import os
import secrets

from fastapi import Cookie, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.shared.config import get_secret
from src.shared.middleware import create_app

app = create_app()

CAPTCHA_SECRET = get_secret("CAPTCHA_SECRET_FILE") or os.getenv("CAPTCHA_SECRET")
CAPTCHA_SUCCESS_LOG = os.getenv("CAPTCHA_SUCCESS_LOG", "/app/logs/captcha_success.log")
TOKEN_EXPIRY = int(os.getenv("CAPTCHA_TOKEN_EXPIRY_SECONDS", 300))

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


@app.get("/challenge", response_class=HTMLResponse)
async def challenge_page(fp_id: str | None = Cookie(None)):
    if not CAPTCHA_SECRET:
        raise HTTPException(status_code=500, detail="CAPTCHA not configured")
    a = secrets.randbelow(8) + 1
    b = secrets.randbelow(8) + 1
    expiry = int(datetime.datetime.now(datetime.UTC).timestamp() + TOKEN_EXPIRY)
    token = _sign({"ans": a + b, "fp": fp_id, "exp": expiry})
    from html import escape

    escaped_token = escape(token)
    html = f"""<!DOCTYPE html>
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
<div id='result'></div>
</div>
<script>
document.getElementById('cform').addEventListener('submit', async (e)=>{{
  e.preventDefault();
  const data = new FormData(e.target);
  const res = await fetch('/solve', {{method: 'POST', body: data}});
  const js = await res.json();
  document.getElementById('result').textContent = js.success ? 'Passed! Token copied to clipboard' : 'Try again';
  if (js.success && js.token){{navigator.clipboard.writeText(js.token);}}
}});
</script>
<script src='/__fp.js' async></script>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/solve")
async def solve(
    answer: str = Form(...),
    token: str = Form(...),
    request: Request = None,
    fp_id: str | None = Cookie(None),
):
    data = _unsign(token)
    if not data or data.get("exp", 0) < int(
        datetime.datetime.now(datetime.UTC).timestamp()
    ):
        return JSONResponse({"success": False})
    try:
        ans_int = int(answer)
    except ValueError:
        return JSONResponse({"success": False})
    if ans_int != data.get("ans"):
        return JSONResponse({"success": False})
    ip = request.client.host if request and request.client else "unknown"
    fingerprint = fp_id or data.get("fp") or ""
    final_token = _sign(
        {
            "ip": ip,
            "fp": fingerprint,
            "ts": int(datetime.datetime.now(datetime.UTC).timestamp()),
        }
    )
    ua = request.headers.get("user-agent", "") if request else ""
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
                },
                f,
            )
            f.write("\n")
    except Exception as e:
        logger.error(f"Failed to log CAPTCHA success: {e}")
    return JSONResponse({"success": True, "token": final_token})


@app.post("/verify")
async def verify(token: str, ip: str):
    data = _unsign(token)
    if not data or data.get("ip") != ip:
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
