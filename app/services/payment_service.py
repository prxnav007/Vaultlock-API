"""Payment reads.

Write paths -- and the idempotency semantics that guard them -- are a later
milestone. This module exists so a payment's final state can be verified
through the API.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    return result.scalar_one_or_none()
