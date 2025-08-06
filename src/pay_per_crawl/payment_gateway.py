from __future__ import annotations

"""Payment gateway abstractions and provider implementations."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from .tokens import tokenize_card

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _redact(value: Optional[str]) -> str:
    """Return a redacted representation of a secret value."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

AUDIT_LOG_FILE = os.getenv("PAYMENT_GATEWAY_AUDIT_LOG")
AUDIT_LOGGER = logging.getLogger("pay_per_crawl.audit")
if AUDIT_LOG_FILE and not AUDIT_LOGGER.handlers:
    try:
        handler = logging.FileHandler(AUDIT_LOG_FILE)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        AUDIT_LOGGER.addHandler(handler)
    except OSError:  # pragma: no cover - filesystem issues
        logging.error("Unable to write audit log to %s", AUDIT_LOG_FILE)
AUDIT_LOGGER.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Base Gateway
# ---------------------------------------------------------------------------


class BaseGateway(ABC):
    """Abstract payment gateway interface."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self.timeout = timeout

    @abstractmethod
    async def create_customer(self, token: str, name: str, purpose: str) -> bool:
        pass

    @abstractmethod
    async def charge(self, token: str, amount: float) -> bool:
        pass

    @abstractmethod
    async def refund(self, token: str, amount: float) -> bool:
        pass

    @abstractmethod
    async def get_balance(self, token: str) -> Optional[float]:
        pass


# ---------------------------------------------------------------------------
# Generic HTTP Gateway
# ---------------------------------------------------------------------------


class HTTPPaymentGateway(BaseGateway):
    """Generic wrapper around a REST-style payment provider."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        *,
        timeout: float = 10.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.base_url = base_url or os.getenv("PAYMENT_GATEWAY_URL")
        self.api_key = api_key or os.getenv("PAYMENT_GATEWAY_KEY")
        self.audit_logger = AUDIT_LOGGER
        if not self.base_url:
            logging.warning("Payment gateway URL not configured")
        elif not self.base_url.lower().startswith("https://"):
            raise ValueError("Payment gateway URL must use HTTPS")
        if not self.api_key:
            logging.warning("Payment gateway API key not configured")

    async def _request(self, method: str, path: str, **kwargs) -> Optional[dict]:
        if not self.base_url or not self.api_key:
            return None
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.request(
                    method, f"{self.base_url}{path}", headers=headers, **kwargs
                )
            resp.raise_for_status()
            try:
                return resp.json()
            except ValueError:
                logging.error("Invalid JSON from payment provider")
                return None
        except Exception as exc:  # pragma: no cover - network issues
            logging.error(
                "Payment request failed (%s): %s",
                _redact(self.api_key),
                exc,
            )
            return None

    def _audit(self, action: str, token: str, amount: float = 0.0) -> None:
        if not self.audit_logger:
            return
        redacted = _redact(token)
        msg = f"{action} token={redacted}"
        if amount:
            msg += f" amount={amount}"
        self.audit_logger.info(msg)

    async def create_customer(self, token: str, name: str, purpose: str) -> bool:
        self._audit("create_customer", token)
        payload = {"token": token, "name": name, "purpose": purpose}
        data = await self._request("POST", "/customers", json=payload)
        return bool(data and data.get("success"))

    async def charge(self, token: str, amount: float) -> bool:
        self._audit("charge", token, amount)
        payload = {"token": token, "amount": amount}
        data = await self._request("POST", "/charge", json=payload)
        return bool(data and data.get("success"))

    async def refund(self, token: str, amount: float) -> bool:
        self._audit("refund", token, amount)
        payload = {"token": token, "amount": amount}
        data = await self._request("POST", "/refund", json=payload)
        return bool(data and data.get("success"))

    async def get_balance(self, token: str) -> Optional[float]:
        self._audit("get_balance", token)
        data = await self._request("GET", f"/customers/{token}")
        if data and "balance" in data:
            try:
                return float(data["balance"])
            except (TypeError, ValueError):  # pragma: no cover - invalid response
                return None
        return None

    def rotate_api_key(self, new_key: str) -> None:
        """Rotate the API key used for requests."""
        self.api_key = new_key
        logging.info("Payment gateway API key rotated: %s", _redact(new_key))

    async def charge_card(
        self,
        card_number: str,
        amount: float,
        *,
        salt: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> bool:
        """Tokenize ``card_number`` and charge the resulting token."""
        token = tokenize_card(card_number, salt=salt, secret=secret)
        return await self.charge(token, amount)


# ---------------------------------------------------------------------------
# Provider-specific gateways
# ---------------------------------------------------------------------------


class StripeGateway(HTTPPaymentGateway):
    """Stripe-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.stripe.com/v1"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("STRIPE_API_KEY"),
            timeout=timeout,
        )


class PayPalGateway(HTTPPaymentGateway):
    """PayPal-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.paypal.com/v1"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("PAYPAL_API_KEY"),
            timeout=timeout,
        )


class BraintreeGateway(HTTPPaymentGateway):
    """Braintree-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.braintreegateway.com"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("BRAINTREE_API_KEY"),
            timeout=timeout,
        )


class SquareGateway(HTTPPaymentGateway):
    """Square-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://connect.squareup.com/v2"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("SQUARE_API_KEY"),
            timeout=timeout,
        )


class AdyenGateway(HTTPPaymentGateway):
    """Adyen-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://checkout.adyen.com/v69"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("ADYEN_API_KEY"),
            timeout=timeout,
        )


class AuthorizeNetGateway(HTTPPaymentGateway):
    """Authorize.Net-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.authorize.net/xml/v1"
        super().__init__(
            base_url=base_url,
            api_key=api_key or os.getenv("AUTHORIZE_NET_API_KEY"),
            timeout=timeout,
        )


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def get_payment_gateway(provider: Optional[str] = None) -> BaseGateway:
    """Return a gateway instance based on ``provider`` or env vars."""
    provider = provider or os.getenv("PAYMENT_GATEWAY_PROVIDER", "http")
    provider = provider.lower()
    if provider == "stripe":
        return StripeGateway()
    if provider == "paypal":
        return PayPalGateway()
    if provider == "braintree":
        return BraintreeGateway()
    if provider == "square":
        return SquareGateway()
    if provider == "adyen":
        return AdyenGateway()
    if provider in {"authorizenet", "authorize_net", "authorize.net"}:
        return AuthorizeNetGateway()
    return HTTPPaymentGateway()


# Backwards compatibility
PaymentGateway = HTTPPaymentGateway
