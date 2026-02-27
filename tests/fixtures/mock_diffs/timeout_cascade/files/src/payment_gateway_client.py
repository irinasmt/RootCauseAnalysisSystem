"""HTTP client for the payment gateway — configurable timeout + retry."""
from __future__ import annotations

import os
import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "https://payments.internal")
TIMEOUT_SECONDS = float(os.getenv("GATEWAY_TIMEOUT", "15"))  # was 30
MAX_RETRIES = int(os.getenv("GATEWAY_MAX_RETRIES", "3"))


class PaymentGatewayClient:
    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def charge(self, amount: float, token: str) -> dict:
        response = self._client.post(
            f"{GATEWAY_URL}/charge",
            json={"amount": amount, "token": token},
        )
        response.raise_for_status()
        return response.json()

    def refund(self, charge_id: str) -> dict:
        response = self._client.post(
            f"{GATEWAY_URL}/refund",
            json={"charge_id": charge_id},
        )
        response.raise_for_status()
        return response.json()
