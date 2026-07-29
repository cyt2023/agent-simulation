from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Protocol

from .transcript import TranscriptSegment


class LanguageModel(Protocol):
    async def complete(self, *, system_prompt: str, input_text: str) -> str: ...


class NeutralityError(ValueError):
    pass


@dataclass(frozen=True)
class SummaryResult:
    content: str
    prompt_version: str


NEUTRAL_SUMMARY_PROMPT = """You create a factual meeting record from the supplied transcript only.
Return exactly one JSON object with five arrays:
{"sections":{"discussion_overview":[],"information_and_reasons":[],"positions_and_disagreements":[],
"tentative_outcome_and_status":[],"open_questions_and_next_steps":[]}}.
Every array item is shaped as {"text":"...","segment_ids":["..."]}.
Each item must stay factual and closely grounded in its cited final transcript segments. Do not put
speaker labels in text because the server adds attribution. Cite every claim with one or more
supplied segment_ids. Do not recommend, rank, persuade, address the reader, infer motives, declare
a final decision, or introduce facts absent from the cited segments. When speakers use normative
language, report it descriptively as a proposal, concern, or disagreement without repeating words
such as should, must, best, or final. Omit a claim when evidence is incomplete."""

SUMMARY_SECTIONS = (
    ("discussion_overview", "1. Discussion overview"),
    ("information_and_reasons", "2. Information and reasons"),
    ("positions_and_disagreements", "3. Positions and disagreements"),
    ("tentative_outcome_and_status", "4. Tentative outcome and status"),
    ("open_questions_and_next_steps", "5. Open questions and next steps"),
)

_PROHIBITED_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:you|we|the\s+team|participants?|t1|t2|p)\s+(?:should|must|ought\s+to|need\s+to)\b",
        r"\b(?:should|must|ought\s+to|need\s+to)\s+(?:choose|select|adopt|use|go\s+with|decide|vote|support)\b",
        r"\b(?:we\s+)?recommend(?:ed|ation)?\b",
        r"\b(?:advise|advises|advised|persuade|persuades|persuaded|convince|convinces|convinced)\b",
        r"\b(?:best|better|preferable|advisable|optimal)\b",
        r"\b(?:clearly|definitely|obviously)\s+(?:choose|select|prefer)\b",
        r"\b(?:choose|select|go\s+with|adopt)\b",
        r"\bfinal\s+(?:decision|choice|answer)\b",
        r"\b(?:overall|therefore|thus|in\s+conclusion|on\s+balance)\b.*\b(?:decision|choice|answer|choose|select|adopt|go\s+with)\b",
        "\u4f60\u5e94\u8be5",
        "\u4f60\u5fc5\u987b",
        "\u5efa\u8bae(?:\u9009\u62e9)?",
        "\u8bf4\u670d",
        "\u6700\u4f73\u9009\u62e9",
        "\u66f4\u597d\u7684?\u9009\u62e9",
        "\u6700\u7ec8(?:\u51b3\u5b9a|\u9009\u62e9|\u7b54\u6848)",
        "(?:\u5e94\u8be5|\u5e94\u5f53|\u5fc5\u987b|\u9700\u8981)\\s*(?:\u9009\u62e9|\u91c7\u7eb3|\u91c7\u7528|\u51b3\u5b9a|\u652f\u6301)",
        "(?:\u7efc\u5408\u6765\u770b|\u56e0\u6b64|\u6240\u4ee5|\u7ed3\u8bba\u662f).*(?:\u9009\u62e9|\u91c7\u7eb3|\u91c7\u7528|\u51b3\u5b9a|\u7b54\u6848)",
    )
)

_GROUNDING_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "said",
    "stated",
    "that",
    "the",
    "to",
    "was",
    "were",
    "with",
}


def _grounding_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", value.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            terms.update(token[index : index + 2] for index in range(len(token) - 1))
        elif len(token) > 1 and token not in _GROUNDING_STOPWORDS:
            terms.add(token)
    return terms


