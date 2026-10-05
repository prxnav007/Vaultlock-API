"""The merchant and payment read endpoints.

Read-only against the generated dataset, which is also what makes them useful:
they verify the API returns the same ledger the feature pipeline consumed.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.db.sync_session import sync_engine

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def sample_ids() -> tuple[str, str]:
    """One merchant and one of its payments, from the loaded dataset."""
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT merchant_id::text, payment_id::text FROM payments LIMIT 1"
            )
        ).first()
    if row is None:
        pytest.skip("no generated dataset; run python -m ml.synthetic.generate")
    return row[0], row[1]


@pytest.fixture
async def client():
    from app.main import app

    # The model is irrelevant to these routes, so do not require it.
    original = settings.REQUIRE_MODEL
    settings.REQUIRE_MODEL = False
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            async with app.router.lifespan_context(app):
                yield c
    finally:
        settings.REQUIRE_MODEL = original


async def test_read_merchant(client, sample_ids) -> None:
    merchant_id, _ = sample_ids
    response = await client.get(f"/merchants/{merchant_id}")
    assert response.status_code == 200

    body = response.json()
    assert body["merchant_id"] == merchant_id
    assert set(body) == {"merchant_id", "joined_at", "industry", "created_at"}
    # Derived state must not leak into the merchant resource.
    assert "is_churned" not in body
    assert "last_transaction_at" not in body


async def test_unknown_merchant_is_404(client) -> None:
    response = await client.get(f"/merchants/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_read_payment(client, sample_ids) -> None:
    merchant_id, payment_id = sample_ids
    response = await client.get(f"/payments/{payment_id}")
    assert response.status_code == 200

    body = response.json()
    assert body["payment_id"] == payment_id
    assert body["merchant_id"] == merchant_id
    # Money stays in minor units all the way to the client.
    assert isinstance(body["amount_minor"], int)
    assert body["amount_minor"] > 0
    assert body["currency"] == "INR"
    assert body["status"] in {"PENDING", "SUCCESS", "FAILED"}


async def test_unknown_payment_is_404(client) -> None:
    response = await client.get(f"/payments/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_malformed_uuid_is_422(client) -> None:
    response = await client.get("/merchants/not-a-uuid")
    assert response.status_code == 422
