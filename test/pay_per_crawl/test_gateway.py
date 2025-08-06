import asyncio
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
from src.pay_per_crawl.tokens import tokenize_card


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
                gateway = HTTPPaymentGateway(base_url="http://api", api_key="k")
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
        token = tokenize_card("4111111111111111")
        self.assertNotIn("4111", token)
        gateway = HTTPPaymentGateway(base_url="http://api", api_key="old")
        gateway.rotate_api_key("new")
        self.assertEqual(gateway.api_key, "new")

    def test_audit_logging(self):
        async def run():
            gateway = HTTPPaymentGateway(base_url="http://api", api_key="k")
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
