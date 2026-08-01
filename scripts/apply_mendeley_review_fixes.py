from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} occurrence(s), found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


audit = Path("src/mca/tem_mendeley_candidate_audit_engine.py")
facade = Path("src/mca/tem_mendeley_candidate_audit.py")
registry = Path("src/mca/tem_external_validation_candidate_registry_engine.py")
page_probe = Path("scripts/probe_mendeley_public_page.py")
audit_tests = Path("tests/test_tem_mendeley_candidate_audit.py")
registry_tests = Path("tests/test_tem_external_validation_candidate_registry.py")
readme = Path("case_studies/mendeley_cop_co2p_co3o4_tem_candidate/README.md")

# 1-3: primary fail-closed status, complete checksums for duplicate identity,
# and honoring the configured API base.
replace_exact(
    audit,
    """MICROSCOPY_EXTENSIONS = {\n""",
    """PROBE_EVIDENCE_FILENAMES = (\n    \"mendeley_public_page_probe.json\",\n    \"mendeley_anonymous_public_api_probe.json\",\n)\n\nMICROSCOPY_EXTENSIONS = {\n""",
)
replace_exact(
    audit,
    """            snapshot_url = (\n                f\"{PUBLIC_API_BASE}/datasets/{spec.dataset_id}/snapshot/{spec.version}\"\n            )\n            files_url = f\"{PUBLIC_API_BASE}/datasets/{spec.dataset_id}/files?\" + (\n""",
    """            snapshot_url = (\n                f\"{config.api_base}/datasets/{spec.dataset_id}/snapshot/{spec.version}\"\n            )\n            files_url = f\"{config.api_base}/datasets/{spec.dataset_id}/files?\" + (\n""",
)
replace_exact(
    audit,
    """            files = _normalize_files(files_payload)\n""",
    """            files = _normalize_files(files_payload) if files_status == 200 else []\n""",
)
replace_exact(
    audit,
    """        successful_file_sources = sum(\n            int(row[\"root_files_status\"] == 200) for row in dataset_rows\n        )\n""",
    """        successful_file_sources = sum(\n            int(row[\"root_files_status\"] == 200) for row in dataset_rows\n        )\n        primary_dataset_row = next(\n            row for row in dataset_rows if row[\"role\"] == \"primary_raw\"\n        )\n        primary_root_files_request_succeeded = (\n            primary_dataset_row[\"root_files_status\"] == 200\n        )\n""",
)
replace_exact(
    audit,
    """        primary_checksums_complete = bool(primary_rows) and all(\n            bool(row[\"sha256\"]) and int(row[\"size_bytes\"]) > 0\n            for row in primary_rows\n        )\n        if successful_file_sources == 0:\n            status = STATUS_API_BLOCKED\n        elif not file_rows:\n            status = STATUS_NO_FILES\n""",
    """        primary_checksums_complete = _file_identity_complete(primary_rows)\n        if not primary_root_files_request_succeeded:\n            status = STATUS_API_BLOCKED\n        elif not primary_rows:\n            status = STATUS_NO_FILES\n""",
)
replace_exact(
    audit,
    """        duplicate_rows = [\n            row for row in file_rows if row[\"dataset_role\"] == \"duplicate_raw_record\"\n        ]\n        duplicate_identical = bool(primary_rows and duplicate_rows) and _file_signatures(\n            primary_rows\n        ) == _file_signatures(duplicate_rows)\n""",
    """        duplicate_rows = [\n            row for row in file_rows if row[\"dataset_role\"] == \"duplicate_raw_record\"\n        ]\n        duplicate_checksums_complete = _file_identity_complete(duplicate_rows)\n        duplicate_identical = (\n            primary_checksums_complete\n            and duplicate_checksums_complete\n            and _file_signatures(primary_rows) == _file_signatures(duplicate_rows)\n        )\n""",
)
replace_exact(
    audit,
    """                \"api_base\": PUBLIC_API_BASE,\n""",
    """                \"api_base\": config.api_base,\n""",
)
replace_exact(
    audit,
    """                \"primary_file_inventory_resolved\": bool(primary_rows),\n                \"primary_checksums_and_sizes_complete\": primary_checksums_complete,\n""",
    """                \"primary_root_files_request_succeeded\": (\n                    primary_root_files_request_succeeded\n                ),\n                \"primary_file_inventory_resolved\": bool(primary_rows),\n                \"primary_checksums_and_sizes_complete\": primary_checksums_complete,\n                \"duplicate_raw_record_checksums_and_sizes_complete\": (\n                    duplicate_checksums_complete\n                ),\n""",
)
replace_exact(
    audit,
    """                \"status\": \"Diagnostic\" if file_rows else \"Inconclusive\",\n""",
    """                \"status\": (\n                    \"Inconclusive\" if status == STATUS_API_BLOCKED else \"Diagnostic\"\n                ),\n""",
)
replace_exact(
    audit,
    """def _file_signatures(rows: Iterable[Mapping[str, Any]]) -> set[tuple[Any, ...]]:\n""",
    """def _file_identity_complete(rows: Iterable[Mapping[str, Any]]) -> bool:\n    records = list(rows)\n    return bool(records) and all(\n        isinstance(row.get(\"sha256\"), str)\n        and re.fullmatch(r\"[0-9a-f]{64}\", str(row[\"sha256\"]).lower())\n        and int(row.get(\"size_bytes\", 0)) > 0\n        for row in records\n    )\n\n\ndef _file_signatures(rows: Iterable[Mapping[str, Any]]) -> set[tuple[Any, ...]]:\n""",
)

