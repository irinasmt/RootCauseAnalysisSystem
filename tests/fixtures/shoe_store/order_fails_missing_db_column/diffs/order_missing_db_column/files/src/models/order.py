"""ORM model for the orders table."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    order_id: str
    customer_id: str
    total_amount: float
    status: str
    promo_code: Optional[str] = None  # added in migration 0012
