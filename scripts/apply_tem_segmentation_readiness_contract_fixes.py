from __future__ import annotations

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


source = Path("src/mca/tem_segmentation_readiness.py")
tests = Path("tests/test_tem_segmentation_readiness.py")
readme = Path("case_studies/tem_segmentation_readiness/README.md")

replace_exact(
    source,
    """CROSS_MATERIAL_READY = (\n    \"diagnostic_cross_material_stress_test_ready_not_in_domain_validation\"\n)\n""",
    """CROSS_MATERIAL_READY = (\n    \"ready_to_freeze_diagnostic_cross_material_stress_test_protocol\"\n)\n""",
)
replace_exact(
    source,
    """    output = _prepare_output(output_dir)\n    try:\n""",
    """    output, output_created_by_call = _prepare_output(output_dir)\n    try:\n""",
)
replace_exact(
    source,
    """        summary: dict[str, Any] = {\n""",
    """        training_patch_count = _integer(\n            _mapping(training, \"result_counts\"), \"patch_pair_count\"\n        )\n        summary: dict[str, Any] = {\n""",
)
old_closeout = '''            "scientific_closeout": {
                "status": "Supported",
                "result": decision["status"],
                "strongest_evidence": (
                    "The checksum-bound training audit validates 256 paired patches but "
                    "shows that every source-notebook validation fold contains all four "
                    "reconstructed candidate parents in both training and validation. The "
                    "parent-overlap audit reports no independent labeled in-domain external "
                    "validation candidate."
                ),
                "primary_limitation": (
                    "No immutable authoritative training patch-to-parent map and no "
                    "predeclared parent-disjoint cobalt-oxide validation set with independent "
                    "labels are available."
                ),
                "evidence_that_would_change_conclusion": (
                    "A checksum-bound cobalt-oxide validation set with immutable sample and "
                    "acquisition lineage, independent expert labels, documented non-use in "
                    "training or model selection, and a frozen evaluation protocol."
                ),
                "suitable_for": [
                    "deciding whether software-only training experiments may proceed",
                    "blocking unsupported segmentation performance claims",
                    "prioritizing the next evidence acquisition step",
                ],
                "not_suitable_for": [
                    "estimating segmentation accuracy",
                    "selecting a production model",
                    "nanometre-scale physical measurement",
                    "causal or mechanistic interpretation",
                    "engineering release",
                ],
            },
'''
replace_exact(
    source,
    old_closeout,
    '''            "scientific_closeout": _scientific_closeout(
                decision=decision,
                gates=gates,
                training_patch_count=training_patch_count,
            ),
''',
)
replace_exact(
    source,
    """    except Exception:\n        if output.exists() and not any(output.iterdir()):\n            output.rmdir()\n        raise\n""",
    """    except Exception:\n        if output_created_by_call and output.exists() and not any(output.iterdir()):\n            output.rmdir()\n        raise\n""",
)
replace_exact(
    source,
    """    values = _mapping(training, \"value_contract\")\n""",
    """    training_sha256 = _training_images_sha256(\n        training, role=\"training_data_audit\"\n    )\n    parent_training_sha256 = _training_images_sha256(\n        parent, role=\"training_parent_overlap_audit\"\n    )\n    if training_sha256 != parent_training_sha256:\n        raise EvidenceContractError(\n            \"training and parent-overlap summaries reference different training images\"\n        )\n\n    values = _mapping(training, \"value_contract\")\n""",
)
replace_exact(
    source,
    """    cross_material_ready = (\n        pilot_summary is not None\n        and pilot_hdf5_complete\n        and pilot_overlap_complete\n        and pilot_overlap_gate_passed\n    )\n""",
    """    cross_material_protocol_freeze_ready = (\n        training_integrity\n        and pilot_summary is not None\n        and pilot_hdf5_complete\n        and pilot_overlap_complete\n        and pilot_overlap_gate_passed\n    )\n""",
)
replace_exact(
    source,
    """        \"training_pair_integrity_validated\": training_integrity,\n""",
    """        \"training_pair_integrity_validated\": training_integrity,\n        \"training_artifact_identity_bound_across_audits\": True,\n        \"training_images_sha256\": training_sha256,\n""",
)
replace_exact(
    source,
    """        \"diagnostic_cross_material_stress_test_ready\": cross_material_ready,\n        \"scientific_in_domain_evaluation_ready\": scientific_evaluation_ready,\n""",
    """        \"diagnostic_cross_material_protocol_freeze_ready\": (\n            cross_material_protocol_freeze_ready\n        ),\n        \"diagnostic_cross_material_stress_test_ready\": False,\n        \"in_domain_protocol_freeze_ready\": scientific_evaluation_ready,\n        \"scientific_in_domain_evaluation_ready\": False,\n""",
)
replace_exact(
    source,
    """    in_domain_ready = bool(gates[\"scientific_in_domain_evaluation_ready\"])\n    cross_material_ready = bool(\n        gates[\"diagnostic_cross_material_stress_test_ready\"]\n    )\n""",
    """    in_domain_protocol_ready = bool(gates[\"in_domain_protocol_freeze_ready\"])\n    cross_material_protocol_ready = bool(\n        gates[\"diagnostic_cross_material_protocol_freeze_ready\"]\n    )\n""",
)
replace_exact(
    source,
    """    elif in_domain_ready:\n""",
    """    elif in_domain_protocol_ready:\n""",
)
replace_exact(
    source,
    """    elif cross_material_ready:\n        status = CROSS_MATERIAL_READY\n        next_action = (\n            \"Run only the predeclared cross-material diagnostic stress test while \"\n            \"continuing to seek an independent in-domain cobalt-oxide validation set.\"\n        )\n""",
    """    elif cross_material_protocol_ready:\n        status = CROSS_MATERIAL_READY\n        next_action = (\n            \"Freeze the diagnostic cross-material metrics, exclusions, uncertainty \"\n            \"method, model version, and untouched evaluation manifest before any \"\n            \"pilot inference, while continuing to seek an independent in-domain set.\"\n        )\n""",
)
replace_exact(
    source,
    """        \"scientific_in_domain_performance_evaluation_ready\": in_domain_ready,\n        \"independent_performance_claim_ready\": in_domain_ready,\n        \"diagnostic_cross_material_stress_test_ready\": cross_material_ready,\n""",
    """        \"predeclared_in_domain_protocol_freeze_ready\": (\n            in_domain_protocol_ready\n        ),\n        \"scientific_in_domain_performance_evaluation_ready\": False,\n        \"independent_performance_claim_ready\": False,\n        \"diagnostic_cross_material_protocol_freeze_ready\": (\n            cross_material_protocol_ready\n        ),\n        \"diagnostic_cross_material_stress_test_ready\": False,\n""",
)
replace_exact(
    source,
    """def _load_evidence(\n""",
    '''def _scientific_closeout(
    *,
    decision: Mapping[str, Any],
    gates: Mapping[str, Any],
    training_patch_count: int,
) -> dict[str, Any]:
    if not bool(gates["training_pair_integrity_validated"]):
        status = "Unsupported"
        strongest = (
            f"The supplied training audit covers {training_patch_count} paired patches, "
            "but one or more required finite/binary/complementary-label integrity gates fail."
        )
        limitation = (
            "Training image-label integrity is unresolved, so neither training nor any "
            "downstream in-domain or cross-material model test is supportable."
        )
    elif bool(gates["in_domain_protocol_freeze_ready"]):
        status = "Supported"
        strongest = (
            f"Training integrity is validated for {training_patch_count} paired patches, "
            "the parent/acquisition independence gate passes, and an independent in-domain "
            "candidate satisfies the supplied lineage and non-use gates."
        )
        limitation = (
            "The evaluation protocol has not yet been frozen or executed; no inference, "
            "segmentation metrics, uncertainty interval, or performance claim exists."
        )
    elif bool(gates["diagnostic_cross_material_protocol_freeze_ready"]):
        status = "Diagnostic"
        strongest = (
            f"Training integrity is validated for {training_patch_count} paired patches and "
            "the cross-material pilot HDF5/content-overlap gate passes."
        )
        limitation = (
            "The pilot is cross-material and its diagnostic protocol has not yet been frozen; "
            "it cannot establish cobalt-oxide in-domain performance."
        )
    else:
        status = "Supported"
        strongest = (
            f"The checksum-bound training audit validates integrity for {training_patch_count} "
            "paired patches, while the supplied evidence does not establish a usable "
            "independent in-domain external-validation set."
        )
        limitation = (
            "No immutable authoritative training patch-to-parent map and no predeclared "
            "parent-disjoint cobalt-oxide validation set with independent labels are available."
        )
    return {
        "status": status,
        "result": decision["status"],
        "strongest_evidence": strongest,
        "primary_limitation": limitation,
        "evidence_that_would_change_conclusion": (
            "A checksum-bound cobalt-oxide validation set with immutable sample/acquisition "
            "lineage, independent blinded expert labels and adjudication, documented non-use "
            "in model development, a frozen protocol, and the later one-time metric results."
        ),
        "suitable_for": [
            "deciding whether software-only training experiments may proceed",
            "blocking unsupported segmentation performance claims",
            "prioritizing the next evidence acquisition or protocol-freeze step",
        ],
        "not_suitable_for": [
            "estimating segmentation accuracy before evaluation results exist",
            "selecting a production model",
            "nanometre-scale physical measurement",
            "causal or mechanistic interpretation",
            "engineering release",
        ],
    }


def _training_images_sha256(
    payload: Mapping[str, Any], *, role: str
) -> str:
    source = _mapping(payload, "source")
    training_images = _mapping(source, "training_images")
    digest = _text(training_images, "sha256").lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise EvidenceContractError(f"{role} training_images.sha256 is invalid")
    return digest


def _load_evidence(
''',
)
replace_exact(
    source,
    """def _prepare_output(path: str | Path) -> Path:\n    output = Path(path)\n    if output.exists():\n        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):\n            raise FileExistsError(\"output directory must be absent or empty.\")\n    else:\n        output.mkdir(parents=True)\n    return output\n""",
    """def _prepare_output(path: str | Path) -> tuple[Path, bool]:\n    output = Path(path)\n    created_by_call = False\n    if output.exists():\n        if output.is_symlink() or not output.is_dir() or any(output.iterdir()):\n            raise FileExistsError(\"output directory must be absent or empty.\")\n    else:\n        output.mkdir(parents=True)\n        created_by_call = True\n    return output, created_by_call\n""",
)

