from __future__ import annotations

import json
from pathlib import Path


def replace_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    marker = old.splitlines()[0] if old.splitlines() else repr(old)
    if count != expected_count:
        raise SystemExit(
            f"{path}: marker {marker!r}: expected {expected_count}, found {count}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


engine = Path("src/mca/tem_external_validation_candidate_registry_engine.py")
bridge = Path("src/mca/tem_candidate_registry_readiness.py")
config_path = Path("case_studies/tem_external_validation_candidate_registry/case_config.json")
registry_tests = Path("tests/test_tem_external_validation_candidate_registry.py")
bridge_tests = Path("tests/test_tem_candidate_registry_readiness_integration.py")
readme = Path("case_studies/tem_external_validation_candidate_registry/README.md")

replace_exact(
    engine,
    'RESULT = "no_public_candidate_ready_for_in_domain_external_validation"\n',
    'RESULT = "no_public_candidate_ready_for_in_domain_external_validation"\n'
    'READY_RESULT = "public_candidate_ready_for_dedicated_in_domain_validation_audit"\n'
    'SUPPORTED_TARGET_TASK = "binary nanoparticle segmentation for cobalt-oxide TEM or HRTEM images"\n'
    'SUPPORTED_TARGET_MATERIAL = "cobalt oxide"\n'
    'SUPPORTED_TARGET_MODALITIES = frozenset({"TEM", "HRTEM"})\n',
)
replace_exact(
    engine,
    """    independent_segmentation_labels_available: bool\n    label_origin: str\n    labeler_count: int | None\n    immutable_sample_ids_available: bool\n""",
    """    independent_segmentation_labels_available: bool\n    label_origin: str\n    labeler_count: int | None\n    blinded_labeling_verified: bool\n    adjudicated_consensus_available: bool\n    immutable_sample_ids_available: bool\n""",
)
replace_exact(
    engine,
    '            "labeler_count",\n            "immutable_sample_ids_available",\n',
    '            "labeler_count",\n            "blinded_labeling_verified",\n            "adjudicated_consensus_available",\n            "immutable_sample_ids_available",\n',
)
replace_exact(
    engine,
    """            labeler_count=_optional_integer(payload.get("labeler_count"), "labeler_count"),\n            immutable_sample_ids_available=_boolean(\n""",
    """            labeler_count=_optional_integer(payload.get("labeler_count"), "labeler_count"),\n            blinded_labeling_verified=_boolean(\n                payload, "blinded_labeling_verified"\n            ),\n            adjudicated_consensus_available=_boolean(\n                payload, "adjudicated_consensus_available"\n            ),\n            immutable_sample_ids_available=_boolean(\n""",
)
replace_exact(
    engine,
    """        if self.independent_segmentation_labels_available and self.labeler_count is None:\n            raise CandidateContractError(\n                f"{self.candidate_id} reports labels without labeler_count"\n            )\n""",
    """        if self.independent_segmentation_labels_available and self.labeler_count is None:\n            raise CandidateContractError(\n                f"{self.candidate_id} reports labels without labeler_count"\n            )\n        if not self.independent_segmentation_labels_available and (\n            self.labeler_count not in (None, 0)\n            or self.blinded_labeling_verified\n            or self.adjudicated_consensus_available\n        ):\n            raise CandidateContractError(\n                f"{self.candidate_id} reports annotation evidence without independent labels"\n            )\n        if self.blinded_labeling_verified and (self.labeler_count or 0) < 2:\n            raise CandidateContractError(\n                f"{self.candidate_id} cannot verify blinded labeling with fewer than two labelers"\n            )\n        if self.adjudicated_consensus_available and (self.labeler_count or 0) < 2:\n            raise CandidateContractError(\n                f"{self.candidate_id} cannot report adjudication with fewer than two labelers"\n            )\n""",
)
replace_exact(
    engine,
    """        if not any(candidate.target_training_source for candidate in self.candidates):\n            raise CandidateContractError("registry must contain the target-source control")\n""",
    """        if self.target_task != SUPPORTED_TARGET_TASK:\n            raise CandidateContractError(\n                f"unsupported target task: {self.target_task!r}"\n            )\n        if self.target_material.casefold() != SUPPORTED_TARGET_MATERIAL:\n            raise CandidateContractError(\n                f"unsupported target material: {self.target_material!r}"\n            )\n        normalized_modalities = {_normalize_modality(value) for value in self.target_modalities}\n        if normalized_modalities != SUPPORTED_TARGET_MODALITIES:\n            raise CandidateContractError(\n                "target modalities must be exactly TEM and HRTEM"\n            )\n        if not any(candidate.target_training_source for candidate in self.candidates):\n            raise CandidateContractError("registry must contain the target-source control")\n""",
)
replace_exact(
    engine,
    """        counts = _counts(rows)\n        recommended = _recommendation(rows)\n        protocol = _annotation_protocol()\n        summary: dict[str, Any] = {\n""",
    """        counts = _counts(rows)\n        recommended = _recommendation(rows)\n        protocol = _annotation_protocol()\n        ready_count = counts["in_domain_external_validation_ready_count"]\n        ready_candidate_available = ready_count > 0\n        result = READY_RESULT if ready_candidate_available else RESULT\n        summary: dict[str, Any] = {\n""",
)
replace_exact(
    engine,
    """            "readiness": {\n                "status": RESULT,\n                "candidate_search_completed_for_snapshot": True,\n                "search_is_globally_exhaustive": False,\n                "independent_in_domain_external_validation_available": False,\n                "public_search_supports_model_evaluation_now": False,\n""",
    """            "readiness": {\n                "status": result,\n                "candidate_search_completed_for_snapshot": True,\n                "search_is_globally_exhaustive": False,\n                "independent_in_domain_external_validation_available": (\n                    ready_candidate_available\n                ),\n                "public_search_supports_model_evaluation_now": (\n                    ready_candidate_available\n                ),\n""",
)
replace_exact(
    engine,
    '                "result": RESULT,\n',
    '                "result": result,\n',
)
replace_exact(
    engine,
    '    has_tem_modality = any("TEM" in value.upper() for value in candidate.modalities)\n',
    '    modality_tokens = {_normalize_modality(value) for value in candidate.modalities}\n'
    '    has_tem_modality = bool(modality_tokens & SUPPORTED_TARGET_MODALITIES)\n',
)
replace_exact(
    engine,
    """    ready = all(\n        (\n            exact_target,\n            modality_available,\n            candidate.file_checksums_available,\n            candidate.independent_segmentation_labels_available,\n            candidate.immutable_sample_ids_available,\n""",
    """    annotation_contract_satisfied = all(\n        (\n            candidate.independent_segmentation_labels_available,\n            (candidate.labeler_count or 0) >= 2,\n            candidate.blinded_labeling_verified,\n            candidate.adjudicated_consensus_available,\n        )\n    )\n    ready = all(\n        (\n            exact_target,\n            modality_available,\n            candidate.file_inventory_status in _RESOLVED_INVENTORIES,\n            candidate.file_checksums_available,\n            annotation_contract_satisfied,\n            candidate.immutable_sample_ids_available,\n""",
)
replace_exact(
    engine,
    """    if not candidate.independent_segmentation_labels_available:\n        blockers.append("independent_segmentation_labels_unavailable")\n""",
    """    if not candidate.independent_segmentation_labels_available:\n        blockers.append("independent_segmentation_labels_unavailable")\n    if (candidate.labeler_count or 0) < 2:\n        blockers.append("minimum_two_independent_labelers_unavailable")\n    if not candidate.blinded_labeling_verified:\n        blockers.append("blinded_labeling_unverified")\n    if not candidate.adjudicated_consensus_available:\n        blockers.append("adjudicated_consensus_unavailable")\n""",
)
replace_exact(
    engine,
    """        "label_origin": candidate.label_origin,\n        "labeler_count": candidate.labeler_count,\n        "immutable_sample_ids_available": candidate.immutable_sample_ids_available,\n""",
    """        "label_origin": candidate.label_origin,\n        "labeler_count": candidate.labeler_count,\n        "blinded_labeling_verified": candidate.blinded_labeling_verified,\n        "adjudicated_consensus_available": (\n            candidate.adjudicated_consensus_available\n        ),\n        "immutable_sample_ids_available": candidate.immutable_sample_ids_available,\n""",
)
replace_exact(
    engine,
    """def _date(payload: Mapping[str, Any], key: str) -> str:\n""",
    """def _normalize_modality(value: str) -> str:\n    return re.sub(r"[^A-Z0-9]+", "", value.upper())\n\n\ndef _date(payload: Mapping[str, Any], key: str) -> str:\n""",
)
replace_exact(
    engine,
    '    "labeler_count",\n    "immutable_sample_ids_available",\n',
    '    "labeler_count",\n    "blinded_labeling_verified",\n    "adjudicated_consensus_available",\n    "immutable_sample_ids_available",\n',
)

# Validate the full registry payload before creating the base readiness output.
replace_exact(
    bridge,
    """    registry: Mapping[str, Any] | None = None\n    registry_record: dict[str, Any] | None = None\n    if candidate_registry_summary_path is not None:\n        registry, registry_record = _load_registry(candidate_registry_summary_path)\n\n    summary = build_tem_segmentation_readiness(\n""",
    """    registry: Mapping[str, Any] | None = None\n    registry_record: dict[str, Any] | None = None\n    registry_fields: dict[str, Any] | None = None\n    if candidate_registry_summary_path is not None:\n        registry, registry_record = _load_registry(candidate_registry_summary_path)\n        registry_fields = _validated_registry_fields(registry)\n\n    summary = build_tem_segmentation_readiness(\n""",
)
replace_exact(
    bridge,
    """    if registry is None or registry_record is None:\n        return summary\n\n    counts = _mapping(registry, "result_counts")\n    readiness = _mapping(registry, "readiness")\n    ready_count = _integer(counts, "in_domain_external_validation_ready_count")\n    search_completed = _boolean(\n        readiness, "candidate_search_completed_for_snapshot"\n    )\n    supports_evaluation = _boolean(\n        readiness, "public_search_supports_model_evaluation_now"\n    )\n    recommended_id = _text(readiness, "recommended_candidate_id")\n    recommended_status = _text(readiness, "recommended_candidate_status")\n    recommended_action = _text(readiness, "recommended_next_action")\n""",
    """    if registry is None or registry_record is None or registry_fields is None:\n        return summary\n\n    ready_count = registry_fields["ready_count"]\n    search_completed = registry_fields["search_completed"]\n    supports_evaluation = registry_fields["supports_evaluation"]\n    recommended_id = registry_fields["recommended_id"]\n    recommended_status = registry_fields["recommended_status"]\n    recommended_action = registry_fields["recommended_action"]\n""",
)
replace_exact(
    bridge,
    """def _load_registry(\n""",
    """def _validated_registry_fields(registry: Mapping[str, Any]) -> dict[str, Any]:\n    counts = _mapping(registry, "result_counts")\n    readiness = _mapping(registry, "readiness")\n    ready_count = _integer(counts, "in_domain_external_validation_ready_count")\n    if ready_count < 0:\n        raise EvidenceContractError(\n            "in_domain_external_validation_ready_count must be non-negative"\n        )\n    search_completed = _boolean(\n        readiness, "candidate_search_completed_for_snapshot"\n    )\n    supports_evaluation = _boolean(\n        readiness, "public_search_supports_model_evaluation_now"\n    )\n    independent_available = _boolean(\n        readiness, "independent_in_domain_external_validation_available"\n    )\n    if independent_available != (ready_count > 0):\n        raise EvidenceContractError(\n            "registry ready count contradicts independent availability"\n        )\n    if supports_evaluation != (ready_count > 0):\n        raise EvidenceContractError(\n            "registry ready count contradicts evaluation support"\n        )\n    return {\n        "ready_count": ready_count,\n        "search_completed": search_completed,\n        "supports_evaluation": supports_evaluation,\n        "recommended_id": _text(readiness, "recommended_candidate_id"),\n        "recommended_status": _text(readiness, "recommended_candidate_status"),\n        "recommended_action": _text(readiness, "recommended_next_action"),\n    }\n\n\ndef _load_registry(\n""",
)

# Add explicit annotation evidence fields to every pinned candidate.
config = json.loads(config_path.read_text(encoding="utf-8"))
for candidate in config["candidates"]:
    candidate["blinded_labeling_verified"] = False
    candidate["adjudicated_consensus_available"] = False
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Focused regressions.
append_registry_tests = r'''


def _ready_candidate_payload() -> dict:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidate = payload["candidates"][0].copy()
    candidate.update(
        {
            "candidate_id": "independent_ready_candidate",
            "repository": "Independent Repository",
            "doi": "10.0000/independent-ready",
            "record_url": "https://example.org/independent-ready",
            "title": "Independent cobalt oxide HRTEM validation set",
            "file_inventory_status": "exact",
            "file_checksums_available": True,
            "raw_or_lossless_tem_images_available": True,
            "reported_tem_file_count": 8,
            "independent_segmentation_labels_available": True,
            "label_origin": "two blinded experts plus adjudicated consensus",
            "labeler_count": 2,
            "blinded_labeling_verified": True,
            "adjudicated_consensus_available": True,
            "immutable_sample_ids_available": True,
            "immutable_acquisition_ids_available": True,
            "verified_not_used_for_target_training_or_model_selection": True,
            "target_creator_name_overlap": False,
            "target_training_source": False,
            "source_evidence": ["checksum-bound independent source"],
            "next_validation_step": "Run the dedicated frozen candidate audit.",
        }
    )
    payload["candidates"].append(candidate)
    return payload


def _load_payload(tmp_path: Path, payload: dict):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return load_registry_config(path)


def test_ready_candidate_requires_two_blinded_labelers_and_adjudication(
    tmp_path: Path,
) -> None:
    payload = _ready_candidate_payload()
    candidate = payload["candidates"][-1]
    candidate["labeler_count"] = 1
    candidate["blinded_labeling_verified"] = False
    candidate["adjudicated_consensus_available"] = False
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0


def test_ready_candidate_requires_resolved_file_inventory(tmp_path: Path) -> None:
    payload = _ready_candidate_payload()
    payload["candidates"][-1]["file_inventory_status"] = "unresolved"
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0
    assert summary["result_counts"]["metadata_resolution_candidate_count"] == 1


def test_ready_summary_is_derived_from_candidate_rows(tmp_path: Path) -> None:
    summary = run_candidate_registry(
        _load_payload(tmp_path, _ready_candidate_payload()), tmp_path / "out"
    )
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 1
    assert summary["readiness"]["independent_in_domain_external_validation_available"]
    assert summary["readiness"]["public_search_supports_model_evaluation_now"]
    assert summary["readiness"]["recommended_candidate_status"] == (
        "in_domain_external_validation_ready"
    )


def test_stem_only_candidate_does_not_match_tem_token(tmp_path: Path) -> None:
    payload = _ready_candidate_payload()
    payload["candidates"][-1]["modalities"] = ["STEM"]
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["result_counts"]["in_domain_external_validation_ready_count"] == 0


def test_registry_without_metadata_resolution_candidate_still_recommends(
    tmp_path: Path,
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert all(
        item["file_inventory_status"] in {"exact", "record_metadata_verified"}
        for item in payload["candidates"]
    )
    summary = run_candidate_registry(_load_payload(tmp_path, payload), tmp_path / "out")
    assert summary["readiness"]["recommended_candidate_id"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("task", "binary segmentation for gold SEM"),
        ("material", "gold"),
        ("modalities", ["SEM"]),
    ],
)
def test_unsupported_target_contract_is_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["target_contract"][field] = value
    with pytest.raises(CandidateContractError, match="unsupported target|target modalities"):
        _load_payload(tmp_path, payload)
'''
text = registry_tests.read_text(encoding="utf-8")
if "test_ready_candidate_requires_two_blinded_labelers_and_adjudication" in text:
    raise SystemExit("registry readiness tests already appended")
registry_tests.write_text(text + append_registry_tests, encoding="utf-8")

replace_exact(
    bridge_tests,
    """import json\nfrom pathlib import Path\n\nfrom mca.tem_candidate_registry_readiness import (\n""",
    """import json\nfrom pathlib import Path\n\nimport pytest\n\nfrom mca.tem_candidate_registry_readiness import (\n""",
)
replace_exact(
    bridge_tests,
    """from mca.tem_segmentation_readiness import NOT_READY\n""",
    """from mca.tem_segmentation_readiness import EvidenceContractError, NOT_READY\n""",
)
replace_exact(
    bridge_tests,
    """        "readiness": {\n            "candidate_search_completed_for_snapshot": True,\n            "public_search_supports_model_evaluation_now": False,\n""",
    """        "readiness": {\n            "candidate_search_completed_for_snapshot": True,\n            "independent_in_domain_external_validation_available": False,\n            "public_search_supports_model_evaluation_now": False,\n""",
)
append_bridge_test = r'''


def test_malformed_registry_fails_before_any_output_is_written(tmp_path: Path) -> None:
    training = _write(tmp_path / "training.json", _training())
    parent = _write(tmp_path / "parent.json", _parent())
    malformed = _registry()
    del malformed["readiness"]["recommended_next_action"]
    registry = _write(tmp_path / "registry.json", malformed)
    output = tmp_path / "out"
    with pytest.raises(EvidenceContractError, match="recommended_next_action"):
        build_tem_segmentation_readiness_with_registry(
            training_summary_path=training,
            parent_overlap_summary_path=parent,
            candidate_registry_summary_path=registry,
            output_dir=output,
        )
    assert not output.exists()
'''
text = bridge_tests.read_text(encoding="utf-8")
if "test_malformed_registry_fails_before_any_output_is_written" in text:
    raise SystemExit("bridge fail-closed test already appended")
bridge_tests.write_text(text + append_bridge_test, encoding="utf-8")

replace_exact(
    readme,
    """A candidate is not considered ready based on repository separation, author separation, or filenames alone.\n""",
    """A candidate is not considered ready based on repository separation, author separation, or filenames alone. Readiness requires an exact resolved file inventory, checksum coverage, exact TEM/HRTEM modality tokens, at least two independently blinded labelers, an adjudicated consensus, immutable sample/acquisition IDs, verified model-development non-use, verified licence, and no target-source or creator overlap. The evaluator currently supports only the pinned cobalt-oxide binary TEM/HRTEM segmentation target contract and rejects other declared targets.\n""",
)

print("Applied TEM candidate registry and readiness-bridge fixes")