def _speaker_label(speaker: str) -> str:
    return {
        "principal": "P",
        "teammate_1": "T1",
        "teammate_2": "T2",
        "proxy": "X",
    }.get(speaker, speaker)


def validate_neutral_language(text: str, *, surface: str) -> None:
    violation = next(
        (pattern.pattern for pattern in _PROHIBITED_PATTERNS if pattern.search(text)),
        None,
    )
    if violation:
        raise NeutralityError(
            f"{surface} failed neutral-language validation: {violation}"
        )


class SummaryService:
    def __init__(self, llm: LanguageModel, *, prompt_version: str):
        self.llm = llm
        self.prompt_version = prompt_version

    async def generate(self, segments: list[TranscriptSegment]) -> SummaryResult:
        final_segments = [segment for segment in segments if segment.is_final]
        if not final_segments:
            return SummaryResult(
                content="\n\n".join(
                    f"## {label}\nNo transcript-supported content."
                    for _, label in SUMMARY_SECTIONS
                ),
                prompt_version=self.prompt_version,
            )
        transcript_payload = [
            {
                "segment_id": segment.segment_id,
                "speaker": segment.speaker,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "text": segment.text,
            }
            for segment in final_segments
        ]
        input_text = json.dumps(transcript_payload, ensure_ascii=False, sort_keys=True)
        last_error: NeutralityError | None = None
        for _attempt in range(2):
            raw = (
                await self.llm.complete(
                    system_prompt=NEUTRAL_SUMMARY_PROMPT,
                    input_text=input_text,
                )
            ).strip()
            try:
                content = self._validate_and_render(raw, final_segments)
                return SummaryResult(
                    content=content, prompt_version=self.prompt_version
                )
            except NeutralityError as error:
                last_error = error
        assert last_error is not None
        raise last_error

    @staticmethod
    def _validate_and_render(
        raw: str, segments: list[TranscriptSegment]
    ) -> str:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as error:
            raise NeutralityError("Summary is not valid JSON") from error
        if not isinstance(payload, dict):
            raise NeutralityError("Summary JSON must be an object")
        sections = payload.get("sections")
        if sections is None and isinstance(payload.get("items"), list):
            # Compatibility for older providers; rendering is still the locked five-section form.
            sections = {"discussion_overview": payload["items"]}
        if not isinstance(sections, dict):
            raise NeutralityError("Summary JSON must contain a sections object")
        by_id = {segment.segment_id: segment for segment in segments}
        rendered_sections: list[str] = []
        for key, label in SUMMARY_SECTIONS:
            items = sections.get(key) or []
            if not isinstance(items, list):
                raise NeutralityError(f"Summary section {key} must be a list")
            rendered: list[str] = []
            for item in items:
                if not isinstance(item, dict):
                    raise NeutralityError("Summary item must be an object")
                text = str(item.get("text") or "").strip()
                segment_ids = item.get("segment_ids")
                if not text or not isinstance(segment_ids, list) or not segment_ids:
                    raise NeutralityError("Summary item requires text and segment_ids")
                validate_neutral_language(text, surface="Summary")
                unknown = [segment_id for segment_id in segment_ids if segment_id not in by_id]
                if unknown:
                    raise NeutralityError(
                        f"Summary cites unknown transcript segment: {unknown[0]}"
                    )
                evidence = " ".join(by_id[segment_id].text for segment_id in segment_ids)
                terms = _grounding_terms(text)
                evidence_terms = _grounding_terms(evidence)
                if terms and len(terms & evidence_terms) / len(terms) < 0.6:
                    raise NeutralityError(
                        "Summary contains facts not grounded in its cited transcript segments"
                    )
                speakers = "/".join(
                    sorted({_speaker_label(by_id[segment_id].speaker) for segment_id in segment_ids})
                )
                citations = ",".join(f"segment:{segment_id}" for segment_id in segment_ids)
                rendered.append(f"- {speakers} stated: {text} [{citations}]")
            body = "\n".join(rendered) or "No transcript-supported content."
            rendered_sections.append(f"## {label}\n{body}")
        return "\n\n".join(rendered_sections)
