from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"replacement target not found: {label}")
    return text.replace(old, new, 1)


source_path = Path("src/mca/saed_bir_metadata_resolution.py")
source = source_path.read_text(encoding="utf-8")
old_gates = '''    gates = {
        "respondent_authority_confirmed": respondent_norm["authority_confirmed"],
        "representation_eligible": (
            classification in {"raw_detector", "lossless_export"}
            and representation_norm["released_files_are_original_acquisition_outputs"]
            and representation_norm["original_detector_intensity_available"]
        ),
        "integration_and_binning_documented": (
            representation_norm["native_frame_integration_count"] == 30
            and representation_norm["spatial_binning_documented"]
            and {"native_frame_integration", "spatial_binning"}.issubset(
                set(representation_norm["additional_operations"])
            )
        ),
        "instrument_geometry_documented": bool(
            instrument_norm["detector_pixel_geometry"]
            and instrument_norm["coordinate_convention"]
        ),
        "minimum_two_series": len(series) >= 2,
        "series_ids_unique": len(series_ids) == len(set(series_ids)),
        "member_paths_unique": len(paths) == len(set(paths)),
        "member_hashes_unique": len(hashes) == len(set(hashes)),
        "minimum_two_source_assigned_samples": (
            len(set(samples)) >= 2
            and independence_norm["sample_ids_are_source_assigned"]
        ),
        "minimum_two_source_assigned_acquisitions": (
            len(set(acquisitions)) >= 2
            and independence_norm["acquisition_ids_are_source_assigned"]
            and independence_norm["series_are_independent_acquisitions"]
        ),
        "all_series_independence_flags_true": all(
            item["independent_sample"] and item["independent_acquisition"]
            for item in series
        ),
        "all_member_checksums_declared": all(item["member_sha256"] != "0" * 64 for item in series),
        "all_centres_traceable": all(item["center"]["method"] != "unresolved" for item in series),
        "all_reciprocal_calibrations_traceable": all(
            item["calibration"]["method"] != "unresolved" for item in series
        ),
        "analyzer_nonuse_attested": all(
            value is False
            for key, value in nonuse_norm.items()
            if key != "attestation"
        ),
    }
'''
new_gates = '''    gates = {
        "respondent_authority_confirmed": (
            respondent_norm["authority_confirmed"]
            and all(
                _is_resolved_text(respondent_norm[key])
                for key in ("name", "role", "affiliation", "contact")
            )
        ),
        "representation_eligible": (
            classification in {"raw_detector", "lossless_export"}
            and representation_norm["released_files_are_original_acquisition_outputs"]
            and representation_norm["original_detector_intensity_available"]
            and _is_resolved_text(representation_norm["classification_basis"])
        ),
        "integration_and_binning_documented": (
            representation_norm["native_frame_integration_count"] == 30
            and representation_norm["spatial_binning_documented"]
            and _is_resolved_text(
                representation_norm["spatial_binning_description"]
            )
            and {"native_frame_integration", "spatial_binning"}.issubset(
                set(representation_norm["additional_operations"])
            )
        ),
        "instrument_geometry_documented": all(
            _is_resolved_text(instrument_norm[key])
            for key in ("detector_pixel_geometry", "coordinate_convention")
        ),
        "minimum_two_series": len(series) >= 2,
        "series_ids_unique": (
            len(series_ids) == len(set(series_ids))
            and all(_is_resolved_identifier(value) for value in series_ids)
        ),
        "member_paths_unique": (
            len(paths) == len(set(paths))
            and all(_is_resolved_text(value) for value in paths)
        ),
        "member_hashes_unique": len(hashes) == len(set(hashes)),
        "minimum_two_source_assigned_samples": (
            len(set(samples)) >= 2
            and all(_is_resolved_identifier(value) for value in samples)
            and independence_norm["sample_ids_are_source_assigned"]
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "minimum_two_source_assigned_acquisitions": (
            len(set(acquisitions)) >= 2
            and all(_is_resolved_identifier(value) for value in acquisitions)
            and independence_norm["acquisition_ids_are_source_assigned"]
            and independence_norm["series_are_independent_acquisitions"]
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "all_series_independence_flags_true": (
            all(
                item["independent_sample"] and item["independent_acquisition"]
                for item in series
            )
            and _is_resolved_text(independence_norm["attestation"])
        ),
        "all_member_checksums_declared": all(
            item["member_sha256"] != "0" * 64 for item in series
        ),
        "all_series_dtype_documented": all(
            _is_resolved_text(item["dtype"]) for item in series
        ),
        "all_centres_traceable": all(
            item["center"]["method"] != "unresolved"
            and _is_resolved_text(item["center"]["source"])
            for item in series
        ),
        "all_reciprocal_calibrations_traceable": all(
            item["calibration"]["method"] != "unresolved"
            and _is_resolved_text(item["calibration"]["source"])
            for item in series
        ),
        "analyzer_nonuse_attested": (
            all(
                value is False
                for key, value in nonuse_norm.items()
                if key != "attestation"
            )
            and _is_resolved_text(nonuse_norm["attestation"])
        ),
    }
'''
source = replace_once(source, old_gates, new_gates, "readiness gates")
helper_anchor = '''def build_parser() -> argparse.ArgumentParser:
'''
helpers = '''_UNRESOLVED_TEXT = {
    "n/a",
    "not available",
    "not provided",
    "tbd",
    "todo",
    "unknown",
    "unresolved",
}
_PLACEHOLDER_PREFIXES = (
    "replace-",
    "replace/",
    "replace_",
    "replace with",
    "replace-with",
)


def _is_resolved_text(value: str) -> bool:
    normalized = " ".join(value.strip().casefold().split())
    return bool(normalized) and normalized not in _UNRESOLVED_TEXT and not normalized.startswith(
        _PLACEHOLDER_PREFIXES
    )


def _is_resolved_identifier(value: str) -> bool:
    return _is_resolved_text(value)


'''
source = replace_once(source, helper_anchor, helpers + helper_anchor, "resolved-text helpers")
source_path.write_text(source, encoding="utf-8")