# 6: refresh the metadata manifest after both probe artifacts are generated.
replace_exact(
    audit,
    """def _prepare_output(path: str | Path) -> Path:\n""",
    """def refresh_mendeley_candidate_audit_manifest(\n    output_dir: str | Path,\n) -> dict[str, Any]:\n    output = Path(output_dir)\n    if not output.is_dir() or output.is_symlink():\n        raise FileNotFoundError(\"candidate audit output directory is required\")\n    required_names = (\n        \"mendeley_dataset_inventory.csv\",\n        \"mendeley_file_inventory.csv\",\n        \"mendeley_candidate_audit_summary.json\",\n        \"mendeley_candidate_audit_report.md\",\n        \"mendeley_api_snapshots.json\",\n        *PROBE_EVIDENCE_FILENAMES,\n    )\n    paths = [output / name for name in required_names]\n    missing = [path.name for path in paths if not path.is_file()]\n    if missing:\n        raise FileNotFoundError(\n            \"candidate audit evidence is incomplete: \" + \", \".join(missing)\n        )\n    manifest = _manifest(output, paths)\n    _write_json(output / \"mendeley_candidate_audit_manifest.json\", manifest)\n    return manifest\n\n\ndef _prepare_output(path: str | Path) -> Path:\n""",
)
replace_exact(
    facade,
    """    load_config,\n    run_mendeley_candidate_audit,\n)\n""",
    """    load_config,\n    refresh_mendeley_candidate_audit_manifest,\n    run_mendeley_candidate_audit,\n)\n""",
)
replace_exact(
    facade,
    """    \"load_config\",\n    \"run_mendeley_candidate_audit\",\n]\n""",
    """    \"load_config\",\n    \"refresh_mendeley_candidate_audit_manifest\",\n    \"run_mendeley_candidate_audit\",\n]\n""",
)

