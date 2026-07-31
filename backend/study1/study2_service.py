"""Permission-filtered projections for Study 2's read-only contract."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .permissions import study2_data_available
from .services import Study1Service, Study1ServiceError
from .study2_contracts import (
    PAGINATED_RESOURCES,
    STUDY2_CONTRACT_VERSION,
    STUDY2_MODULE_TELEMETRY_ALLOWLIST,
    STUDY2_MODULE_TELEMETRY_FIELDS,
    STUDY2_RESOURCES,
    Study2ContractError,
    paginate,
)


class Study2ReadOnlyService:
    """Expose projections only; it never mutates the Study 1 repository."""

    def __init__(self, study1_service: Study1Service):
        self.study1_service = study1_service

    def read_resource(
        self,
        session_id: str,
        identity: Mapping[str, Any],
        resource: str,
        *,
        cursor: str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        if resource not in STUDY2_RESOURCES:
            raise Study1ServiceError(
                "INVALID_STUDY2_RESOURCE", "Unknown Study 2 contract resource", 404
            )
        method_name = resource.replace("-", "_")
        method = getattr(self, method_name)
        try:
            if resource in PAGINATED_RESOURCES:
                return method(session_id, identity, cursor=cursor, limit=limit)
            return method(session_id, identity)
        except Study2ContractError as error:
            raise Study1ServiceError(error.code, str(error), 400) from error

    def utterances(
        self,
        session_id: str,
        identity: Mapping[str, Any],
        *,
        cursor: str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "utterances")
        utterances: list[dict[str, Any]] = []
        for artifact in data.get("artifacts") or []:
            if artifact.get("type") != "transcript":
                continue
            for index, segment in enumerate(_transcript_segments(artifact), start=1):
                utterance_id = str(
                    segment.get("utterance_id")
                    or segment.get("segment_id")
                    or segment.get("id")
                    or f"{artifact.get('artifact_id', 'transcript')}:{index}"
                )
                item = {
                    "utterance_id": utterance_id,
                    "speaker": str(segment.get("speaker") or "unknown"),
                    "text": str(segment.get("text") or ""),
                }
                for field in ("start_ms", "end_ms", "started_at_ms", "ended_at_ms"):
                    if field in segment:
                        item[field] = segment[field]
                utterances.append(item)
        return paginate(utterances, cursor, limit)

    def decisions(
        self,
        session_id: str,
        identity: Mapping[str, Any],
        *,
        cursor: str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "decisions")
        role = _identity_value(identity, "role")
        participant_id = _identity_value(identity, "participant_id")
        values: list[dict[str, Any]] = []
        for decision in data.get("decisions") or []:
            if role != "researcher" and decision.get("decision_kind") != "team_final":
                if decision.get("participant_id") != participant_id:
                    continue
            values.append(_decision_projection(decision))
        return paginate(values, cursor, limit)

    def facts(
        self,
        session_id: str,
        identity: Mapping[str, Any],
        *,
        cursor: str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "facts")
        role = _identity_value(identity, "role")
        facts: dict[str, dict[str, Any]] = {}
        for material in data.get("materials") or []:
            metadata = material.get("metadata") or material.get("metadata_payload") or {}
            for fact in metadata.get("facts") or []:
                visible_to_roles = [str(value) for value in fact.get("visible_to_roles") or []]
                if role != "researcher" and role not in visible_to_roles:
                    continue
                fact_id = str(fact.get("fact_id") or "")
                if not fact_id:
                    continue
                facts.setdefault(
                    fact_id,
                    {
                        "fact_id": fact_id,
                        "candidate_id": str(fact.get("candidate_id") or ""),
                        "text": str(fact.get("text") or ""),
                        "valence": fact.get("valence"),
                        "information_type": fact.get("information_type"),
                    },
                )
        return paginate(list(facts.values()), cursor, limit)

    def proxy_authority(
        self, session_id: str, identity: Mapping[str, Any]
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "proxy-authority")
        config = _protocol_config(data)
        authorized_material_ids: list[str] = []
        for submission in data.get("submissions") or []:
            if submission.get("submission_type") != "proxy_config":
                continue
            payload = submission.get("payload") or {}
            authorized_material_ids = [
                str(value) for value in payload.get("authorized_material_ids") or []
            ]
        return {
            "contract_version": STUDY2_CONTRACT_VERSION,
            "authority_level": str(config.get("authority_level") or "share_only"),
            "authorized_material_ids": authorized_material_ids,
        }

    def baseline_recap(
        self, session_id: str, identity: Mapping[str, Any]
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "baseline-recap")
        role = _identity_value(identity, "role")
        participant_id = _identity_value(identity, "participant_id")
        items = [
            _decision_projection(decision)
            for decision in data.get("decisions") or []
            if decision.get("decision_kind") == "pre_individual"
            and (
                role == "researcher"
                or decision.get("participant_id") == participant_id
            )
        ]
        return {
            "contract_version": STUDY2_CONTRACT_VERSION,
            "available": bool(items),
            "items": items,
        }

    def features(
        self, session_id: str, identity: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        data = self._data(session_id)
        if identity is not None:
            self._require_available(data["session"], identity, "features")
        return {
            "contract_version": STUDY2_CONTRACT_VERSION,
            "read_only": True,
            "resync_enabled": False,
        }

    def module_telemetry(
        self,
        session_id: str,
        identity: Mapping[str, Any],
        *,
        cursor: str | None = None,
        limit: int | str | None = None,
    ) -> dict[str, Any]:
        data = self._data(session_id)
        self._require_available(data["session"], identity, "module-telemetry")
        raw_items = data["session"].get("study2_module_telemetry") or []
        values = [
            {
                field: item[field]
                for field in STUDY2_MODULE_TELEMETRY_FIELDS
                if field in item
            }
            for item in raw_items
            if isinstance(item, Mapping)
            and item.get("module_id") in STUDY2_MODULE_TELEMETRY_ALLOWLIST
        ]
        return paginate(values, cursor, limit)

    def _data(self, session_id: str) -> dict[str, Any]:
        return self.study1_service.repository.export_data(session_id)

    @staticmethod
    def _require_available(
        session: Mapping[str, Any], identity: Mapping[str, Any], resource: str
    ) -> None:
        role = _identity_value(identity, "role")
        if role not in {"principal", "teammate_1", "teammate_2", "researcher"}:
            raise Study1ServiceError("FORBIDDEN", "Study 2 read access is not permitted", 403)
        if not study2_data_available(identity, session, resource):
            raise Study1ServiceError(
                "STUDY2_DATA_NOT_AVAILABLE",
                "Study 2 data is unavailable while the principal is isolated",
                403,
            )


# Short alias for callers that do not need the implementation qualifier.
Study2Service = Study2ReadOnlyService


def _identity_value(identity: Mapping[str, Any], name: str) -> str:
    value = identity.get(name)
    return getattr(value, "value", value) or ""


def _transcript_segments(artifact: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    content = artifact.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError:
            return []
    if isinstance(content, list):
        return [item for item in content if isinstance(item, Mapping)]
    if isinstance(content, Mapping):
        segments = content.get("segments") or content.get("utterances") or []
        return [item for item in segments if isinstance(item, Mapping)]
    return []


def _decision_projection(decision: Mapping[str, Any]) -> dict[str, Any]:
    result = {
        "decision_id": str(decision.get("decision_id") or ""),
        "decision_kind": str(decision.get("decision_kind") or ""),
        "candidate_id": decision.get("candidate_id"),
        "rationale": decision.get("rationale"),
        "confidence": decision.get("confidence"),
        "decision_status": decision.get("decision_status"),
        "locked": bool(decision.get("locked", False)),
    }
    return {key: value for key, value in result.items() if value is not None}


def _protocol_config(data: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = data.get("protocol_snapshot") or {}
    return (
        snapshot.get("canonical_config")
        or (data.get("session") or {}).get("experiment_config")
        or {}
    )
