from __future__ import annotations

import json
from typing import Any, Mapping


def build_authorized_context_snapshot(
    authorized_context: Mapping[str, Any],
    *,
    context_event_ids: list[str],
    current_utterance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    materials = [
        {
            "material_id": str(item.get("material_id") or ""),
            "title": str(item.get("title") or ""),
            "content": str(item.get("content") or ""),
        }
        for item in authorized_context.get("materials") or []
        if isinstance(item, Mapping)
    ]
    proxy_config = dict(authorized_context.get("proxy_config") or {})
    payload = {
        "proxy_config": proxy_config,
        "materials": materials,
        "current_utterance": dict(current_utterance or {}),
    }
    return {
        "context_event_ids": list(context_event_ids),
        "authorized_context": payload,
        "input_text": json.dumps(payload, ensure_ascii=False, sort_keys=True),
    }
