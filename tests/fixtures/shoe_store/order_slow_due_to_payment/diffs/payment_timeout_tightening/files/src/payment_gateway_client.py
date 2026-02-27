"""Payment client used by order-service checkout flow."""
from __future__ import annotations

import os
import httpx

PAYMENT_GATEWAY_URL = os.getenv("PAYMENT_GATEWAY_URL", "https://gateway.payments.example")
PAYMENT_TIMEOUT_SECONDS = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "10"))
PAYMENT_MAX_RETRIES = int(os.getenv("PAYMENT_MAX_RETRIES", "2"))


class PaymentGatewayClient:
    def __init__(self, timeout: float = PAYMENT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def charge(self, amount: float, token: str) -> dict:
        response = self._client.post(
            f"{PAYMENT_GATEWAY_URL}/charge",
            json={"amount": amount, "token": token},
        )
        response.raise_for_status()
        return response.json()
