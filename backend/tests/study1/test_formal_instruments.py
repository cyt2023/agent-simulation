from __future__ import annotations

import pytest

from study1.instruments import InstrumentValidationError, load_instrument_catalog, validate_ordered_responses


def test_formal_instrument_rejects_wrong_order():
    catalog = load_instrument_catalog()
    instrument = catalog["instruments"][0]
    responses = [
        {"item_id": "confidence", "response": 4},
        {"item_id": "candidate_id", "response": "a"},
        {"item_id": "rationale", "response": "Reason"},
    ]
    with pytest.raises(InstrumentValidationError) as error:
        validate_ordered_responses(instrument, responses)
    assert error.value.code == "INVALID_INSTRUMENT_ORDER"


def test_catalog_contains_only_ordered_versioned_english_items():
    catalog = load_instrument_catalog()
    assert catalog["catalog_version"] == "study1-instruments-v2"
    assert len(catalog["checksum"]) == 64
    for instrument in catalog["instruments"]:
        assert instrument["instrument_version"] == "2.0"
        assert [item["item_id"] for item in instrument["items"]]
