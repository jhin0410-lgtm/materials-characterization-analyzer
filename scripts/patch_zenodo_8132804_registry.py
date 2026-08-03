from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "case_studies/tem_external_validation_candidate_registry/case_config.json"
README = ROOT / "case_studies/tem_external_validation_candidate_registry/README.md"
TEST = ROOT / "tests/test_tem_external_validation_candidate_registry.py"
COLLATERAL = ROOT / "scripts/audit_co3o4_public_tem_candidates.py"
CANDIDATE_ID = "zenodo_8132804_co3o4_mn3o4_stem_tomography"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one replacement in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    candidates = payload["candidates"]
    if len(candidates) != 10:
        raise RuntimeError(f"expected 10 candidates before patch, found {len(candidates)}")
    if any(item["candidate_id"] == CANDIDATE_ID for item in candidates):
        raise RuntimeError("Zenodo 8132804 candidate already exists")
    candidates.append(
        {
            "candidate_id": CANDIDATE_ID,
            "repository": "Zenodo",
            "doi": "10.5281/zenodo.8132804",
            "record_url": "https://zenodo.org/records/8132804",
            "title": "Imaging 3D Chemistry at 1 nm Resolution with Fused Multi-Modal Electron Tomography",
            "materials": ["Co3O4-Mn3O4 core-shell nanocrystal"],
            "modalities": ["HAADF-STEM tomography", "EELS tomography"],
            "file_inventory_status": "exact",
            "file_checksums_available": True,
            "raw_or_lossless_tem_images_available": False,
            "reported_tem_file_count": 0,
            "independent_segmentation_labels_available": False,
            "label_origin": "none",
            "labeler_count": 0,
            "blinded_labeling_verified": False,
            "adjudicated_consensus_available": False,
            "immutable_sample_ids_available": False,
            "immutable_acquisition_ids_available": False,
            "verified_not_used_for_target_training_or_model_selection": False,
            "target_creator_name_overlap": True,
            "target_material_relation": "heterojunction_contains_cobalt_oxide",
            "imaging_domain_relation": "material_or_acquisition_domain_shift",
            "reuse_license": "CC-BY-4.0",
            "reuse_license_verified": True,
            "target_training_source": False,
            "source_evidence": [
                "Zenodo record 8132804 version 0.1 exposes one 1,183,315,114-byte archive with MD5 cb249cc2893428aa20c9b487918c0d5f under CC BY 4.0.",
                "Bounded HTTP Range audit verified the 71-member ZIP inventory without downloading the full archive.",
                "Exp_1_coarse_tilt_series.h5 and raw_tilt_series.h5 were verified by ZIP CRC32 and uncompressed SHA-256.",
                "The raw HDF5 contains 400 x 400 x 31 HAADF-STEM and 400 x 400 x 9 EELS tilt-series arrays, all float32.",
                "The source is a mixed Co3O4-Mn3O4 core-shell specimen acquired by HAADF-STEM/EELS, not target TEM/HRTEM.",
                "Only source-assigned Exp_1 is represented; embedded sample IDs, acquisition IDs, pixel calibration, detector provenance, and segmentation labels are absent.",
                "Mary Scott overlaps the target training-source creator set, and target-model non-use is unverified."
            ],
            "next_validation_step": "Exclude from target TEM/HRTEM segmentation validation. Use only for bounded HDF5 ingestion or cross-modality tomography diagnostics; continue searching for an independent pure-cobalt-oxide TEM/HRTEM cohort with at least two samples and acquisitions."
        }
    )
    terms = payload["search_snapshot"]["search_terms"]
    term = "Co3O4 Mn3O4 HAADF STEM EELS tomography raw tilt series HDF5"
    if term not in terms:
        terms.append(term)
    CONFIG.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    bullet = (
        "- Zenodo `10.5281/zenodo.8132804`: checksum-bound raw/coarse HDF5 arrays from one "
        "Co3O4-Mn3O4 `Exp_1`; real HAADF-STEM/EELS tomography, but mixed-material, wrong "
        "target modality, single-experiment, unlabeled, and without embedded lineage or calibration.\n"
    )
    marker = "- RepOD `10.18150/SAU9QX`: exact-material Co3O4 TEM content is deposited only inside two checksum-bound multi-panel RGB JPEG publication figures; no individual raw/lossless TEM micrographs.\n"
    readme = README.read_text(encoding="utf-8")
    if readme.count(marker) != 1 or bullet in readme:
        raise RuntimeError("registry README insertion point changed")
    README.write_text(readme.replace(marker, marker + bullet), encoding="utf-8")

    replace_once(TEST, '"candidate_count": 10,', '"candidate_count": 11,')
    replace_once(TEST, '"excluded_control_count": 5,', '"excluded_control_count": 6,')
    replace_once(TEST, 'assert printed["candidate_count"] == 10', 'assert printed["candidate_count"] == 11')
    insertion = '''\n\ndef test_zenodo_8132804_raw_stem_arrays_are_wrong_target_modality(\n    tmp_path: Path,\n) -> None:\n    output = tmp_path / "out"\n    run_candidate_registry(load_registry_config(CONFIG), output)\n    with (output / "tem_external_validation_candidate_inventory.csv").open(\n        encoding="utf-8", newline=""\n    ) as handle:\n        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}\n    candidate = rows["zenodo_8132804_co3o4_mn3o4_stem_tomography"]\n    assert candidate["candidate_status"] == WRONG_MODALITY\n    assert candidate["target_material_relation"] == "heterojunction_contains_cobalt_oxide"\n    assert candidate["modalities"] == "HAADF-STEM tomography | EELS tomography"\n    assert candidate["reported_tem_file_count"] == "0"\n    assert candidate["raw_or_lossless_tem_images_available"] == "False"\n    assert "target_material_mismatch" not in candidate["blockers"]\n    assert "raw_or_lossless_tem_images_unavailable" in candidate["blockers"]\n    assert "immutable_sample_ids_unavailable" in candidate["blockers"]\n    assert "target_creator_overlap" in candidate["blockers"]\n    assert "400 x 400 x 31 HAADF-STEM" in candidate["source_evidence"]\n    assert "Exp_1" in candidate["source_evidence"]\n    assert candidate["evaluation_ready"] == "False"\n'''
    test_text = TEST.read_text(encoding="utf-8")
    anchor = "\n\ndef test_phaset3m_processed_exact_material_is_diagnostic_only("
    if test_text.count(anchor) != 1 or "test_zenodo_8132804_raw_stem_arrays" in test_text:
        raise RuntimeError("registry test insertion point changed")
    TEST.write_text(test_text.replace(anchor, insertion + anchor), encoding="utf-8")

    replace_once(COLLATERAL, 'counts["candidate_count"] != 10', 'counts["candidate_count"] != 11')
    replace_once(COLLATERAL, 'counts["excluded_control_count"] != 5', 'counts["excluded_control_count"] != 6')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
