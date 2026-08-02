from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"replacement target not found: {label}")
    return text.replace(old, new, 1)


source_path = Path("src/mca/saed_bir_metadata_audit.py")
text = source_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    'RESULT = "metadata_resolved_but_source_not_ready_for_saed_evaluation"',
    'RESULT = "record_inventory_verified_but_source_not_ready_for_saed_evaluation"',
    "result constant",
)
text = replace_once(
    text,
    "        request_items = _author_request_items(config)\n        subset_plan = {",
    """        request_items = _author_request_items(
            config, rights_verified=bool(rights)
        )
        unresolved_download_gates = [
            "member count",
            "sample/acquisition lineage",
            "centre",
            "calibration",
            "analyzer-development non-use",
        ]
        if not rights:
            unresolved_download_gates.insert(-1, "reuse terms")
        unresolved_download_text = ", ".join(unresolved_download_gates)
        subset_plan = {""",
    "request and unresolved gates",
)
text = replace_once(
    text,
    """                "until member count, sample/acquisition lineage, centre, calibration, "
                "reuse terms, and analyzer-development non-use are resolved"""",
    '                f"until {unresolved_download_text} are resolved"',
    "selection basis",
)
text = replace_once(
    text,
    """                "primary_limitation": (
                    "The released MRC series are integrated and binned acquisition-derived "
                    "frames, while archive members, immutable lineage, centre, reciprocal "
                    "calibration, reuse terms, and analyzer-development non-use remain unresolved."
                ),
                "evidence_that_would_change_conclusion": (
                    "Authoritative series-to-crystal lineage, archive member inventory, "
                    "direct-beam/centre procedure, reciprocal calibration, explicit data "
                    "reuse terms, and analyzer-development non-use, followed by a checksum-bound "
                    "bounded archive audit."
                ),""",
    """                "primary_limitation": (
                    "The released MRC series are integrated and binned acquisition-derived "
                    "frames, while archive members, immutable lineage, centre, reciprocal "
                    f"calibration, {'reuse terms, ' if not rights else ''}and "
                    "analyzer-development non-use remain unresolved."
                ),
                "evidence_that_would_change_conclusion": (
                    "Authoritative series-to-crystal lineage, archive member inventory, "
                    "direct-beam/centre procedure, reciprocal calibration, "
                    f"{'explicit data reuse terms, ' if not rights else ''}and "
                    "analyzer-development non-use, followed by a checksum-bound bounded "
                    "archive audit."
                ),""",
    "scientific closeout",
)
text = replace_once(
    text,
    "def _author_request_items(config: AuditConfig) -> list[str]:\n    return [",
    """def _author_request_items(
    config: AuditConfig, *, rights_verified: bool
) -> list[str]:
    items = [""",
    "author request signature",
)
text = replace_once(
    text,
    """        "State whether the proposed series or their derived outputs were used to develop, tune, or select the current analyzer.",
        "Provide explicit data reuse terms for the Zenodo record files.",
        f"Confirm that at least {config.minimum_independent_series} proposed series represent independent acquisitions rather than exports or repeated processing of one acquisition.",
    ]""",
    """        "State whether the proposed series or their derived outputs were used to develop, tune, or select the current analyzer.",
    ]
    if not rights_verified:
        items.append("Provide explicit data reuse terms for the Zenodo record files.")
    items.append(
        f"Confirm that at least {config.minimum_independent_series} proposed series represent independent acquisitions rather than exports or repeated processing of one acquisition."
    )
    return items""",
    "author request body",
)
text = replace_once(
    text,
    '            "- Reason: smallest checksum-bound archive, but member inventory, lineage, centre, calibration, reuse, and non-use remain unresolved.",',
    """            (
                "- Reason: smallest checksum-bound archive, but member inventory, "
                "lineage, centre, calibration, "
                f"{'reuse, ' if not source['rights'] else ''}and non-use remain unresolved."
            ),""",
    "report reason",
)
source_path.write_text(text, encoding="utf-8")


test_path = Path("tests/test_saed_bir_metadata_audit.py")
text = test_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    """    assert summary["evidence_gates"]["explicit_reuse_terms_verified"]
    assert not summary["evidence_gates"]["ready_for_bounded_archive_download"]
    assert "pattern_center_not_traceable" in summary["blockers"]
    assert "reciprocal_calibration_not_traceable" in summary["blockers"]
""",
    """    assert summary["evidence_gates"]["explicit_reuse_terms_verified"]
    assert not summary["evidence_gates"]["ready_for_bounded_archive_download"]
    assert "pattern_center_not_traceable" in summary["blockers"]
    assert "reciprocal_calibration_not_traceable" in summary["blockers"]
    assert "reuse terms" not in summary["scientific_closeout"]["primary_limitation"]
    request = (tmp_path / "out" / "bir_author_metadata_request.md").read_text(
        encoding="utf-8"
    )
    assert "Provide explicit data reuse terms" not in request
    plan = json.loads(
        (tmp_path / "out" / "bir_bounded_subset_plan.json").read_text(
            encoding="utf-8"
        )
    )
    assert "reuse terms" not in plan["selection_basis"]
""",
    "rights regression",
)
test_path.write_text(text, encoding="utf-8")


workflow_path = Path(".github/workflows/saed-bir-200kev-metadata-audit.yml")
text = workflow_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "metadata_resolved_but_source_not_ready_for_saed_evaluation",
    "record_inventory_verified_but_source_not_ready_for_saed_evaluation",
    "workflow result",
)
workflow_path.write_text(text, encoding="utf-8")


readme_path = Path("case_studies/saed_bir_200kev_metadata_audit/README.md")
text = readme_path.read_text(encoding="utf-8")
text = text.replace("- explicit reuse terms for the record files;\n", "")
text = replace_once(
    text,
    "The candidate remains **not ready** for bounded archive download or SAED validation intake.\n",
    "The candidate remains **not ready** for bounded archive download or SAED validation intake. The live record explicitly declares `CC BY 4.0`, so reuse authorization is supported and is no longer a blocker.\n",
    "README rights status",
)
readme_path.write_text(text, encoding="utf-8")
