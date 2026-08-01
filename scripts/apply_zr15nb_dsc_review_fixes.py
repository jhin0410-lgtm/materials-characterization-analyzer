from __future__ import annotations

from pathlib import Path


candidate = Path("scripts/review_public_zr15nb_dsc_candidates.py")
source = Path("scripts/audit_public_zr15nb_dsc_source.py")
candidate_tests = Path("tests/test_public_zr15nb_dsc_candidate_review.py")
source_tests = Path("tests/test_public_zr15nb_dsc_source_audit.py")
readme = Path("case_studies/public_zr15nb_dsc/README.md")


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} occurrence(s), found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_between(path: Path, start_marker: str, end_marker: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


replace_exact(
    candidate,
    """import numpy as np\nimport pandas as pd\n""",
    """import numpy as np\nimport pandas as pd\nfrom scipy.optimize import linear_sum_assignment\n""",
)
replace_exact(
    candidate,
    """REQUIRED_RUNS = (\"primary\", \"sensitivity_1c\", \"sensitivity_5c\")\n""",
    """REQUIRED_RUNS = (\"primary\", \"sensitivity_1c\", \"sensitivity_5c\")\nREVIEW_SECTION_START = \"<!-- BEGIN MCA DSC CANDIDATE REVIEW -->\"\nREVIEW_SECTION_END = \"<!-- END MCA DSC CANDIDATE REVIEW -->\"\n""",
)

new_review_function = '''def _optimal_same_direction_assignment(\n    primary: pd.DataFrame,\n    sensitivity: pd.DataFrame,\n    *,\n    tolerance_c: float,\n) -> dict[int, int]:\n    \"\"\"Maximize valid one-to-one matches, then minimize total temperature distance.\"\"\"\n\n    if primary.empty or sensitivity.empty:\n        return {}\n    primary_indices = list(primary.index)\n    sensitivity_indices = list(sensitivity.index)\n    n_primary = len(primary_indices)\n    n_sensitivity = len(sensitivity_indices)\n    unmatched_penalty = (max(n_primary, n_sensitivity) + 1) * (tolerance_c + 1.0)\n    invalid_penalty = unmatched_penalty * 2.0\n    cost = np.full(\n        (n_primary, n_sensitivity + n_primary),\n        unmatched_penalty,\n        dtype=float,\n    )\n    cost[:, :n_sensitivity] = invalid_penalty\n    for row_position, primary_index in enumerate(primary_indices):\n        primary_temperature = float(primary.loc[primary_index, \"temperature_c\"])\n        for column_position, sensitivity_index in enumerate(sensitivity_indices):\n            delta = abs(\n                float(sensitivity.loc[sensitivity_index, \"temperature_c\"])\n                - primary_temperature\n            )\n            if delta <= tolerance_c:\n                cost[row_position, column_position] = delta\n\n    row_positions, column_positions = linear_sum_assignment(cost)\n    assignment: dict[int, int] = {}\n    for row_position, column_position in zip(\n        row_positions, column_positions, strict=True\n    ):\n        if column_position >= n_sensitivity:\n            continue\n        if cost[row_position, column_position] > tolerance_c:\n            continue\n        assignment[primary_indices[row_position]] = sensitivity_indices[column_position]\n    return assignment\n\n\ndef review_candidates(table: pd.DataFrame, *, tolerance_c: float) -> tuple[pd.DataFrame, pd.DataFrame]:\n    required = {\n        \"run_id\",\n        \"candidate_id\",\n        \"candidate_type\",\n        \"temperature_c\",\n        \"enthalpy_within_fwhm_j_g\",\n    }\n    missing = sorted(required.difference(table.columns))\n    if missing:\n        raise ReviewError(f\"candidate table is missing columns: {', '.join(missing)}\")\n    if not math.isfinite(tolerance_c) or tolerance_c <= 0:\n        raise ReviewError(\"temperature tolerance must be positive\")\n    observed_runs = set(table[\"run_id\"].astype(str))\n    if observed_runs != set(REQUIRED_RUNS):\n        raise ReviewError(\"candidate table must contain exactly the three configured runs\")\n    if not set(table[\"candidate_type\"].astype(str)).issubset({\"endothermic\", \"exothermic\"}):\n        raise ReviewError(\"candidate_type contains unsupported values\")\n\n    primary = table[table[\"run_id\"] == \"primary\"].copy().sort_values(\n        [\"temperature_c\", \"candidate_type\"]\n    )\n    assignments: dict[tuple[str, str], dict[int, int]] = {}\n    used: dict[str, set[int]] = {run_id: set() for run_id in REQUIRED_RUNS[1:]}\n    for candidate_type in (\"endothermic\", \"exothermic\"):\n        primary_subset = primary[primary[\"candidate_type\"] == candidate_type]\n        for run_id in REQUIRED_RUNS[1:]:\n            sensitivity_subset = table[\n                (table[\"run_id\"] == run_id)\n                & (table[\"candidate_type\"] == candidate_type)\n            ]\n            mapping = _optimal_same_direction_assignment(\n                primary_subset,\n                sensitivity_subset,\n                tolerance_c=tolerance_c,\n            )\n            assignments[(run_id, candidate_type)] = mapping\n            used[run_id].update(mapping.values())\n\n    review_rows: list[dict[str, Any]] = []\n    for primary_index, primary_row in primary.iterrows():\n        candidate_type = str(primary_row[\"candidate_type\"])\n        primary_temperature = float(primary_row[\"temperature_c\"])\n        temperatures = [primary_temperature]\n        area_flags = [\n            _directional_area_consistent(\n                candidate_type, primary_row[\"enthalpy_within_fwhm_j_g\"]\n            )\n        ]\n        record: dict[str, Any] = {\n            \"primary_candidate_id\": int(primary_row[\"candidate_id\"]),\n            \"candidate_type\": candidate_type,\n            \"primary_temperature_c\": primary_temperature,\n            \"primary_diagnostic_area_direction_consistent\": area_flags[0],\n        }\n        all_matched = True\n        for run_id in REQUIRED_RUNS[1:]:\n            match_index = assignments[(run_id, candidate_type)].get(int(primary_index))\n            match = table.loc[match_index] if match_index is not None else None\n            prefix = run_id\n            if match is None:\n                all_matched = False\n                record[f\"{prefix}_candidate_id\"] = None\n                record[f\"{prefix}_temperature_c\"] = None\n                record[f\"{prefix}_delta_from_primary_c\"] = None\n                record[f\"{prefix}_diagnostic_area_direction_consistent\"] = False\n                continue\n            match_temperature = float(match[\"temperature_c\"])\n            consistent = _directional_area_consistent(\n                candidate_type, match[\"enthalpy_within_fwhm_j_g\"]\n            )\n            temperatures.append(match_temperature)\n            area_flags.append(consistent)\n            record[f\"{prefix}_candidate_id\"] = int(match[\"candidate_id\"])\n            record[f\"{prefix}_temperature_c\"] = match_temperature\n            record[f\"{prefix}_delta_from_primary_c\"] = (\n                match_temperature - primary_temperature\n            )\n            record[f\"{prefix}_diagnostic_area_direction_consistent\"] = consistent\n\n        maximum_spread = max(temperatures) - min(temperatures)\n        area_consistent = all(area_flags) and len(area_flags) == len(REQUIRED_RUNS)\n        if not all_matched:\n            status = \"smoothing_sensitive_review_required\"\n        elif maximum_spread > tolerance_c:\n            status = \"temperature_spread_review_required\"\n        elif not area_consistent:\n            status = \"stable_temperature_area_direction_review_required\"\n        else:\n            status = \"stable_temperature_review_required\"\n        record.update(\n            {\n                \"all_runs_matched\": all_matched,\n                \"maximum_temperature_spread_c\": maximum_spread,\n                \"all_runs_diagnostic_area_direction_consistent\": area_consistent,\n                \"case_review_status\": status,\n            }\n        )\n        review_rows.append(record)\n\n    unmatched_rows: list[pd.DataFrame] = []\n    for run_id in REQUIRED_RUNS[1:]:\n        subset = table[\n            (table[\"run_id\"] == run_id)\n            & (~table.index.isin(used[run_id]))\n        ].copy()\n        if not subset.empty:\n            unmatched_rows.append(subset)\n    unmatched = (\n        pd.concat(unmatched_rows, ignore_index=True)\n        if unmatched_rows\n        else table.iloc[0:0].copy()\n    )\n    return pd.DataFrame(review_rows), unmatched\n\n\ndef _strip_existing_review(report: str) -> str:\n    text = report.rstrip()\n    if REVIEW_SECTION_START in text:\n        return text.split(REVIEW_SECTION_START, 1)[0].rstrip()\n    legacy_header = \"## Candidate smoothing-sensitivity review\"\n    if legacy_header in text:\n        return text.split(legacy_header, 1)[0].rstrip()\n    return text\n\n\n'''
replace_between(candidate, "def review_candidates", "def _write_manifest", new_review_function)

old_report_start = "    report = report_path.read_text(encoding=\"utf-8\").rstrip()\n"
old_report_end = "    _write_manifest(result_dir)\n"
text = candidate.read_text(encoding="utf-8")
start = text.index(old_report_start)
end = text.index(old_report_end, start)
new_report = '''    report = _strip_existing_review(report_path.read_text(encoding="utf-8"))\n    lines = [\n        report,\n        "",\n        REVIEW_SECTION_START,\n        "## Candidate smoothing-sensitivity review",\n        "",\n        f"- Primary candidates: `{len(reviewed)}`",\n        f"- Matched in both sensitivity runs: `{int(reviewed['all_runs_matched'].sum())}`",\n        f"- Unmatched sensitivity candidates: `{len(unmatched)}`",\n        f"- Matching tolerance: `{tolerance:.3g} degC`",\n        "- Matching objective: `maximum cardinality, then minimum total temperature distance`",\n        "- Analyzer candidate tables modified: `false`",\n        "- Candidate acceptance or rejection performed: `false`",\n        "",\n        "| Type | Primary temperature (degC) | Maximum three-run spread (degC) | Review status |",\n        "|---|---:|---:|---|",\n    ]\n    for row in reviewed.itertuples(index=False):\n        lines.append(\n            f"| {row.candidate_type} | {row.primary_temperature_c:.5g} | "\n            f"{row.maximum_temperature_spread_c:.5g} | `{row.case_review_status}` |"\n        )\n    lines.extend(\n        [\n            "",\n            "Temperature stability across smoothing spans does not establish phase or reaction "\n            "identity. A directionally inconsistent diagnostic within-FWHM area is retained as a "\n            "quality flag rather than silently relabelled or removed.",\n            REVIEW_SECTION_END,\n            "",\n        ]\n    )\n    report_path.write_text("\\n".join(lines), encoding="utf-8")\n'''
candidate.write_text(text[:start] + new_report + text[end:], encoding="utf-8")

replace_exact(
    source,
    """    return {\n        \"filename\": configured[\"filename\"],\n        \"role\": configured[\"role\"],\n        \"bytes\": len(payload),\n        \"source_checksum_algorithm\": configured_algorithm,\n        \"source_checksum\": configured_digest,\n        \"source_checksum_verified\": True,\n        \"downloaded_sha256\": hashlib.sha256(payload).hexdigest(),\n    }\n""",
    """    downloaded_sha256 = hashlib.sha256(payload).hexdigest()\n    expected_sha256 = configured.get(\"verified_sha256\")\n    if expected_sha256 is not None:\n        if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:\n            raise SourceAuditError(\"configured verified_sha256 is invalid\")\n        if downloaded_sha256 != expected_sha256.lower():\n            raise SourceAuditError(f\"SHA-256 mismatch for {configured['filename']}\")\n    return {\n        \"filename\": configured[\"filename\"],\n        \"role\": configured[\"role\"],\n        \"bytes\": len(payload),\n        \"source_checksum_algorithm\": configured_algorithm,\n        \"source_checksum\": configured_digest,\n        \"source_checksum_verified\": True,\n        \"downloaded_sha256\": downloaded_sha256,\n        \"verified_sha256\": expected_sha256.lower() if isinstance(expected_sha256, str) else None,\n        \"verified_sha256_matched\": expected_sha256 is None or downloaded_sha256 == expected_sha256.lower(),\n    }\n""",
)

new_run_function = '''def _longest_strict_run(\n    values: Sequence[float | None], *, increasing: bool\n) -> dict[str, int]:\n    best_start = 0\n    best_end = 0\n    current_start: int | None = None\n    previous: float | None = None\n    for index, value in enumerate(values):\n        if value is None:\n            current_start = None\n            previous = None\n            continue\n        if current_start is None:\n            current_start = index\n        elif previous is None:\n            current_start = index\n        else:\n            valid = value > previous if increasing else value < previous\n            if not valid:\n                current_start = index\n        previous = value\n        if current_start is not None and index + 1 - current_start > best_end - best_start:\n            best_start, best_end = current_start, index + 1\n    return {\n        \"start\": best_start,\n        \"end_exclusive\": best_end,\n        \"length\": best_end - best_start,\n    }\n\n\n'''
replace_between(source, "def _longest_strict_run", "def _profile_table", new_run_function)
replace_exact(
    source,
    """        values = [\n            number\n            for row in data_rows\n            if (number := _parse_number(row[column_index], delimiter=delimiter)) is not None\n        ]\n""",
    """        parsed_values = [\n            _parse_number(row[column_index], delimiter=delimiter)\n            for row in data_rows\n        ]\n        values = [number for number in parsed_values if number is not None]\n""",
)
replace_exact(
    source,
    """        increasing = _longest_strict_run(values, increasing=True)\n        decreasing = _longest_strict_run(values, increasing=False)\n""",
    """        increasing = _longest_strict_run(parsed_values, increasing=True)\n        decreasing = _longest_strict_run(parsed_values, increasing=False)\n""",
)

append_candidate_tests = r'''


def test_global_assignment_maximizes_matches_before_distance() -> None:
    table = pd.DataFrame(
        [
            _row("primary", 1, "exothermic", 0.0, -1.0),
            _row("primary", 2, "exothermic", 10.0, -1.0),
            _row("sensitivity_1c", 1, "exothermic", -6.1, -1.0),
            _row("sensitivity_1c", 2, "exothermic", 4.0, -1.0),
            _row("sensitivity_5c", 1, "exothermic", -6.1, -1.0),
            _row("sensitivity_5c", 2, "exothermic", 4.0, -1.0),
        ]
    )
    reviewed, unmatched = review.review_candidates(table, tolerance_c=10.0)
    assert unmatched.empty
    assert reviewed["all_runs_matched"].all()
    first = reviewed.sort_values("primary_temperature_c").iloc[0]
    second = reviewed.sort_values("primary_temperature_c").iloc[1]
    assert first["sensitivity_1c_temperature_c"] == pytest.approx(-6.1)
    assert second["sensitivity_1c_temperature_c"] == pytest.approx(4.0)


def test_existing_review_section_is_replaced_idempotently() -> None:
    base = "# Report\\n\\nOriginal evidence"
    reviewed = (
        base
        + "\\n\\n"
        + review.REVIEW_SECTION_START
        + "\\n## Candidate smoothing-sensitivity review\\nold\\n"
        + review.REVIEW_SECTION_END
    )
    assert review._strip_existing_review(reviewed) == base
    legacy = base + "\\n\\n## Candidate smoothing-sensitivity review\\nold"
    assert review._strip_existing_review(legacy) == base
'''
text = candidate_tests.read_text(encoding="utf-8")
if "test_global_assignment_maximizes_matches_before_distance" in text:
    raise SystemExit("candidate review tests already appended")
candidate_tests.write_text(text + append_candidate_tests, encoding="utf-8")

append_source_tests = r'''


def test_verify_bytes_rejects_pinned_sha256_drift() -> None:
    payload = b"real source bytes"
    configured = {
        "filename": "data.csv",
        "role": "source",
        "expected_size_bytes": len(payload),
        "checksum_algorithm": "md5",
        "checksum": hashlib.md5(payload).hexdigest(),
        "verified_sha256": "0" * 64,
    }
    repository = {
        "size": len(payload),
        "checksum": "md5:" + hashlib.md5(payload).hexdigest(),
    }
    with pytest.raises(MODULE.SourceAuditError, match="SHA-256 mismatch"):
        MODULE._verify_bytes(
            payload,
            configured=configured,
            repository_record=repository,
        )


def test_invalid_numeric_row_breaks_monotonic_run_and_preserves_offsets() -> None:
    text = "\\n".join(
        [
            "DSC,DSC",
            "Temperature,Heat Flow",
            "degC,mW/mg",
            "20,0.1",
            "25,0.2",
            ",0.3",
            "30,0.4",
            "35,0.5",
            "40,0.6",
        ]
    )
    _, profiles = MODULE._profile_table(text)
    run = profiles[0]["longest_strictly_increasing_run"]
    assert run == {"start": 3, "end_exclusive": 6, "length": 3}
    assert profiles[0]["numeric_value_count"] == 5
'''
text = source_tests.read_text(encoding="utf-8")
if "test_verify_bytes_rejects_pinned_sha256_drift" in text:
    raise SystemExit("source audit tests already appended")
source_tests.write_text(text + append_source_tests, encoding="utf-8")

replace_exact(
    readme,
    """## Scientific closeout\n""",
    """## Regression hardening\n\n- The standalone source audit verifies both the repository MD5 and the pinned SHA-256 before reporting checksum success.\n- Invalid, blank, nonnumeric, or nonfinite temperature cells terminate monotonic runs and retain source-row offsets.\n- Candidate matching maximizes valid one-to-one matches before minimizing total temperature distance within each direction and sensitivity run.\n- Re-running the review replaces its delimited report section rather than appending duplicate human-readable evidence.\n\n## Scientific closeout\n""",
)

print("Applied Zr15Nb DSC review fixes")
