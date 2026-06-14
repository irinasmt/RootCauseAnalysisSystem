"""Repository for persisting orders to PostgreSQL."""
from __future__ import annotations

import psycopg2


class OrderRepository:
    def __init__(self, conn: psycopg2.extensions.connection) -> None:
        self._conn = conn

    def insert(self, order) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (order_id, customer_id, total_amount, status, promo_code)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order.order_id, order.customer_id, order.total_amount, order.status, order.promo_code),
            )
        self._conn.commit()
