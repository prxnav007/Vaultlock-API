"""A one-page demonstration UI for the churn-risk endpoint.

Deliberately plain, and deliberately thin: it calls the same public endpoints a
client would, so what it shows is exactly what the API returns. It is report
evidence and a demo surface, not a product.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["dashboard"])

DASHBOARD = Path(__file__).resolve().parents[2] / "static" / "dashboard.html"


@router.get("/dashboard", response_class=FileResponse, include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD, media_type="text/html")
