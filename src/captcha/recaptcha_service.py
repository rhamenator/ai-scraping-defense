from fastapi import FastAPI, HTTPException
import httpx
import os
import datetime
import logging
from src.shared.config import get_secret

app = FastAPI()

CAPTCHA_VERIFICATION_URL = os.getenv(
    "CAPTCHA_VERIFICATION_URL", "https://www.google.com/recaptcha/api/siteverify"
)
CAPTCHA_SECRET = get_secret("CAPTCHA_SECRET_FILE") or os.getenv("CAPTCHA_SECRET")
CAPTCHA_SUCCESS_LOG = os.getenv("CAPTCHA_SUCCESS_LOG", "/app/logs/captcha_success.log")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@app.post("/verify")
async def verify_captcha(token: str, ip: str):
    if not CAPTCHA_SECRET:
        logger.error("CAPTCHA secret not configured")
        raise HTTPException(
            status_code=500, detail="CAPTCHA verification not configured"
        )
    payload = {"secret": CAPTCHA_SECRET, "response": token, "remoteip": ip}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                CAPTCHA_VERIFICATION_URL, data=payload, timeout=10.0
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as e:
        logger.error(f"Error verifying CAPTCHA for IP {ip}: {e}")
        raise HTTPException(status_code=502, detail="CAPTCHA verification failed")
    success = bool(result.get("success"))
    if success:
        try:
            os.makedirs(os.path.dirname(CAPTCHA_SUCCESS_LOG), exist_ok=True)
            with open(CAPTCHA_SUCCESS_LOG, "a") as f:
                f.write(
                    f"{datetime.datetime.now(datetime.timezone.utc).isoformat()},{ip}\n"
                )
        except Exception as e:
            logger.error(f"Failed to log CAPTCHA success: {e}")
    return {"success": success}