# 4 and 7: preserve v1 inventory columns and keep rendered exclusions out of
# the mutually exclusive control bucket.
replace_exact(
    registry,
    """        \"independent_segmentation_labels_available\": (\n            candidate.independent_segmentation_labels_available\n        ),\n        \"immutable_sample_ids_available\": candidate.immutable_sample_ids_available,\n""",
    """        \"independent_segmentation_labels_available\": (\n            candidate.independent_segmentation_labels_available\n        ),\n        \"label_origin\": candidate.label_origin,\n        \"labeler_count\": candidate.labeler_count,\n        \"immutable_sample_ids_available\": candidate.immutable_sample_ids_available,\n""",
)
replace_exact(
    registry,
    """        \"reuse_license_verified\": candidate.reuse_license_verified,\n        \"evaluation_ready\": ready,\n""",
    """        \"reuse_license_verified\": candidate.reuse_license_verified,\n        \"target_training_source\": candidate.target_training_source,\n        \"in_domain_external_validation_ready\": ready,\n        \"evaluation_ready\": ready,\n""",
)
replace_exact(
    registry,
    """        \"excluded_control_count\": (\n            count(TARGET_SOURCE) + count(WRONG_MODALITY) + count(EXCLUDED_REPRESENTATION)\n        ),\n""",
    """        \"excluded_control_count\": count(TARGET_SOURCE) + count(WRONG_MODALITY),\n""",
)
replace_exact(
    registry,
    """    \"independent_segmentation_labels_available\",\n    \"immutable_sample_ids_available\",\n""",
    """    \"independent_segmentation_labels_available\",\n    \"label_origin\",\n    \"labeler_count\",\n    \"immutable_sample_ids_available\",\n""",
)
replace_exact(
    registry,
    """    \"reuse_license_verified\",\n    \"evaluation_ready\",\n""",
    """    \"reuse_license_verified\",\n    \"target_training_source\",\n    \"in_domain_external_validation_ready\",\n    \"evaluation_ready\",\n""",
)

# 5: remove query strings and fragments from all stored page/asset URLs.
replace_exact(
    page_probe,
    """def _clues(text: str, dataset_id: str) -> dict[str, Any]:\n""",
    """def _sanitize_url(url: str) -> str:\n    parsed = urllib.parse.urlsplit(url)\n    return urllib.parse.urlunsplit(\n        (parsed.scheme, parsed.netloc, parsed.path, \"\", \"\")\n    )\n\n\ndef _clues(text: str, dataset_id: str) -> dict[str, Any]:\n""",
)
replace_exact(
    page_probe,
    """    urls = sorted(\n        url.rstrip(\".,);]\")\n        for url in set(URL_PATTERN.findall(text))\n        if dataset_id in url or \"mendeley\" in url.lower()\n    )\n""",
    """    urls = sorted(\n        {\n            _sanitize_url(url.rstrip(\".,);]\"))\n            for url in URL_PATTERN.findall(text)\n            if dataset_id in url or \"mendeley\" in url.lower()\n        }\n    )\n""",
)
replace_exact(
    page_probe,
    """                \"final_url\": final_url,\n""",
    """                \"final_url\": _sanitize_url(final_url),\n""",
)
replace_exact(
    page_probe,
    """                \"script_urls\": script_urls,\n""",
    """                \"script_urls\": [_sanitize_url(item) for item in script_urls],\n""",
)
replace_exact(
    page_probe,
    """                assets.append({\"url\": script_url, \"error\": type(exc).__name__})\n""",
    """                assets.append(\n                    {\"url\": _sanitize_url(script_url), \"error\": type(exc).__name__}\n                )\n""",
)
replace_exact(
    page_probe,
    """                        \"url\": script_url,\n                        \"final_url\": asset_final,\n""",
    """                        \"url\": _sanitize_url(script_url),\n                        \"final_url\": _sanitize_url(asset_final),\n""",
)

# New manifest-refresh CLI used by the dedicated workflow.
refresh_script = Path("scripts/refresh_mendeley_candidate_audit_manifest.py")
if refresh_script.exists():
    raise SystemExit("refresh script already exists")
refresh_script.write_text(
    '''"""Refresh the checksum manifest after public-page and API probes."""\nfrom __future__ import annotations\n\nimport argparse\nimport json\nfrom pathlib import Path\n\nfrom mca.tem_mendeley_candidate_audit import (\n    refresh_mendeley_candidate_audit_manifest,\n)\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument("--output", type=Path, required=True)\n    args = parser.parse_args()\n    manifest = refresh_mendeley_candidate_audit_manifest(args.output)\n    print(json.dumps(manifest, indent=2, sort_keys=True))\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n''',
    encoding="utf-8",
)

