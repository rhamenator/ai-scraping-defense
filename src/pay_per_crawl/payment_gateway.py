from __future__ import annotations

"""Payment gateway abstractions and provider implementations."""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import httpx


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
        if not self.base_url:
            logging.warning("Payment gateway URL not configured")
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
            return resp.json()
        except Exception as exc:  # pragma: no cover - network issues
            logging.error(
                "Payment request failed (%s): %s",
                _redact(self.api_key),
                exc,
            )
            return None

    async def create_customer(self, token: str, name: str, purpose: str) -> bool:
        payload = {"token": token, "name": name, "purpose": purpose}
        data = await self._request("POST", "/customers", json=payload)
        return bool(data and data.get("success"))

    async def charge(self, token: str, amount: float) -> bool:
        payload = {"token": token, "amount": amount}
        data = await self._request("POST", "/charge", json=payload)
        return bool(data and data.get("success"))

    async def refund(self, token: str, amount: float) -> bool:
        payload = {"token": token, "amount": amount}
        data = await self._request("POST", "/refund", json=payload)
        return bool(data and data.get("success"))

    async def get_balance(self, token: str) -> Optional[float]:
        data = await self._request("GET", f"/customers/{token}")
        if data and "balance" in data:
            try:
                return float(data["balance"])
            except (TypeError, ValueError):  # pragma: no cover - invalid response
                return None
        return None


# ---------------------------------------------------------------------------
# Provider-specific gateways
# ---------------------------------------------------------------------------

class StripeGateway(HTTPPaymentGateway):
    """Stripe-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.stripe.com/v1"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("STRIPE_API_KEY"), timeout=timeout)


class PayPalGateway(HTTPPaymentGateway):
    """PayPal-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.paypal.com/v1"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("PAYPAL_API_KEY"), timeout=timeout)


class BraintreeGateway(HTTPPaymentGateway):
    """Braintree-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.braintreegateway.com"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("BRAINTREE_API_KEY"), timeout=timeout)


class SquareGateway(HTTPPaymentGateway):
    """Square-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://connect.squareup.com/v2"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("SQUARE_API_KEY"), timeout=timeout)


class AdyenGateway(HTTPPaymentGateway):
    """Adyen-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://checkout.adyen.com/v69"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("ADYEN_API_KEY"), timeout=timeout)


class AuthorizeNetGateway(HTTPPaymentGateway):
    """Authorize.Net-specific gateway using its REST API."""

    def __init__(self, api_key: Optional[str] = None, *, timeout: float = 10.0) -> None:
        base_url = "https://api.authorize.net/xml/v1"
        super().__init__(base_url=base_url, api_key=api_key or os.getenv("AUTHORIZE_NET_API_KEY"), timeout=timeout)


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
