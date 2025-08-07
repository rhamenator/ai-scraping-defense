import importlib
import logging
from typing import List

import httpx
import pytest


@pytest.mark.asyncio
async def test_report_attack_valid_url(monkeypatch, caplog):
    provider_url = "https://provider.example/report"
    internal_url = "http://internal.example/report"

    monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
    monkeypatch.setenv("DDOS_PROTECTION_PROVIDER_URL", provider_url)
    monkeypatch.setenv("DDOS_PROTECTION_API_KEY", "api-key")
    monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", internal_url)

    from src.util import ddos_protection

    importlib.reload(ddos_protection)

    called_urls: List[str] = []

    async def mock_post(self, url, *args, **kwargs):
        called_urls.append(url)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await ddos_protection.report_attack("1.2.3.4")

    assert result is True
    assert called_urls == [provider_url]


@pytest.mark.asyncio
async def test_report_attack_invalid_url(monkeypatch, caplog):
    provider_url = "http://provider.example/report"
    internal_url = "http://internal.example/report"

    monkeypatch.setenv("ENABLE_DDOS_PROTECTION", "true")
    monkeypatch.setenv("DDOS_PROTECTION_PROVIDER_URL", provider_url)
    monkeypatch.setenv("DDOS_PROTECTION_API_KEY", "api-key")
    monkeypatch.setenv("DDOS_INTERNAL_ENDPOINT", internal_url)

    from src.util import ddos_protection

    importlib.reload(ddos_protection)

    called_urls: List[str] = []

    async def mock_post(self, url, *args, **kwargs):
        called_urls.append(url)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with caplog.at_level(logging.ERROR):
        result = await ddos_protection.report_attack("1.2.3.4")

    assert result is True
    assert called_urls == [internal_url]
    assert "must start with 'https://'" in caplog.text
