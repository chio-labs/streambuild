from __future__ import annotations

import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from kafka import KafkaProducer

PRODUCTS: list[dict[str, str | float]] = [
    {"name": "Widget Pro", "category": "electronics", "price": 29.99},
    {"name": "Gadget Mini", "category": "electronics", "price": 14.99},
    {"name": "Super Cable", "category": "electronics", "price": 9.99},
    {"name": "Cotton Tee", "category": "apparel", "price": 19.99},
    {"name": "Denim Jacket", "category": "apparel", "price": 79.99},
    {"name": "Running Shoes", "category": "apparel", "price": 64.99},
    {"name": "Coffee Beans 1kg", "category": "grocery", "price": 12.49},
    {"name": "Olive Oil 750ml", "category": "grocery", "price": 8.99},
    {"name": "Notebook A5", "category": "office", "price": 4.99},
    {"name": "Ballpoint Pen 10pk", "category": "office", "price": 6.49},
]

REGIONS: list[str] = ["us-west", "us-east", "eu-west", "ap-south"]

CUSTOMER_IDS: list[str] = [f"cust_{i:04d}" for i in range(1, 51)]

STATUS_TRANSITIONS: dict[str, list[str]] = {
    "created": ["paid", "cancelled"],
    "paid": ["shipped", "refunded"],
    "shipped": ["delivered"],
}

TERMINAL_STATUSES: set[str] = {"delivered", "cancelled", "refunded"}


@dataclass
class ActiveOrder:
    order_id: str
    customer_id: str
    product: dict[str, str | float]
    quantity: int
    region: str
    status: str
    created_at: datetime
    ticks_until_next: int = field(default=0)


def build_message(order: ActiveOrder, event_at: datetime) -> dict[str, str | None]:
    return {
        "order_id": order.order_id,
        "customer_id": order.customer_id,
        "product": str(order.product["name"]),
        "category": str(order.product["category"]),
        "quantity": str(order.quantity),
        "unit_price": str(order.product["price"]),
        "status": order.status,
        "region": order.region,
        "event_at": event_at.isoformat(timespec="milliseconds"),
    }


def create_new_order(event_at: datetime) -> ActiveOrder:
    return ActiveOrder(
        order_id=f"ord_{uuid.uuid4().hex[:12]}",
        customer_id=random.choice(CUSTOMER_IDS),
        product=random.choice(PRODUCTS),
        quantity=random.randint(1, 5),
        region=random.choice(REGIONS),
        status="created",
        created_at=event_at,
        ticks_until_next=random.randint(2, 6),
    )


def advance_order(order: ActiveOrder) -> str | None:
    next_statuses: list[str] | None = STATUS_TRANSITIONS.get(order.status)
    if next_statuses is None:
        return None
    weights: list[float] = []
    for status in next_statuses:
        if status in ("cancelled", "refunded"):
            weights.append(0.15)
        else:
            weights.append(0.85)
    chosen: str = random.choices(next_statuses, weights=weights, k=1)[0]
    return chosen


def main() -> None:
    bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
    topic: str = os.getenv("KAFKA_TOPIC", "source.order_events.live")
    tick_interval_seconds: float = float(os.getenv("TICK_INTERVAL_SECONDS", "3"))
    new_orders_per_tick: int = int(os.getenv("NEW_ORDERS_PER_TICK", "2"))

    producer: KafkaProducer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
    )

    active_orders: list[ActiveOrder] = []

    try:
        while True:
            now: datetime = datetime.now(tz=UTC)
            messages_sent: int = 0

            for _ in range(new_orders_per_tick):
                order: ActiveOrder = create_new_order(event_at=now)
                message: dict[str, str | None] = build_message(order=order, event_at=now)
                producer.send(
                    topic,
                    key=order.order_id.encode("utf-8"),
                    value=message,
                )
                active_orders.append(order)
                messages_sent += 1

            still_active: list[ActiveOrder] = []
            for order in active_orders:
                order.ticks_until_next -= 1
                if order.ticks_until_next > 0:
                    still_active.append(order)
                    continue

                next_status: str | None = advance_order(order)
                if next_status is None:
                    continue

                order.status = next_status
                message = build_message(order=order, event_at=now)
                producer.send(
                    topic,
                    key=order.order_id.encode("utf-8"),
                    value=message,
                )
                messages_sent += 1

                if order.status in TERMINAL_STATUSES:
                    pass
                else:
                    order.ticks_until_next = random.randint(2, 6)
                    still_active.append(order)

            active_orders = still_active
            producer.flush()
            print(
                f"tick: sent {messages_sent} events, "
                f"{len(active_orders)} active orders "
                f"at {now.isoformat(timespec='milliseconds')}"
            )
            time.sleep(tick_interval_seconds)
    finally:
        producer.close()


if __name__ == "__main__":
    main()