test_path = Path("tests/test_saed_bir_metadata_resolution.py")
tests = test_path.read_text(encoding="utf-8")
anchor = '''def test_identity_mismatch_rejected(tmp_path: Path) -> None:
'''
new_test = '''def test_placeholder_text_cannot_satisfy_readiness(tmp_path: Path) -> None:
    bundle, payload, _ = _template(tmp_path)
    payload = _positive(payload)
    payload["respondent"]["name"] = "replace-with-name"
    payload["representation"]["classification_basis"] = "unresolved"
    payload["instrument"]["coordinate_convention"] = "replace-with-convention"
    payload["series"][0]["sample_id"] = "replace-sample-001"
    payload["series"][0]["member_path"] = "replace/member-001.mrc"
    payload["series"][0]["dtype"] = "replace-with-file-dtype"
    payload["series"][0]["center"]["source"] = "unresolved"
    payload["series"][0]["calibration"]["source"] = "replace-with-calibration"
    payload["independence_attestation"]["attestation"] = "unresolved"
    payload["analyzer_nonuse_attestation"]["attestation"] = "replace-with-attestation"
    response = tmp_path / "response.json"
    _write_json(response, payload)
    result = assess_author_response(bundle, response, tmp_path / "assessment")
    assert result["status"] == RESPONSE_BLOCKED
    for gate in (
        "respondent_authority_confirmed",
        "representation_eligible",
        "instrument_geometry_documented",
        "member_paths_unique",
        "minimum_two_source_assigned_samples",
        "all_series_dtype_documented",
        "all_centres_traceable",
        "all_reciprocal_calibrations_traceable",
        "analyzer_nonuse_attested",
    ):
        assert not result["evidence_gates"][gate]


'''
tests = replace_once(tests, anchor, new_test + anchor, "placeholder regression")
test_path.write_text(tests, encoding="utf-8")
