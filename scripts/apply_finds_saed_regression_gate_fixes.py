from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} occurrence(s), found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


verifier = Path("scripts/verify_public_finds_saed_case.py")
tests = Path("tests/test_public_finds_saed_case.py")
readme = Path("case_studies/public_finds_saed/README.md")

replace_exact(
    verifier,
    """import argparse\nimport hashlib\nimport json\n""",
    """import argparse\nimport hashlib\nimport json\nimport math\n""",
)
replace_exact(
    verifier,
    """EXPECTED_RUN_IDS = {\n    \"primary\",\n    \"smoothing_5\",\n    \"smoothing_11\",\n    \"center_m2_p0\",\n    \"center_p2_p0\",\n    \"center_p0_m2\",\n    \"center_p0_p2\",\n}\n""",
    """EXPECTED_RUN_IDS = {\n    \"primary\",\n    \"smoothing_5\",\n    \"smoothing_11\",\n    \"center_m2_p0\",\n    \"center_p2_p0\",\n    \"center_p0_m2\",\n    \"center_p0_p2\",\n}\nEXPECTED_PRIMARY_CANDIDATES = (\n    (1, 108.45621, 0.541693),\n    (2, 289.46752, 0.202959),\n    (3, 410.46660, 0.143130),\n    (4, 502.46939, 0.116923),\n)\nEXPECTED_PRIMARY_CANDIDATE_COUNT = len(EXPECTED_PRIMARY_CANDIDATES)\nPRIMARY_RADIUS_ABS_TOLERANCE_PX = 1e-4\nPRIMARY_D_SPACING_ABS_TOLERANCE_NM = 1e-6\n""",
)
replace_exact(
    verifier,
    """def verify(audit_output: Path, result_output: Path) -> dict[str, Any]:\n""",
    """def _verify_pinned_primary_candidates(primary: pd.DataFrame) -> None:\n    _require(\n        len(primary) == EXPECTED_PRIMARY_CANDIDATE_COUNT,\n        \"primary candidate count drift\",\n    )\n    ordered = primary.sort_values(\"radius_px\").reset_index(drop=True)\n    for observed, (ring_id, radius_px, d_spacing_nm) in zip(\n        ordered.to_dict(orient=\"records\"),\n        EXPECTED_PRIMARY_CANDIDATES,\n        strict=True,\n    ):\n        _require(int(observed[\"ring_id\"]) == ring_id, f\"primary ring ID drift: {ring_id}\")\n        _require(\n            math.isclose(\n                float(observed[\"radius_px\"]),\n                radius_px,\n                rel_tol=0.0,\n                abs_tol=PRIMARY_RADIUS_ABS_TOLERANCE_PX,\n            ),\n            f\"primary radius drift for ring {ring_id}\",\n        )\n        _require(\n            math.isclose(\n                float(observed[\"d_spacing_nm\"]),\n                d_spacing_nm,\n                rel_tol=0.0,\n                abs_tol=PRIMARY_D_SPACING_ABS_TOLERANCE_NM,\n            ),\n            f\"primary d-spacing drift for ring {ring_id}\",\n        )\n\n\ndef verify(audit_output: Path, result_output: Path) -> dict[str, Any]:\n""",
)
replace_exact(
    verifier,
    """    review = summary[\"candidate_robustness\"]\n    _require(review[\"primary_candidate_count\"] == len(robustness), \"primary robustness count\")\n    _require(review[\"all_runs_matched_count\"] <= review[\"primary_candidate_count\"], \"matched count\")\n    _require(\n        review[\"unmatched_sensitivity_candidate_count\"] == len(unmatched),\n        \"unmatched sensitivity count\",\n    )\n""",
    """    review = summary[\"candidate_robustness\"]\n    _require(\n        review[\"primary_candidate_count\"] == EXPECTED_PRIMARY_CANDIDATE_COUNT,\n        \"pinned primary robustness count\",\n    )\n    _require(len(robustness) == EXPECTED_PRIMARY_CANDIDATE_COUNT, \"primary robustness rows\")\n    _require(\n        review[\"all_runs_matched_count\"] == EXPECTED_PRIMARY_CANDIDATE_COUNT,\n        \"all-runs matched count drift\",\n    )\n    _require(robustness[\"all_runs_matched\"].all(), \"primary candidate lost sensitivity match\")\n    _require(\n        review[\"unmatched_sensitivity_candidate_count\"] == 0,\n        \"unmatched sensitivity candidate count drift\",\n    )\n    _require(len(unmatched) == 0, \"unmatched sensitivity candidate rows\")\n""",
)
replace_exact(
    verifier,
    """    _require(set(candidates[\"run_id\"]) == EXPECTED_RUN_IDS, \"candidate run IDs\")\n\n    _verify_manifest(audit_output, audit_manifest)\n""",
    """    _require(set(candidates[\"run_id\"]) == EXPECTED_RUN_IDS, \"candidate run IDs\")\n    candidate_counts = candidates.groupby(\"run_id\").size().to_dict()\n    _require(\n        candidate_counts == {run_id: EXPECTED_PRIMARY_CANDIDATE_COUNT for run_id in EXPECTED_RUN_IDS},\n        \"per-run candidate count drift\",\n    )\n    primary = candidates[candidates[\"run_id\"] == \"primary\"]\n    _verify_pinned_primary_candidates(primary)\n\n    _verify_manifest(audit_output, audit_manifest)\n""",
)
replace_exact(
    verifier,
    """    primary = candidates[candidates[\"run_id\"] == \"primary\"]\n    return {\n""",
    """    return {\n""",
)