# Regression tests for all seven findings.
replace_exact(
    audit_tests,
    """    AuditConfig,\n    run_mendeley_candidate_audit,\n)\n""",
    """    AuditConfig,\n    refresh_mendeley_candidate_audit_manifest,\n    run_mendeley_candidate_audit,\n)\n""",
)
append_audit_tests = r'''


def test_primary_file_failure_is_blocked_when_other_records_succeed(
    tmp_path: Path,
) -> None:
    def partial(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        del accept
        dataset_id = next(
            item
            for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
            if item in url
        )
        if "/snapshot/" in url:
            return 200, {}, _snapshot(dataset_id)
        if dataset_id == "8w66synjmx":
            return 503, {}, {"message": "primary unavailable"}
        return 200, {}, [_file(dataset_id, "database.rar", "a" * 64, 123)]

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=partial,
    )
    assert summary["inventory_readiness"]["status"] == STATUS_API_BLOCKED
    assert not summary["inventory_readiness"]["primary_root_files_request_succeeded"]
    assert not summary["inventory_readiness"]["primary_file_inventory_resolved"]
    assert summary["scientific_closeout"]["status"] == "Inconclusive"


def test_duplicate_identity_requires_complete_checksums(tmp_path: Path) -> None:
    def missing_checksums(
        url: str, accept: str
    ) -> tuple[int, Mapping[str, str], Any]:
        del accept
        dataset_id = next(
            item
            for item in ("8w66synjmx", "zhnbzhjrtr", "jz9dpgwwc3")
            if item in url
        )
        if "/snapshot/" in url:
            return 200, {}, _snapshot(dataset_id)
        item = _file(dataset_id, "database.rar", "a" * 64, 123)
        item["content_details"].pop("sha256_hash")
        return 200, {}, [item]

    summary = run_mendeley_candidate_audit(
        _config(),
        tmp_path / "out",
        transport=missing_checksums,
    )
    assert not summary["inventory_readiness"]["primary_checksums_and_sizes_complete"]
    assert not summary["inventory_readiness"][
        "duplicate_raw_record_checksums_and_sizes_complete"
    ]
    assert not summary["inventory_readiness"][
        "duplicate_raw_record_content_identical"
    ]


def test_configured_api_base_is_used_and_reported(tmp_path: Path) -> None:
    payload = {
        "case_id": "mendeley_cop_co2p_co3o4_tem_candidate_audit",
        "api_base": "https://api.data.mendeley.com",
        "datasets": [
            {
                "dataset_id": item.dataset_id,
                "version": item.version,
                "doi": item.doi,
                "role": item.role,
                "expected_title_fragment": item.expected_title_fragment,
            }
            for item in _config().datasets
        ],
    }
    config = AuditConfig.from_mapping(payload)
    observed_urls: list[str] = []

    def transport(url: str, accept: str) -> tuple[int, Mapping[str, str], Any]:
        observed_urls.append(url)
        return _transport(url, accept)

    summary = run_mendeley_candidate_audit(
        config,
        tmp_path / "out",
        transport=transport,
    )
    assert observed_urls
    assert all(url.startswith("https://api.data.mendeley.com/") for url in observed_urls)
    assert summary["source"]["api_base"] == "https://api.data.mendeley.com"


def test_refresh_manifest_binds_probe_artifacts(tmp_path: Path) -> None:
    output = tmp_path / "out"
    run_mendeley_candidate_audit(_config(), output, transport=_transport)
    (output / "mendeley_public_page_probe.json").write_text(
        '{"case_id":"page-probe"}\n', encoding="utf-8"
    )
    (output / "mendeley_anonymous_public_api_probe.json").write_text(
        '{"case_id":"api-probe"}\n', encoding="utf-8"
    )
    manifest = refresh_mendeley_candidate_audit_manifest(output)
    assert manifest["artifact_count"] == 7
    paths = {record["path"] for record in manifest["artifacts"]}
    assert "mendeley_public_page_probe.json" in paths
    assert "mendeley_anonymous_public_api_probe.json" in paths
    for record in manifest["artifacts"]:
        path = output / record["path"]
        assert record["bytes"] == path.stat().st_size
        assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
'''
text = audit_tests.read_text(encoding="utf-8")
if "test_primary_file_failure_is_blocked_when_other_records_succeed" in text:
    raise SystemExit("Mendeley audit tests already appended")
audit_tests.write_text(text + append_audit_tests, encoding="utf-8")

