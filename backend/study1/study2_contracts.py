"""Stable value helpers for the versioned Study 2 read-only boundary."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Iterable, Mapping


STUDY2_CONTRACT_VERSION = "study2-readonly-contract-v1"
STUDY2_API_PREFIX = "/api/study2/v1"
STUDY2_RESOURCES = frozenset(
    {
        "utterances",
        "decisions",
        "facts",
        "proxy-authority",
        "baseline-recap",
        "features",
        "module-telemetry",
    }
)
PAGINATED_RESOURCES = frozenset(
    {"utterances", "decisions", "facts", "module-telemetry"}
)
STUDY2_MODULE_TELEMETRY_ALLOWLIST = frozenset({"study2.readonly"})
STUDY2_MODULE_TELEMETRY_FIELDS = (
    "module_id",
    "event_type",
    "occurred_at",
    "duration_ms",
    "status",
)
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 200


class Study2ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def paginate(
    items: Iterable[Mapping[str, Any]], cursor: str | None, limit: int | str | None
) -> dict[str, Any]:
    """Return a deterministic offset page without exposing the backing store."""

    try:
        start = int(cursor) if cursor else 0
    except (TypeError, ValueError) as error:
        raise Study2ContractError("INVALID_CURSOR", "cursor must be a non-negative offset") from error
    if start < 0:
        raise Study2ContractError("INVALID_CURSOR", "cursor must be a non-negative offset")
    try:
        page_limit = int(limit) if limit is not None else DEFAULT_PAGE_LIMIT
    except (TypeError, ValueError) as error:
        raise Study2ContractError("INVALID_PAGE_LIMIT", "limit must be an integer") from error
    if not 1 <= page_limit <= MAX_PAGE_LIMIT:
        raise Study2ContractError(
            "INVALID_PAGE_LIMIT",
            f"limit must be between 1 and {MAX_PAGE_LIMIT}",
        )

    values = [dict(item) for item in items]
    page = values[start : start + page_limit]
    next_offset = start + len(page)
    return {
        "contract_version": STUDY2_CONTRACT_VERSION,
        "items": page,
        "next_cursor": str(next_offset) if next_offset < len(values) else None,
    }


def contract_etag(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_value,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_value(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
