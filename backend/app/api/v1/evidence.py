"""
AEROWIND API v1 — Evidence Router
======================================
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/evidence", tags=["Evidence"])

@router.get("/")
async def list_evidence() -> list[dict]:
    """Return an empty list for now. Placeholder for future evidence implementation."""
    return []