# Bind both test fixtures to the same training artifact identity.
replace_exact(
    tests,
    '        "software_version": "0.9.3",\n        "value_contract": {\n',
    '        "software_version": "0.9.3",\n        "source": {"training_images": {"sha256": "a" * 64}},\n        "value_contract": {\n',
)
replace_exact(
    tests,
    '        "software_version": "0.9.3",\n        "external_validation_readiness": {\n',
    '        "software_version": "0.9.3",\n        "source": {"training_images": {"sha256": "a" * 64}},\n        "external_validation_readiness": {\n',
)
replace_exact(
    tests,
    """    assert summary[\"decision\"][\"diagnostic_cross_material_stress_test_ready\"]\n""",
    """    assert summary[\"decision\"][\"diagnostic_cross_material_protocol_freeze_ready\"]\n    assert not summary[\"decision\"][\"diagnostic_cross_material_stress_test_ready\"]\n    assert \"Freeze the diagnostic cross-material metrics\" in summary[\"decision\"][\"next_action\"]\n""",
)
append_tests = r'''


def test_cross_material_protocol_is_blocked_by_training_integrity_failure(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path, integrity=False)
    pilot_summary = _write(tmp_path / "pilot-summary.json", _pilot_summary())
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        pilot_summary_path=pilot_summary,
        output_dir=tmp_path / "out",
    )
    assert summary["decision"]["status"] == TRAINING_BLOCKED
    assert not summary["decision"][
        "diagnostic_cross_material_protocol_freeze_ready"
    ]
    assert not summary["decision"]["diagnostic_cross_material_stress_test_ready"]


def test_training_artifact_mismatch_fails_closed(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    parent = json.loads(paths["parent"].read_text(encoding="utf-8"))
    parent["source"]["training_images"]["sha256"] = "b" * 64
    _write(paths["parent"], parent)
    with pytest.raises(EvidenceContractError, match="different training images"):
        build_tem_segmentation_readiness(
            training_summary_path=paths["training"],
            parent_overlap_summary_path=paths["parent"],
            output_dir=tmp_path / "out",
        )


def test_existing_empty_output_directory_is_preserved_on_failure(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    parent = json.loads(paths["parent"].read_text(encoding="utf-8"))
    parent["source"]["training_images"]["sha256"] = "b" * 64
    _write(paths["parent"], parent)
    output = tmp_path / "caller-owned-empty"
    output.mkdir()
    with pytest.raises(EvidenceContractError):
        build_tem_segmentation_readiness(
            training_summary_path=paths["training"],
            parent_overlap_summary_path=paths["parent"],
            output_dir=output,
        )
    assert output.is_dir()
    assert not list(output.iterdir())


def test_protocol_ready_never_authorizes_performance_claim(tmp_path: Path) -> None:
    training = _training()
    training["candidate_parent_grouping"]["authoritative_parent_ids_available"] = True
    training["notebook_split_audit"]["independent_parent_image_validation"] = True
    parent = _parent_overlap()
    candidate = _external_candidate()
    candidate["result_counts"][
        "independent_in_domain_external_validation_pair_count"
    ] = 2
    gates = candidate["target_comparison"]["gates"]
    gates["target_material_match"] = True
    gates["immutable_cross_dataset_lineage_manifest_available"] = True
    gates["verified_not_used_for_target_model_training"] = True
    gates["creator_overlap_with_target_dataset"] = False
    gates["multi_labeler_or_adjudication_evidence_available"] = True
    candidate["readiness"]["model_evaluation_allowed_now"] = True
    summary = build_tem_segmentation_readiness(
        training_summary_path=_write(tmp_path / "training.json", training),
        parent_overlap_summary_path=_write(tmp_path / "parent.json", parent),
        external_candidate_summary_path=_write(tmp_path / "candidate.json", candidate),
        output_dir=tmp_path / "out",
    )
    decision = summary["decision"]
    assert decision["status"] == (
        "ready_to_freeze_predeclared_in_domain_evaluation_protocol"
    )
    assert decision["predeclared_in_domain_protocol_freeze_ready"]
    assert not decision["scientific_in_domain_performance_evaluation_ready"]
    assert not decision["independent_performance_claim_ready"]
    assert "not yet been frozen or executed" in summary["scientific_closeout"][
        "primary_limitation"
    ]


def test_training_failure_closeout_does_not_claim_validated_pairs(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path, integrity=False)
    summary = build_tem_segmentation_readiness(
        training_summary_path=paths["training"],
        parent_overlap_summary_path=paths["parent"],
        output_dir=tmp_path / "out",
    )
    closeout = summary["scientific_closeout"]
    assert closeout["status"] == "Unsupported"
    assert "integrity gates fail" in closeout["strongest_evidence"]
'''
text = tests.read_text(encoding="utf-8")
if "test_training_artifact_mismatch_fails_closed" in text:
    raise SystemExit("readiness contract tests already appended")
tests.write_text(text + append_tests, encoding="utf-8")

replace_exact(
    readme,
    """The command is intentionally fail-closed. Missing optional evidence remains unresolved, and a cross-material diagnostic never becomes cobalt-oxide in-domain validation.\n""",
    """The command is intentionally fail-closed. Missing optional evidence remains unresolved, and a cross-material diagnostic never becomes cobalt-oxide in-domain validation. Training and parent-overlap summaries must bind the same `source.training_images.sha256`. Passing candidate or pilot gates permits only protocol freeze; model inference, metric reporting, and independent performance claims remain blocked until later execution evidence exists.\n""",
)

print("Applied TEM segmentation readiness contract fixes")
