
import os
import json
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

from app.schemas.models import AdvisoryResponse, SeverityLevel

logger = logging.getLogger("gemini_service")

load_dotenv()  
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {
            "type": "string",
            "enum": ["low", "moderate", "high", "severe"],
        },
        "affected_areas": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_actions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "advisory_text": {
            "type": "string",
            "description": "The full human-readable advisory, in the requested language.",
        },
    },
    "required": ["severity", "affected_areas", "recommended_actions", "advisory_text"],
}


def _build_prompt(
    region_id: str,
    cyclone_id: str,
    language: str,
    surge_height_m: Optional[float],
    flood_extent_km2: Optional[float],
    exposure_score: Optional[float],
    bulletin_text: Optional[str],
) -> str:
    """
    Builds the text portion of the prompt. Numbers are explicitly labeled
    so the model treats them as ground truth to reason from, not as
    decoration.
    """
    lines = [
        "You are generating an official-style cyclone advisory for a disaster "
        "response dashboard. Base your severity rating and advisory text "
        "STRICTLY on the numeric data and bulletin text provided below. "
        "Do not invent figures. If a figure is missing, say the affected "
        "area's exposure is uncertain rather than guessing a number.",
        "",
        f"Region: {region_id}",
        f"Cyclone: {cyclone_id}",
        f"Target language for advisory_text: {language} "
        "(write the advisory_text field itself in this language; "
        "severity/affected_areas/recommended_actions can stay in English "
        "as structured labels).",
        "",
        "--- Model outputs ---",
    ]
    if surge_height_m is not None:
        lines.append(f"Max storm surge height: {surge_height_m} meters")
    if flood_extent_km2 is not None:
        lines.append(f"Estimated flood extent: {flood_extent_km2} sq km")
    if exposure_score is not None:
        lines.append(f"Infrastructure exposure score (0-1 scale): {exposure_score}")
    if bulletin_text:
        lines.append("")
        lines.append("--- Meteorological bulletin excerpt ---")
        lines.append(bulletin_text)

    lines.append("")
    lines.append(
        "Return ONLY the structured fields requested: severity, "
        "affected_areas, recommended_actions, advisory_text."
    )
    return "\n".join(lines)


async def generate_advisory(
    region_id: str,
    cyclone_id: str,
    language: str = "en",
    surge_height_m: Optional[float] = None,
    flood_extent_km2: Optional[float] = None,
    exposure_score: Optional[float] = None,
    bulletin_text: Optional[str] = None,
    satellite_image_bytes: Optional[bytes] = None,
    satellite_image_mime: str = "image/jpeg",
) -> AdvisoryResponse:
    now = datetime.now(timezone.utc).isoformat()

    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set -- returning fallback advisory.")
        return _fallback_advisory(region_id, cyclone_id, language, now)

    prompt_text = _build_prompt(
        region_id, cyclone_id, language,
        surge_height_m, flood_extent_km2, exposure_score, bulletin_text,
    )

    parts = [{"text": prompt_text}]
    if satellite_image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": satellite_image_mime,
                "data": base64.b64encode(satellite_image_bytes).decode("utf-8"),
            }
        })

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GEMINI_ENDPOINT,
                headers={"x-goog-api-key": GEMINI_API_KEY},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)

        return AdvisoryResponse(
            region_id=region_id,
            cyclone_id=cyclone_id,
            language=language,
            severity=SeverityLevel(parsed["severity"]),
            affected_areas=parsed["affected_areas"],
            recommended_actions=parsed["recommended_actions"],
            advisory_text=parsed["advisory_text"],
            generated_at=now,
            model_used=GEMINI_MODEL,
            is_fallback=False,
        )

    except Exception as exc:  # noqa: BLE001 -- deliberately broad for demo resilience
        logger.exception("Gemini call failed, returning fallback advisory: %s", exc)
        return _fallback_advisory(region_id, cyclone_id, language, now)


def _fallback_advisory(
    region_id: str, cyclone_id: str, language: str, now: str
) -> AdvisoryResponse:
    """
    Canned advisory shown if Gemini is unreachable, misconfigured, or errors
    out. Keeps the demo alive instead of surfacing a raw failure.
    """
    return AdvisoryResponse(
        region_id=region_id,
        cyclone_id=cyclone_id,
        language=language,
        severity=SeverityLevel.moderate,
        affected_areas=["Data unavailable -- showing fallback advisory"],
        recommended_actions=[
            "Monitor official IMD bulletins directly",
            "Follow local district administration guidance",
        ],
        advisory_text=(
            "Advisory generation is temporarily unavailable. Please refer to "
            "the latest official meteorological bulletin for this region."
        ),
        generated_at=now,
        model_used="fallback",
        is_fallback=True,
    )