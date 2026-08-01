from __future__ import annotations

from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected_count:
        raise SystemExit(f"{path}: expected {expected_count} occurrence(s), found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


source = Path("src/mca/tem_external_validation_intake.py")
tests = Path("tests/test_tem_external_validation_intake.py")
template = Path("case_studies/tem_external_validation_intake/manifest_template.example.json")
readme = Path("case_studies/tem_external_validation_intake/README.md")
changelog = Path("CHANGELOG.md")

replace_exact(
    source,
    """    test_manifest_checksum_frozen: bool\n    metrics_frozen: bool\n""",
    """    test_manifest_checksum_frozen: bool\n    frozen_manifest_sha256: str | None\n    metrics_frozen: bool\n""",
)
replace_exact(
    source,
    """            \"test_manifest_checksum_frozen\",\n            \"metrics_frozen\",\n""",
    """            \"test_manifest_checksum_frozen\",\n            \"frozen_manifest_sha256\",\n            \"metrics_frozen\",\n""",
)
replace_exact(
    source,
    """            test_manifest_checksum_frozen=_boolean(\n                payload, \"test_manifest_checksum_frozen\"\n            ),\n            metrics_frozen=_boolean(payload, \"metrics_frozen\"),\n""",
    """            test_manifest_checksum_frozen=_boolean(\n                payload, \"test_manifest_checksum_frozen\"\n            ),\n            frozen_manifest_sha256=_optional_sha256(\n                payload.get(\"frozen_manifest_sha256\"),\n                \"frozen_manifest_sha256\",\n            ),\n            metrics_frozen=_boolean(payload, \"metrics_frozen\"),\n""",
)
replace_exact(
    source,
    """        if protocol.all_freeze_flags and protocol.frozen_protocol_id is None:\n            raise IntakeContractError(\n                \"frozen_protocol_id is required when all protocol fields are frozen\"\n            )\n        return protocol\n""",
    """        if protocol.test_manifest_checksum_frozen and protocol.frozen_manifest_sha256 is None:\n            raise IntakeContractError(\n                \"frozen_manifest_sha256 is required when test_manifest_checksum_frozen is true\"\n            )\n        if not protocol.test_manifest_checksum_frozen and protocol.frozen_manifest_sha256 is not None:\n            raise IntakeContractError(\n                \"frozen_manifest_sha256 must be null until test_manifest_checksum_frozen is true\"\n            )\n        if protocol.all_freeze_flags and protocol.frozen_protocol_id is None:\n            raise IntakeContractError(\n                \"frozen_protocol_id is required when all protocol fields are frozen\"\n            )\n        return protocol\n""",
)
replace_exact(
    source,
    """class IntakeManifest:\n    case_id: str\n    dataset: DatasetContract\n    images: tuple[ImageRecord, ...]\n    annotations: tuple[AnnotationRecord, ...]\n    evaluation_protocol: EvaluationProtocol\n""",
    """class IntakeManifest:\n    case_id: str\n    dataset: DatasetContract\n    images: tuple[ImageRecord, ...]\n    annotations: tuple[AnnotationRecord, ...]\n    evaluation_protocol: EvaluationProtocol\n    computed_manifest_sha256: str\n""",
)
replace_exact(
    source,
    """            evaluation_protocol=EvaluationProtocol.from_mapping(\n                _mapping(payload, \"evaluation_protocol\")\n            ),\n        )\n""",
    """            evaluation_protocol=EvaluationProtocol.from_mapping(\n                _mapping(payload, \"evaluation_protocol\")\n            ),\n            computed_manifest_sha256=compute_intake_manifest_sha256(payload),\n        )\n""",
)
replace_exact(
    source,
    """        _unique([image.image_id for image in self.images], \"image_id\")\n        _unique([annotation.annotation_id for annotation in self.annotations], \"annotation_id\")\n        image_ids = {image.image_id for image in self.images}\n""",
    """        _unique([image.image_id for image in self.images], \"image_id\")\n        _unique([annotation.annotation_id for annotation in self.annotations], \"annotation_id\")\n        _unique(\n            [annotation.relative_path for annotation in self.annotations],\n            \"annotation relative_path\",\n        )\n        protocol = self.evaluation_protocol\n        if (\n            protocol.test_manifest_checksum_frozen\n            and protocol.frozen_manifest_sha256 != self.computed_manifest_sha256\n        ):\n            raise IntakeContractError(\n                \"frozen_manifest_sha256 does not match the canonical manifest SHA-256: \"\n                f\"{protocol.frozen_manifest_sha256} != {self.computed_manifest_sha256}\"\n            )\n        image_ids = {image.image_id for image in self.images}\n""",
)
replace_exact(
    source,
    """def load_intake_manifest(path: str | Path) -> IntakeManifest:\n    payload = json.loads(Path(path).read_text(encoding=\"utf-8\"))\n    if not isinstance(payload, Mapping):\n        raise IntakeContractError(\"manifest must contain a JSON object\")\n    return IntakeManifest.from_mapping(payload)\n""",
    """def load_intake_manifest(path: str | Path) -> IntakeManifest:\n    payload = json.loads(\n        Path(path).read_text(encoding=\"utf-8\"),\n        object_pairs_hook=_strict_json_object,\n    )\n    if not isinstance(payload, Mapping):\n        raise IntakeContractError(\"manifest must contain a JSON object\")\n    return IntakeManifest.from_mapping(payload)\n\n\ndef compute_intake_manifest_sha256(payload: Mapping[str, Any]) -> str:\n    \"\"\"Return the canonical manifest digest used by the protocol-freeze gate.\n\n    The self-referential checksum field and its declaration boolean are normalized\n    before hashing. All dataset, image, annotation, audit, metric, exclusion, and\n    protocol-ID fields remain bound by the digest.\n    \"\"\"\n\n    canonical = json.loads(json.dumps(payload, ensure_ascii=False))\n    if not isinstance(canonical, dict):\n        raise IntakeContractError(\"manifest must contain a JSON object\")\n    protocol = canonical.get(\"evaluation_protocol\")\n    if not isinstance(protocol, dict):\n        raise IntakeContractError(\"evaluation_protocol must be an object\")\n    protocol[\"test_manifest_checksum_frozen\"] = False\n    protocol[\"frozen_manifest_sha256\"] = None\n    encoded = json.dumps(\n        canonical,\n        ensure_ascii=False,\n        sort_keys=True,\n        separators=(\",\", \":\"),\n    ).encode(\"utf-8\")\n    return hashlib.sha256(encoded).hexdigest()\n""",
)
replace_exact(
    source,
    """        file_rows: list[dict[str, Any]] = []\n        image_hashes: Counter[str] = Counter()\n        for image in manifest.images:\n""",
    """        file_rows: list[dict[str, Any]] = []\n        for image in manifest.images:\n""",
)
replace_exact(
    source,
    """            image_hashes[record[\"sha256\"]] += 1\n            file_rows.append(\n""",
    """            file_rows.append(\n""",
)
replace_exact(
    source,
    """        active_images = [image for image in manifest.images if not image.excluded]\n        duplicate_active_content = sum(\n            count - 1\n            for digest, count in image_hashes.items()\n            if count > 1\n            and any(\n                image.sha256 == digest and not image.excluded\n                for image in manifest.images\n            )\n        )\n""",
    """        active_images = [image for image in manifest.images if not image.excluded]\n        active_image_ids = {image.image_id for image in active_images}\n        active_annotations = [\n            annotation\n            for annotation in manifest.annotations\n            if annotation.image_id in active_image_ids\n        ]\n        active_image_hashes = Counter(image.sha256 for image in active_images)\n        duplicate_active_content = sum(\n            count - 1 for count in active_image_hashes.values() if count > 1\n        )\n""",
)
replace_exact(
    source,
    """        decision = _decision(gates, annotations_present=bool(manifest.annotations))\n""",
    """        decision = _decision(gates, annotations_present=bool(active_annotations))\n""",
)
replace_exact(
    source,
    """                \"annotation_count\": len(manifest.annotations),\n                \"duplicate_active_image_content_count\": duplicate_active_content,\n            },\n            \"evidence_gates\": gates,\n""",
    """                \"annotation_count\": len(manifest.annotations),\n                \"active_annotation_count\": len(active_annotations),\n                \"duplicate_active_image_content_count\": duplicate_active_content,\n            },\n            \"manifest_identity\": {\n                \"computed_manifest_sha256\": manifest.computed_manifest_sha256,\n                \"frozen_manifest_sha256\": (\n                    manifest.evaluation_protocol.frozen_manifest_sha256\n                ),\n            },\n            \"evidence_gates\": gates,\n""",
)
replace_exact(
    source,
    """        unique_blinded_labelers = {\n            record.labeler_id\n            for record in independent\n            if record.blinded_to_model_predictions\n            and not record.used_for_model_development\n        }\n        versions = {record.label_definition_version for record in records}\n        complete = (\n            len(unique_blinded_labelers)\n            >= dataset.minimum_independent_blinded_labelers\n            and len(consensus) == 1\n            and consensus[0].blinded_to_model_predictions\n            and not consensus[0].used_for_model_development\n            and len(versions) == 1\n        )\n""",
    """        unique_blinded_labelers = {\n            record.labeler_id\n            for record in independent\n            if record.blinded_to_model_predictions\n            and not record.used_for_model_development\n        }\n        versions = {record.label_definition_version for record in records}\n        all_records_clean = bool(records) and all(\n            record.blinded_to_model_predictions\n            and not record.used_for_model_development\n            for record in records\n        )\n        complete = (\n            all_records_clean\n            and len(unique_blinded_labelers)\n            >= dataset.minimum_independent_blinded_labelers\n            and len(consensus) == 1\n            and len(versions) == 1\n        )\n""",
)
replace_exact(
    source,
    """            \"label_definition_version_count\": len(versions),\n            \"complete\": complete,\n""",
    """            \"label_definition_version_count\": len(versions),\n            \"all_annotations_blinded_and_model_development_nonuse\": all_records_clean,\n            \"complete\": complete,\n""",
)
replace_exact(
    source,
    """    annotations_complete = bool(active_images) and complete_images == len(active_images)\n    protocol = manifest.evaluation_protocol\n    protocol_ready = (\n        annotations_complete\n        and protocol.all_audits_passed\n        and protocol.all_freeze_flags\n        and protocol.frozen_protocol_id is not None\n    )\n    annotation_pilot_ready = all(\n""",
    """    annotations_complete = bool(active_images) and complete_images == len(active_images)\n    protocol = manifest.evaluation_protocol\n    annotation_pilot_ready = all(\n""",
)
replace_exact(
    source,
    """    )\n\n    unresolved: list[str] = []\n    checks = {\n""",
    """    )\n    frozen_manifest_bound = (\n        protocol.test_manifest_checksum_frozen\n        and protocol.frozen_manifest_sha256 == manifest.computed_manifest_sha256\n    )\n    protocol_ready = (\n        annotation_pilot_ready\n        and annotations_complete\n        and protocol.all_audits_passed\n        and protocol.all_freeze_flags\n        and frozen_manifest_bound\n        and protocol.frozen_protocol_id is not None\n    )\n\n    unresolved: list[str] = []\n    checks = {\n""",
)
replace_exact(
    source,
    """        \"evaluation_protocol_frozen\": protocol.all_freeze_flags,\n        \"predeclared_external_evaluation_ready\": protocol_ready,\n""",
    """        \"frozen_manifest_sha256_matches\": frozen_manifest_bound,\n        \"evaluation_protocol_frozen\": (\n            protocol.all_freeze_flags and frozen_manifest_bound\n        ),\n        \"predeclared_external_evaluation_ready\": protocol_ready,\n""",
)
replace_exact(
    source,
    """def _optional_positive_float(value: Any, key: str) -> float | None:\n""",
    """def _optional_sha256(value: Any, key: str) -> str | None:\n    if value is None:\n        return None\n    if not isinstance(value, str):\n        raise IntakeContractError(f\"{key} must be null or a SHA-256 string\")\n    normalized = value.strip().lower()\n    if not re.fullmatch(r\"[0-9a-f]{64}\", normalized):\n        raise IntakeContractError(f\"{key} must contain 64 lowercase hexadecimal characters\")\n    return normalized\n\n\ndef _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:\n    result: dict[str, Any] = {}\n    for key, value in pairs:\n        if key in result:\n            raise IntakeContractError(f\"duplicate JSON object key: {key}\")\n        result[key] = value\n    return result\n\n\ndef _optional_positive_float(value: Any, key: str) -> float | None:\n""",
)

replace_exact(
    tests,
    """    load_intake_manifest,\n    run_external_validation_intake,\n)\n""",
    """    compute_intake_manifest_sha256,\n    load_intake_manifest,\n    run_external_validation_intake,\n)\n""",
)
replace_exact(
    tests,
    """        \"test_manifest_checksum_frozen\": complete,\n        \"metrics_frozen\": complete,\n""",
    """        \"test_manifest_checksum_frozen\": complete,\n        \"frozen_manifest_sha256\": None,\n        \"metrics_frozen\": complete,\n""",
)
replace_exact(
    tests,
    """def _manifest(images: list[dict], annotations: list[dict], *, protocol_complete: bool = False) -> dict:\n    return {\n""",
    """def _manifest(images: list[dict], annotations: list[dict], *, protocol_complete: bool = False) -> dict:\n    payload = {\n""",
)
replace_exact(
    tests,
    """        \"evaluation_protocol\": _protocol(complete=protocol_complete),\n    }\n\n\ndef _write_manifest(path: Path, payload: dict) -> Path:\n""",
    """        \"evaluation_protocol\": _protocol(complete=protocol_complete),\n    }\n    if protocol_complete:\n        payload[\"evaluation_protocol\"][\"frozen_manifest_sha256\"] = (\n            compute_intake_manifest_sha256(payload)\n        )\n    return payload\n\n\ndef _write_manifest(path: Path, payload: dict) -> Path:\n""",
)

append_tests = r'''


def test_blocked_dataset_never_allows_inference_even_with_complete_protocol(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    for image in images:
        image["representation"] = "rendered_figure"
        image["original_detector_intensity_available"] = False
    payload = _manifest(images, _complete_annotations(root), protocol_complete=True)
    summary = run_external_validation_intake(
        load_intake_manifest(_write_manifest(tmp_path / "manifest.json", payload)),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == BLOCKED
    assert not summary["decision"]["predeclared_external_model_evaluation_ready"]
    assert not summary["decision"]["model_inference_allowed_now"]


def test_excluded_copy_does_not_count_as_duplicate_active_content(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    duplicate_digest = _write_file(root, "images/excluded-copy.tif", b"synthetic-image-a")
    excluded = _image(
        "image-excluded",
        "images/excluded-copy.tif",
        duplicate_digest,
        "sample-excluded",
        "acq-excluded",
    )
    excluded["excluded"] = True
    excluded["exclusion_reason"] = "archival duplicate retained for provenance"
    images.append(excluded)
    summary = run_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(images, []))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == ANNOTATION_READY
    assert summary["result_counts"]["duplicate_active_image_content_count"] == 0


def test_annotations_for_excluded_images_do_not_change_active_annotation_status(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    excluded_digest = _write_file(root, "images/excluded.tif", b"excluded-image")
    excluded = _image(
        "image-excluded",
        "images/excluded.tif",
        excluded_digest,
        "sample-excluded",
        "acq-excluded",
    )
    excluded["excluded"] = True
    excluded["exclusion_reason"] = "not part of the frozen cohort"
    images.append(excluded)
    label_digest = _write_file(root, "labels/excluded.png", b"excluded-label")
    annotations = [
        _annotation(
            "excluded-label",
            "image-excluded",
            "labels/excluded.png",
            label_digest,
            "expert-1",
            "independent",
        )
    ]
    summary = run_external_validation_intake(
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(images, annotations))
        ),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == ANNOTATION_READY
    assert summary["result_counts"]["annotation_count"] == 1
    assert summary["result_counts"]["active_annotation_count"] == 0


def test_frozen_manifest_digest_detects_post_freeze_mutation(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    payload = _manifest(
        _two_images(root),
        _complete_annotations(root),
        protocol_complete=True,
    )
    payload["images"][0]["sample_id"] = "post-freeze-mutated-sample"
    with pytest.raises(IntakeContractError, match="does not match the canonical manifest"):
        load_intake_manifest(_write_manifest(tmp_path / "manifest.json", payload))


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":"1.0","schema_version":"0.9"}',
        encoding="utf-8",
    )
    with pytest.raises(IntakeContractError, match="duplicate JSON object key"):
        load_intake_manifest(path)


def test_any_contaminated_active_annotation_blocks_completion(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    annotations = _complete_annotations(root)
    digest = _write_file(root, "labels/image-a-contaminated.png", b"contaminated")
    annotations.append(
        _annotation(
            "image-a-contaminated",
            "image-a",
            "labels/image-a-contaminated.png",
            digest,
            "expert-3",
            "independent",
            blinded=False,
            used_for_model_selection=True,
        )
    )
    payload = _manifest(images, annotations, protocol_complete=True)
    summary = run_external_validation_intake(
        load_intake_manifest(_write_manifest(tmp_path / "manifest.json", payload)),
        root,
        tmp_path / "out",
    )
    assert summary["decision"]["status"] == ANNOTATION_INCOMPLETE
    assert not summary["evidence_gates"]["independent_annotations_complete"]
    assert not summary["decision"]["model_inference_allowed_now"]
    assert not summary["evidence_gates"]["annotation_completion_by_image"]["image-a"][
        "all_annotations_blinded_and_model_development_nonuse"
    ]


def test_duplicate_annotation_file_path_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    images = _two_images(root)
    digest = _write_file(root, "labels/shared.png", b"shared-label")
    annotations = [
        _annotation(
            "image-a-expert-1",
            "image-a",
            "labels/shared.png",
            digest,
            "expert-1",
            "independent",
        ),
        _annotation(
            "image-a-expert-2",
            "image-a",
            "labels/shared.png",
            digest,
            "expert-2",
            "independent",
        ),
    ]
    with pytest.raises(IntakeContractError, match="duplicate annotation relative_path"):
        load_intake_manifest(
            _write_manifest(tmp_path / "manifest.json", _manifest(images, annotations))
        )
'''
text = tests.read_text(encoding="utf-8")
if "test_blocked_dataset_never_allows_inference_even_with_complete_protocol" in text:
    raise SystemExit("tests already appended")
tests.write_text(text + append_tests, encoding="utf-8")

replace_exact(
    template,
    '    "test_manifest_checksum_frozen": false,\n    "metrics_frozen": false,\n',
    '    "test_manifest_checksum_frozen": false,\n    "frozen_manifest_sha256": null,\n    "metrics_frozen": false,\n',
)
replace_exact(
    readme,
    """- checksum-bound test manifest;\n- metrics;\n""",
    """- checksum-bound test manifest with a canonical SHA-256 stored in `frozen_manifest_sha256`;\n- metrics;\n""",
)
replace_exact(
    readme,
    """Even then, the intake reports only `ready_for_predeclared_external_evaluation`. An independent performance claim requires the later frozen inference run and its validated results.\n""",
    """The canonical digest normalizes only the self-referential `test_manifest_checksum_frozen` and `frozen_manifest_sha256` fields. Dataset identity, active/excluded images, annotations, audit states, metric/uncertainty/exclusion freeze fields, and the protocol ID remain checksum-bound. Run the intake before final freeze, copy `manifest_identity.computed_manifest_sha256` into `frozen_manifest_sha256`, then set `test_manifest_checksum_frozen` to `true` without changing any other field.\n\nEven then, the intake reports only `ready_for_predeclared_external_evaluation`. An independent performance claim requires the later frozen inference run and its validated results.\n""",
)
replace_exact(
    changelog,
    """## [Unreleased]\n\nNo unreleased changes are currently recorded.\n""",
    """## [Unreleased]\n\n### Fixed\n\n- TEM external-validation intake now keeps model inference blocked whenever any dataset or image gate fails, even if annotations and protocol fields are otherwise complete.\n- Canonical manifest SHA-256 binding now detects post-freeze cohort or protocol mutation, and duplicate JSON object keys fail closed.\n- Duplicate active-image detection ignores excluded archival copies, excluded-image annotations do not change active-cohort status, every active annotation must remain blinded and unused for model development, and annotation file paths must be unique.\n""",
)

print("Applied TEM external-validation intake review fixes")
