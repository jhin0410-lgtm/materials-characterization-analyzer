"""Verify the public FINDS SAED source-audit and diagnostic-case artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

EXPECTED_RUN_IDS = {
    "primary",
    "smoothing_5",
    "smoothing_11",
    "center_m2_p0",
    "center_p2_p0",
    "center_p0_m2",
    "center_p0_p2",
}


class VerificationError(AssertionError):
    """Raised when generated evidence violates the pinned case contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _verify_manifest(base: Path, manifest: Mapping[str, Any]) -> None:
    records = manifest.get("artifacts")
    _require(isinstance(records, list), "manifest artifacts must be a list")
    for record in records:
        _require(isinstance(record, Mapping), "manifest artifact must be an object")
        path = base / str(record["path"])
        _require(path.is_file(), f"manifest artifact missing: {path}")
        payload = path.read_bytes()
        _require(len(payload) == record["bytes"], f"artifact byte drift: {path}")
        _require(
            hashlib.sha256(payload).hexdigest() == record["sha256"],
            f"artifact SHA-256 drift: {path}",
        )


def verify(audit_output: Path, result_output: Path) -> dict[str, Any]:
    audit = json.loads((audit_output / "source_audit_summary.json").read_text())
    audit_manifest = json.loads((audit_output / "source_audit_manifest.json").read_text())
    summary = json.loads((result_output / "case_summary.json").read_text())
    manifest = json.loads((result_output / "case_artifact_manifest.json").read_text())
    candidates = pd.read_csv(result_output / "saed_sensitivity_candidates.csv")
    robustness = pd.read_csv(result_output / "saed_candidate_robustness.csv")
    unmatched = pd.read_csv(result_output / "saed_unmatched_sensitivity_candidates.csv")
    references = pd.read_csv(result_output / "source_d_value_comparison.csv")

    _require(audit["case_id"] == "public_finds_saed_source_audit", "audit case_id")
    source_audit = audit["source"]
    _require(source_audit["record_id"] == 13748483, "audit record_id")
    _require(source_audit["doi"] == "10.5281/zenodo.13748483", "audit DOI")
    _require(source_audit["license"] == "gpl-3.0-or-later", "audit licence")
    _require(source_audit["archive"]["bytes"] == 425297, "archive bytes")
    _require(
        source_audit["archive"]["downloaded_sha256"]
        == "3bd91d96469dbedd9f780292fc248fa6ce94e391f63d6d7a12c4e75738d1a7d6",
        "archive SHA-256",
    )
    gates = audit["readiness"]
    _require(gates["archive_checksum_verified"], "archive checksum gate")
    _require(gates["project_camera_constant_resolved"], "camera constant gate")
    _require(gates["project_center_resolved"], "center gate")
    _require(not gates["source_images_persisted"], "source bytes persisted")
    _require(not gates["saed_analyzer_executed"], "source audit ran analyzer")
    _require(not gates["material_identity_resolved"], "invented material identity")
    _require(
        not gates["phase_or_zone_axis_assignment_performed"],
        "source audit assigned crystallography",
    )
    counts = audit["result_counts"]
    _require(counts["archive_member_count"] == 7, "archive member count")
    _require(counts["platform_metadata_member_count"] == 3, "platform metadata count")
    _require(counts["image_member_count"] == 1, "measurement image count")
    _require(counts["project_candidate_count"] == 1, "valid project count")
    _require(counts["resolved_project_image_count"] == 1, "resolved project image count")
    _require(counts["analyzable_project_image_count"] == 1, "analyzable image count")
    _require(audit_manifest["artifact_count"] == 3, "audit artifact count")

    _require(summary["case_id"] == "public_finds_saed_diagnostic_case", "case_id")
    readiness = summary["readiness"]
    _require(
        readiness["status"] == "diagnostic_calibrated_saed_case_completed",
        "case status",
    )
    for key in (
        "archive_and_member_checksums_verified",
        "project_center_and_camera_constant_verified",
        "decoded_jpeg_to_png_pixel_roundtrip_verified",
        "saed_analyzer_executed",
        "center_and_smoothing_sensitivity_completed",
    ):
        _require(readiness[key], f"required readiness gate: {key}")
    for key in (
        "material_identity_resolved",
        "raw_detector_provenance_resolved",
        "phase_reflection_or_zone_axis_assignment_performed",
        "engineering_release_ready",
    ):
        _require(not readiness[key], f"fail-closed readiness gate: {key}")

    source = summary["source"]
    _require(
        source["source_image_representation"] == "lossy_jpeg_rendered_image",
        "source representation",
    )
    _require(not source["source_images_persisted"], "source images persisted")
    project = source["project"]
    _require(project["center_x_px"] == 586.0, "project center x")
    _require(project["center_y_px"] == 575.0, "project center y")
    _require(project["camera_constant_angstrom_pixel"] == 587.5, "camera constant Å·px")
    _require(project["camera_constant_nm_pixel"] == 58.75, "camera constant nm·px")

    adapter = summary["canonical_adapter"]
    _require(adapter["decoded_shape"] == [1152, 1170], "decoded shape")
    _require(adapter["decoded_dtype"] == "uint8", "decoded dtype")
    _require(adapter["png_roundtrip_pixel_equal"], "PNG pixel roundtrip")
    for key in (
        "normalization_applied",
        "contrast_adjustment_applied",
        "cropping_applied",
        "resizing_applied",
        "denoising_applied",
    ):
        _require(not adapter[key], f"unexpected adapter operation: {key}")

    runs = summary["analysis_runs"]
    _require(len(runs) == 7, "analysis run count")
    _require({record["run_id"] for record in runs} == EXPECTED_RUN_IDS, "run IDs")
    for record in runs:
        analysis_manifest = json.loads(
            (result_output / record["analysis_manifest"]).read_text()
        )
        analysis = analysis_manifest["analyses"][0]
        _require(analysis["instrument"] == "saed", "analysis instrument")
        _require(
            analysis["sample_id"] == "finds_saed_example_material_unresolved",
            "analysis sample_id",
        )
        _require(analysis["source_sha256"] == adapter["canonical_sha256"], "source hash")
        _require(
            "automatic_ring_candidates_require_manual_review" in analysis["warnings"],
            "manual-review warning",
        )

    review = summary["candidate_robustness"]
    _require(review["primary_candidate_count"] == len(robustness), "primary robustness count")
    _require(review["all_runs_matched_count"] <= review["primary_candidate_count"], "matched count")
    _require(
        review["unmatched_sensitivity_candidate_count"] == len(unmatched),
        "unmatched sensitivity count",
    )
    _require(not review["raw_analyzer_candidate_tables_modified"], "candidate table modified")
    _require(not review["candidate_acceptance_or_rejection_performed"], "candidate accepted")
    _require(
        summary["source_d_value_context"]["used_for_detection_tuning"] is False,
        "source d-values used for tuning",
    )
    _require(
        summary["source_d_value_context"]["used_for_phase_or_material_assignment"] is False,
        "source d-values used for assignment",
    )
    _require(len(references) == 4, "source d-value count")
    _require(not references["reference_used_for_detection_tuning"].any(), "reference tuning flag")
    _require(not references["material_or_phase_identity_assigned"].any(), "reference assignment flag")
    _require(set(candidates["run_id"]) == EXPECTED_RUN_IDS, "candidate run IDs")

    _verify_manifest(audit_output, audit_manifest)
    _verify_manifest(result_output, manifest)

    primary = candidates[candidates["run_id"] == "primary"]
    return {
        "status": readiness["status"],
        "source_counts": counts,
        "primary_candidate_count": int(len(primary)),
        "primary_candidate_radii_px": [round(value, 5) for value in primary["radius_px"].tolist()],
        "primary_candidate_d_nm": [round(value, 7) for value in primary["d_spacing_nm"].tolist()],
        "candidate_counts": {
            run_id: int(len(group))
            for run_id, group in candidates.groupby("run_id", sort=True)
        },
        "analysis_warnings": {
            record["run_id"]: record["warnings"] for record in runs
        },
        "all_runs_matched_count": review["all_runs_matched_count"],
        "unmatched_sensitivity_candidate_count": review[
            "unmatched_sensitivity_candidate_count"
        ],
        "source_reference_comparison": references.to_dict(orient="records"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args(argv)
    result = verify(args.audit, args.result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