replace_exact(
    tests,
    """import run_public_finds_saed_case as case  # noqa: E402\n""",
    """import run_public_finds_saed_case as case  # noqa: E402\nimport verify_public_finds_saed_case as verifier  # noqa: E402\n""",
)
append_tests = r'''


def test_verifier_pins_primary_candidate_count_radii_and_d_spacings() -> None:
    primary = pd.DataFrame(
        [
            {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
            for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES
        ]
    )
    verifier._verify_pinned_primary_candidates(primary)


@pytest.mark.parametrize(
    ("column", "delta", "message"),
    [
        ("radius_px", 0.01, "primary radius drift"),
        ("d_spacing_nm", 0.001, "primary d-spacing drift"),
    ],
)
def test_verifier_rejects_primary_candidate_numerical_drift(
    column: str,
    delta: float,
    message: str,
) -> None:
    rows = [
        {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
        for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES
    ]
    rows[0][column] += delta
    with pytest.raises(verifier.VerificationError, match=message):
        verifier._verify_pinned_primary_candidates(pd.DataFrame(rows))


def test_verifier_rejects_missing_primary_candidate() -> None:
    rows = [
        {"ring_id": ring_id, "radius_px": radius_px, "d_spacing_nm": d_spacing_nm}
        for ring_id, radius_px, d_spacing_nm in verifier.EXPECTED_PRIMARY_CANDIDATES[:-1]
    ]
    with pytest.raises(verifier.VerificationError, match="primary candidate count drift"):
        verifier._verify_pinned_primary_candidates(pd.DataFrame(rows))
'''
text = tests.read_text(encoding="utf-8")
if "test_verifier_pins_primary_candidate_count_radii_and_d_spacings" in text:
    raise SystemExit("SAED verifier tests already appended")
tests.write_text(text + append_tests, encoding="utf-8")

replace_exact(
    readme,
    """All four primary candidates matched one-to-one in all six sensitivity runs. No\nunmatched sensitivity candidate remained. This demonstrates parameter-level\nradius stability for this rendered example only; it does not validate the ring\nas a reflection or phase.\n""",
    """All four primary candidates matched one-to-one in all six sensitivity runs. No\nunmatched sensitivity candidate remained. The workflow verifier pins the four\nprimary radii and calibrated d-spacings with explicit absolute tolerances,\nrequires exactly four candidates in every run, and fails if any primary loses a\nsensitivity match or any unmatched candidate appears. This demonstrates\nparameter-level radius stability for this rendered example only; it does not\nvalidate the ring as a reflection or phase.\n""",
)

print("Applied FINDS SAED regression-gate fixes")
