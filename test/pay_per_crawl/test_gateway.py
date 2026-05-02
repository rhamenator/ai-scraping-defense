import asyncio
import secrets
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.pay_per_crawl.payment_gateway import (
    AdyenGateway,
    AuthorizeNetGateway,
    BraintreeGateway,
    HTTPPaymentGateway,
    PayPalGateway,
    SquareGateway,
    StripeGateway,
    get_payment_gateway,
)
from src.pay_per_crawl.tokens import secure_hash, tokenize_card


class TestPaymentGateway(unittest.TestCase):
    def test_charge_returns_false_without_config(self):
        gateway = HTTPPaymentGateway(base_url=None, api_key=None)
        result = asyncio.run(gateway.charge("tok", 1.0))
        self.assertFalse(result)

    def test_create_and_balance(self):
        async def run():
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"success": True}
            mock_resp.raise_for_status.return_value = None
            mock_client.__aenter__.return_value.request.return_value = mock_resp
            with patch(
                "src.pay_per_crawl.payment_gateway.httpx.AsyncClient",
                return_value=mock_client,
            ):
                gateway = HTTPPaymentGateway(base_url="https://api", api_key="k")
                ok = await gateway.create_customer("tok", "name", "purpose")
                self.assertTrue(ok)

            mock_resp2 = MagicMock()
            mock_resp2.json.return_value = {"balance": 5.0}
            mock_resp2.raise_for_status.return_value = None
            mock_client.__aenter__.return_value.request.return_value = mock_resp2
            with patch(
                "src.pay_per_crawl.payment_gateway.httpx.AsyncClient",
                return_value=mock_client,
            ):
                bal = await gateway.get_balance("tok")
                self.assertEqual(bal, 5.0)

        asyncio.run(run())

    def test_get_payment_gateway(self):
        gateway = get_payment_gateway("stripe")
        self.assertIsInstance(gateway, StripeGateway)

        gateway = get_payment_gateway("paypal")
        self.assertIsInstance(gateway, PayPalGateway)

        gateway = get_payment_gateway("braintree")
        self.assertIsInstance(gateway, BraintreeGateway)

        gateway = get_payment_gateway("square")
        self.assertIsInstance(gateway, SquareGateway)

        gateway = get_payment_gateway("adyen")
        self.assertIsInstance(gateway, AdyenGateway)

        gateway = get_payment_gateway("authorizenet")
        self.assertIsInstance(gateway, AuthorizeNetGateway)

    def test_tokenize_and_rotate(self):
        secret = secrets.token_urlsafe(8)
        token = tokenize_card("4111 1111-1111 1111", secret=secret)
        self.assertNotIn("4111", token)
        with self.assertRaisesRegex(ValueError, "invalid card number"):
            tokenize_card("1234", secret=secret)
        gateway = HTTPPaymentGateway(base_url="https://api", api_key="old")
        gateway.rotate_api_key("new")
        self.assertEqual(gateway.api_key, "new")

    def test_tokenize_12_digit_luhn_card(self):
        token = tokenize_card("100000000008", secret=secrets.token_urlsafe(8))
        self.assertTrue(token)
        self.assertNotIn("1000", token)

    def test_tokenize_19_digit_luhn_card(self):
        token = tokenize_card("1000000000000000009", secret=secrets.token_urlsafe(8))
        self.assertTrue(token)
        self.assertNotIn("1000", token)

    def test_secure_hash(self):
        secret = secrets.token_urlsafe(8)
        h1 = secure_hash("data", secret=secret)
        h2 = secure_hash("data", secret=secret)
        self.assertEqual(h1, h2)
        h3 = secure_hash("data", secret=secrets.token_urlsafe(8))
        self.assertNotEqual(h1, h3)

    def test_audit_logging(self):
        async def run():
            gateway = HTTPPaymentGateway(base_url="https://api", api_key="k")

            with self.assertLogs("pay_per_crawl.audit", level="INFO") as cm:
                with patch.object(
                    HTTPPaymentGateway,
                    "_request",
                    new=AsyncMock(return_value={"success": True}),
                ):
                    await gateway.charge("tok", 1.0)
            self.assertTrue(any("charge" in msg for msg in cm.output))

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