# CSV schema/count regression tests.
replace_exact(
    registry_tests,
    """import hashlib\nimport json\n""",
    """import csv\nimport hashlib\nimport json\n""",
)
replace_exact(
    registry_tests,
    '        "excluded_control_count": 3,\n',
    '        "excluded_control_count": 2,\n',
)
append_registry_tests = r'''


def test_candidate_inventory_preserves_versioned_provenance_columns(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    run_candidate_registry(load_registry_config(CONFIG), output)
    with (output / "tem_external_validation_candidate_inventory.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    expected = {
        "label_origin",
        "labeler_count",
        "target_training_source",
        "in_domain_external_validation_ready",
        "evaluation_ready",
    }
    assert expected.issubset(rows[0])
    target = next(
        row
        for row in rows
        if row["candidate_id"] == "zenodo_14927582_target_training_source"
    )
    assert target["target_training_source"] == "True"
    assert target["in_domain_external_validation_ready"] == "False"
    assert target["evaluation_ready"] == "False"


def test_mutually_exclusive_candidate_status_counts_reconcile(
    tmp_path: Path,
) -> None:
    counts = run_candidate_registry(
        load_registry_config(CONFIG), tmp_path / "out"
    )["result_counts"]
    bucket_total = sum(
        counts[key]
        for key in (
            "in_domain_external_validation_ready_count",
            "metadata_resolution_candidate_count",
            "annotation_pilot_candidate_count",
            "rendered_representation_exclusion_count",
            "cross_phase_candidate_count",
            "diagnostic_cross_material_candidate_count",
            "excluded_control_count",
        )
    )
    assert bucket_total == counts["candidate_count"]
'''
text = registry_tests.read_text(encoding="utf-8")
if "test_candidate_inventory_preserves_versioned_provenance_columns" in text:
    raise SystemExit("candidate registry tests already appended")
registry_tests.write_text(text + append_registry_tests, encoding="utf-8")

# Dedicated URL sanitization tests.
page_tests = Path("tests/test_probe_mendeley_public_page.py")
if page_tests.exists():
    raise SystemExit("page probe tests already exist")
page_tests.write_text(
    '''from __future__ import annotations\n\nimport importlib.util\nfrom pathlib import Path\n\nSCRIPT = Path(__file__).parents[1] / "scripts" / "probe_mendeley_public_page.py"\nSPEC = importlib.util.spec_from_file_location("probe_mendeley_public_page", SCRIPT)\nassert SPEC is not None and SPEC.loader is not None\nMODULE = importlib.util.module_from_spec(SPEC)\nSPEC.loader.exec_module(MODULE)\n\n\ndef test_sanitize_url_removes_query_and_fragment() -> None:\n    value = MODULE._sanitize_url(\n        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file?"\n        "X-Amz-Signature=secret&token=also-secret#fragment"\n    )\n    assert value == (\n        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file"\n    )\n\n\ndef test_relevant_url_clues_never_store_signed_query_values() -> None:\n    text = (\n        "https://data.mendeley.com/public-files/datasets/8w66synjmx/file?"\n        "X-Amz-Signature=secret&X-Amz-Credential=credential"\n    )\n    clues = MODULE._clues(text, "8w66synjmx")\n    encoded = " ".join(clues["relevant_urls"])\n    assert "?" not in encoded\n    assert "secret" not in encoded\n    assert "Credential" not in encoded\n''',
    encoding="utf-8",
)

replace_exact(
    readme,
    """This command resolves immutable dataset snapshots and root-file UUID, size, and SHA-256 metadata. It does not download the archive.\n""",
    """This command resolves immutable dataset snapshots and root-file UUID, size, and SHA-256 metadata. It does not download the archive. A failed primary root-file request remains `blocked_public_api_metadata_access` even when control records respond. Duplicate-record identity is asserted only when both inventories provide valid SHA-256 values and positive byte sizes, and the configured API base is the endpoint actually queried and reported.\n""",
)
replace_exact(
    readme,
    """5. deletes the source bytes and uploads metadata-only evidence.\n""",
    """5. strips query strings and fragments from every persisted landing-page or asset URL;\n6. regenerates the metadata artifact manifest after both probe files exist, so all uploaded metadata evidence is checksum-bound;\n7. deletes the source bytes and uploads metadata-only evidence.\n""",
)

print("Applied Mendeley audit and candidate-registry review fixes")
