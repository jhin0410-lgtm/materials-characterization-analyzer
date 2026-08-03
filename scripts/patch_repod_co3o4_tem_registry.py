from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(".")
CONFIG = ROOT / "case_studies" / "tem_external_validation_candidate_registry" / "case_config.json"
README = ROOT / "case_studies" / "tem_external_validation_candidate_registry" / "README.md"
TESTS = ROOT / "tests" / "test_tem_external_validation_candidate_registry.py"

payload = json.loads(CONFIG.read_text(encoding="utf-8"))
if "RepOD" not in payload["search_snapshot"]["repositories_searched"]:
    payload["search_snapshot"]["repositories_searched"].append("RepOD")
term = "Hierarchical Co3O4 anode TEM raw micrographs RepOD"
if term not in payload["search_snapshot"]["search_terms"]:
    payload["search_snapshot"]["search_terms"].append(term)

candidate = {
    "candidate_id": "repod_sau9qx_co3o4_rendered_tem_figures",
    "repository": "RepOD",
    "doi": "10.18150/SAU9QX",
    "record_url": "https://repod.icm.edu.pl/dataset.xhtml?persistentId=doi:10.18150/SAU9QX",
    "title": "Hierarchical Co3O4 anode for high-performance Na-ion battery",
    "materials": ["Co3O4 nanosheets", "Co3O4 nanoparticles"],
    "modalities": ["TEM", "SEM", "Raman", "ToF-SIMS", "electrochemistry"],
    "file_inventory_status": "exact",
    "file_checksums_available": True,
    "raw_or_lossless_tem_images_available": False,
    "reported_tem_file_count": 2,
    "independent_segmentation_labels_available": False,
    "label_origin": "no segmentation labels; TEM content is embedded in composite publication JPEG figures",
    "labeler_count": None,
    "immutable_sample_ids_available": False,
    "immutable_acquisition_ids_available": False,
    "verified_not_used_for_target_training_or_model_selection": False,
    "target_creator_name_overlap": False,
    "target_material_relation": "exact_cobalt_oxide",
    "imaging_domain_relation": "rendered_multi_panel_publication_figures",
    "reuse_license": "CC0-1.0",
    "reuse_license_verified": True,
    "target_training_source": False,
    "source_evidence": [
        "Official RepOD Dataverse version 1.0 exposes exactly six public image/jpeg files with immutable data-file IDs, byte counts and MD5 values; every file declares CC0 Creative Commons Zero 1.0 Waiver.",
        "Figure_2.jpg is checksum-bound at 496538 bytes with MD5 f2dbf4eae85e7e2546526bda8bd0b69f and decodes as a single-frame 1430 x 1117 RGB JPEG. Its official description combines SEM panels (a-c), TEM panels (d-f), and SEM panels (g-i).",
        "Figure_6.jpg is checksum-bound at 111955 bytes with MD5 c5d0534d273fbe248c7f886dd331e307 and decodes as a single-frame 925 x 614 RGB JPEG. Its official description combines Nyquist, ToF-SIMS, one TEM panel, and elemental-map panels.",
        "No individual TEM micrograph, detector file, demonstrably lossless image, pixel calibration, immutable acquisition ID or independent segmentation label is deposited."
    ],
    "next_validation_step": "Exclude the deposited publication figures from segmentation validation. Request checksum-bound individual TEM micrographs or detector files with pixel calibration, sample/acquisition lineage, independent labels and target-model non-use evidence.",
    "blinded_labeling_verified": False,
    "adjudicated_consensus_available": False
}
if not any(item["candidate_id"] == candidate["candidate_id"] for item in payload["candidates"]):
    payload["candidates"].append(candidate)
CONFIG.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

readme = README.read_text(encoding="utf-8")
anchor = "- Mendeley Data `10.17632/kkk76z8g8z.1`: two directly verified version-1 snapshots had different SHA-256 values and different SEM member paths; both contained 760 members, only three SEM PNG images, and no deposited TEM/HRTEM/STEM files.\n"
addition = anchor + "- RepOD `10.18150/SAU9QX`: exact-material Co3O4 TEM content is deposited only inside two checksum-bound multi-panel RGB JPEG publication figures; no individual raw/lossless TEM micrographs.\n"
if "RepOD `10.18150/SAU9QX`" not in readme:
    if anchor not in readme:
        raise SystemExit("registry README anchor not found")
    readme = readme.replace(anchor, addition, 1)
README.write_text(readme, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
tests = tests.replace('"candidate_count": 9,', '"candidate_count": 10,', 1)
tests = tests.replace(
    '"rendered_representation_exclusion_count": 1,',
    '"rendered_representation_exclusion_count": 2,',
    1,
)
tests = tests.replace(
    'assert printed["candidate_count"] == 9',
    'assert printed["candidate_count"] == 10',
    1,
)
marker = "\n\ndef test_new_co3o4_public_records_are_wrong_modality_exclusions(\n"
new_test = '''\n\ndef test_repod_exact_material_figures_are_rendered_representation_exclusion(\n    tmp_path: Path,\n) -> None:\n    output = tmp_path / "out"\n    run_candidate_registry(load_registry_config(CONFIG), output)\n    with (output / "tem_external_validation_candidate_inventory.csv").open(\n        encoding="utf-8", newline=""\n    ) as handle:\n        rows = {row["candidate_id"]: row for row in csv.DictReader(handle)}\n    candidate = rows["repod_sau9qx_co3o4_rendered_tem_figures"]\n    assert candidate["candidate_status"] == EXCLUDED_REPRESENTATION\n    assert candidate["reported_tem_file_count"] == "2"\n    assert candidate["raw_or_lossless_tem_images_available"] == "False"\n    assert candidate["target_material_relation"] == "exact_cobalt_oxide"\n    assert "f2dbf4eae85e7e2546526bda8bd0b69f" in candidate["source_evidence"]\n    assert "c5d0534d273fbe248c7f886dd331e307" in candidate["source_evidence"]\n    assert "multi-panel" in candidate["source_evidence"]\n    assert candidate["evaluation_ready"] == "False"\n\n'''
if "test_repod_exact_material_figures_are_rendered_representation_exclusion" not in tests:
    if marker not in tests:
        raise SystemExit("registry test insertion anchor not found")
    tests = tests.replace(marker, new_test + marker, 1)
TESTS.write_text(tests, encoding="utf-8")
