from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "verify_saed_independent_source_transfer.py"
)
SPEC = importlib.util.spec_from_file_location("saed_transfer", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _source_tree(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "source"
    (root / "patterns").mkdir(parents=True)
    first = root / "patterns" / "pattern_001.tif"
    second = root / "patterns" / "pattern_002.tif"
    first.write_bytes(b"lossless-pattern-a")
    second.write_bytes(b"raw-pattern-b")
    source_manifest = root / "source_manifest.json"
    _write_json(
        source_manifest,
        {
            "dataset_id": "saed-independent-001",
            "files": [
                {"path": "patterns/pattern_001.tif", "sha256": _sha(first)},
                {"path": "patterns/pattern_002.tif", "sha256": _sha(second)},
            ],
        },
    )
    candidate: dict[str, object] = {
        "dataset_id": "saed-independent-001",
        "dataset_version": "1.0",
        "source_type": "external_public",
        "source_url": "https://example.org/records/saed-independent-001",
        "transfer_route": "HTTPS repository file endpoint",
        "reuse_license": "CC BY 4.0",
        "reuse_authorization_basis": "Repository license record",
        "collection_manifest_sha256": _sha(source_manifest),
        "material_identity": "L-histidine hydrochloride monohydrate",
        "composition": "C6H10ClN3O2-H2O",
        "preparation_history": "Crystallized from aqueous solution",
        "acquisition_mode": "static_selected_area_diffraction",
        "accelerating_voltage_kv": 200.0,
        "detector_model": "Ceta-D",
        "detector_pixel_size_um": 14.0,
        "pattern_center_method": "Direct-beam calibration",
        "pattern_center_source": "Acquisition log and calibration image",
        "reciprocal_calibration_nm_inv_per_pixel": 0.0125,
        "reciprocal_calibration_source": "Camera-length calibration standard",
        "reference_protocol_id": "saed-reference-protocol-v1",
        "reference_type": "predeclared_reference_structures",
        "reference_identifiers": ["COD:2102215"],
        "reference_frozen_before_analyzer_execution": True,
        "analyzer_development_nonuse_attested": True,
        "patterns": [
            {
                "pattern_id": "pattern-001",
                "relative_path": "patterns/pattern_001.tif",
                "bytes": first.stat().st_size,
                "sha256": _sha(first),
                "representation": "lossless_export",
                "original_intensity_preserved": True,
                "sample_id": "sample-001",
                "sample_identity_provenance": "source_assigned",
                "acquisition_id": "acq-001",
                "acquisition_identity_provenance": "source_assigned",
                "pattern_center_x_px": 1024.5,
                "pattern_center_y_px": 1023.5,
            },
            {
                "pattern_id": "pattern-002",
                "relative_path": "patterns/pattern_002.tif",
                "bytes": second.stat().st_size,
                "sha256": _sha(second),
                "representation": "raw_detector",
                "original_intensity_preserved": True,
                "sample_id": "sample-002",
                "sample_identity_provenance": "operator_assigned_at_acquisition",
                "acquisition_id": "acq-002",
                "acquisition_identity_provenance": "operator_assigned_at_acquisition",
                "pattern_center_x_px": 1022.5,
                "pattern_center_y_px": 1025.0,
            },
        ],
    }
    return root, candidate



__all__ = ["module", "_sha", "_write_json", "_source_tree"]
