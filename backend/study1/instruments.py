"""Versioned, ordered Study 1 instrument catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


class InstrumentValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


CATALOG_PATH = Path(__file__).with_name("instrument_definitions") / "study1-v2.json"


def load_instrument_catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(value["instruments"], sort_keys=True, separators=(",", ":"))
    value["checksum"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return value


def instrument_for(catalog: Mapping[str, Any], phase: str, role: str) -> dict[str, Any] | None:
    for instrument in catalog.get("instruments") or []:
        if instrument.get("phase") == phase and role in (instrument.get("applicable_roles") or []):
            return dict(instrument)
    return None


def validate_ordered_responses(
    instrument: Mapping[str, Any], responses: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    items = list(instrument.get("items") or [])
    expected = [item["item_id"] for item in items]
    actual = [str(item.get("item_id") or "") for item in responses]
    if actual != expected:
        raise InstrumentValidationError(
            "INVALID_INSTRUMENT_ORDER", "Responses must use the exact server-defined item order"
        )
    normalized: list[dict[str, Any]] = []
    for definition, answer in zip(items, responses, strict=True):
        value = answer.get("response")
        if definition.get("required", True) and (value is None or value == ""):
            raise InstrumentValidationError("INSTRUMENT_ITEM_REQUIRED", f"{definition['item_id']} is required")
        response_type = definition.get("response_type")
        constraints = definition.get("constraints") or {}
        if response_type == "integer" and value is not None:
            if isinstance(value, bool):
                raise InstrumentValidationError("INVALID_INSTRUMENT_RESPONSE", f"{definition['item_id']} must be an integer")
            try:
                value = int(value)
            except (TypeError, ValueError) as error:
                raise InstrumentValidationError("INVALID_INSTRUMENT_RESPONSE", f"{definition['item_id']} must be an integer") from error
            if value < int(constraints.get("min", value)) or value > int(constraints.get("max", value)):
                raise InstrumentValidationError("INVALID_INSTRUMENT_RESPONSE", f"{definition['item_id']} is out of range")
        elif response_type == "enum" and value not in constraints.get("values", []):
            raise InstrumentValidationError("INVALID_INSTRUMENT_RESPONSE", f"{definition['item_id']} is not an allowed value")
        elif response_type == "text" and value is not None:
            value = str(value).strip()
            if len(value) > int(constraints.get("max_length", 4000)):
                raise InstrumentValidationError("INVALID_INSTRUMENT_RESPONSE", f"{definition['item_id']} is too long")
        normalized.append({"item_id": definition["item_id"], "response": value})
    return normalized
