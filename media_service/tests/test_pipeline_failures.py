from __future__ import annotations


def test_context_builder_uses_only_authorized_materials():
    from media_service.app.context_builder import build_authorized_context_snapshot

    snapshot = build_authorized_context_snapshot(
        {
            "materials": [
                {"material_id": "p-1", "title": "P", "content": "P authorized"},
            ],
            "unshared_materials": [
                {"material_id": "t1-1", "title": "T1", "content": "Do not leak"},
            ],
            "proxy_config": {"authority_level": "share_only"},
        },
        context_event_ids=["u1"],
    )

    assert "P authorized" in snapshot["input_text"]
    assert "Do not leak" not in snapshot["input_text"]
    assert snapshot["context_event_ids"] == ["u1"]
