

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from app.schemas.models import AlertDispatchRequest, AlertDispatchResponse, AlertChannel

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger = logging.getLogger("alerts")

DISPATCH_LOG: list[dict] = []


@router.post("/dispatch", response_model=AlertDispatchResponse)
async def dispatch_alert(req: AlertDispatchRequest):
    now = datetime.now(timezone.utc).isoformat()

    if req.channel == AlertChannel.webhook and req.recipient:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(req.recipient, json=req.advisory.model_dump())
            detail = f"Webhook POSTed to {req.recipient}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Webhook dispatch failed: %s", exc)
            detail = f"Webhook dispatch failed (mocked success for demo): {exc}"
    else:
        detail = f"[MOCK] {req.channel.value} alert logged for {req.recipient or 'no recipient specified'}"
        logger.info(detail)

    entry = {
        "region_id": req.region_id,
        "cyclone_id": req.cyclone_id,
        "channel": req.channel.value,
        "logged_at": now,
        "detail": detail,
    }
    DISPATCH_LOG.append(entry)

    return AlertDispatchResponse(
        dispatched=True,
        channel=req.channel,
        logged_at=now,
        detail=detail,
    )


@router.get("/log")
def get_dispatch_log():
    """Recent dispatched alerts -- useful for a demo 'alerts sent' panel."""
    return {"alerts": DISPATCH_LOG[-50:]}
