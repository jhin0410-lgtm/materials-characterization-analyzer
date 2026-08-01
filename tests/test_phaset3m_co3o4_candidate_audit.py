from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pytest

import mca.phaset3m_candidate_audit as phaset3m_audit
from mca.phaset3m_candidate_audit import (
    CASE_ID,
    RESULT,
    PhaseT3MContractError,
    audit_phaset3m_candidate,
    load_config,
)


def _archive(
    tmp_path: Path,
    *,
    member: str = "Raw_tilt_data/Co3O4/Co3O4_denoised_tilt_series.h5",
    duplicate_target: bool = False,
    traversal: bool = False,
) -> Path:
    h5_path = tmp_path / "source.h5"
    with h5py.File(h5_path, "w") as handle:
        dataset = handle.create_dataset(
            "tilt_series", data=np.arange(60, dtype=np.float32).reshape(3, 4, 5)
        )
        dataset.attrs["pixel_size_angstrom"] = 0.8
        handle.attrs["material"] = "Co3O4"
    archive = tmp_path / "raw_tilt_data.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(h5_path, "../escape.h5" if traversal else member)
        if duplicate_target:
            bundle.write(h5_path, "other/Co3O4_denoised_tilt_series.h5")
    return archive


def _config(
    tmp_path: Path,
    archive: Path,
    *,
    archive_md5: str | None = None,
) -> Path:
    payload = {
        "case_id": CASE_ID,
        "source": {
            "record_id": 17336678,
            "doi": "10.5281/zenodo.17336678",
            "record_url": "https://zenodo.org/records/17336678",
            "title": "PhaseT3M",
            "archive_name": "raw_tilt_data.zip",
            "archive_md5": archive_md5
            or hashlib.md5(archive.read_bytes(), usedforsecurity=False).hexdigest(),
            "target_member_basename": "Co3O4_denoised_tilt_series.h5",
            "source_material": "Co3O4",
            "source_particle_count": 1,
            "source_processing": [
                "motion_corrected",
                "tilt_aligned",
                "denoised",
            ],
            "target_training_creator_overlap": True,
            "reuse_license": "not explicitly declared for data",
            "reuse_license_verified": False,
        },
        "scientific_contract": {
            "minimum_independent_samples": 2,
            "minimum_independent_acquisitions": 2,
            "raw_or_demonstrably_lossless_required": True,
            "independent_labels_required": True,
        },
        "archive_safety": {
            "max_member_count": 100,
            "max_single_member_bytes": 10_000_000,
            "max_total_uncompressed_bytes": 20_000_000,
            "max_compression_ratio": 1000.0,
        },
        "inspection": {"max_sample_values_per_dataset": 1000},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_checksum_bound_hdf5_audit_is_diagnostic_only(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    summary = audit_phaset3m_candidate(
        load_config(_config(tmp_path, archive)), archive, tmp_path / "out"
    )
    assert summary["scientific_closeout"]["result"] == RESULT
    assert summary["hdf5_audit"]["dataset_count"] == 1
    assert summary["hdf5_audit"]["datasets"][0]["shape"] == [3, 4, 5]
    assert not summary["scientific_gates"]["ready_for_blinded_annotation_pilot"]
    assert not summary["scientific_gates"][
        "ready_for_predeclared_external_evaluation"
    ]
    output = tmp_path / "out"
    assert not list(output.glob("*.h5"))
    assert not list(output.glob("*.zip"))
    manifest = json.loads(
        (output / "phaset3m_candidate_audit_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["artifact_count"] == 4
    assert not manifest["raw_source_files_included"]


def test_archive_checksum_mismatch_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    config = load_config(_config(tmp_path, archive, archive_md5="0" * 32))
    with pytest.raises(PhaseT3MContractError, match="MD5 mismatch"):
        audit_phaset3m_candidate(config, archive, tmp_path / "out")


def test_archive_path_traversal_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path, traversal=True)
    with pytest.raises(PhaseT3MContractError, match="unsafe ZIP member path"):
        audit_phaset3m_candidate(
            load_config(_config(tmp_path, archive)), archive, tmp_path / "out"
        )


def test_duplicate_target_member_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path, duplicate_target=True)
    with pytest.raises(PhaseT3MContractError, match="exactly one target HDF5"):
        audit_phaset3m_candidate(
            load_config(_config(tmp_path, archive)), archive, tmp_path / "out"
        )


def test_unknown_config_key_fails_closed(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    config_path = _config(tmp_path, archive)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["source"]["invented"] = True
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PhaseT3MContractError, match="unknown source keys"):
        load_config(config_path)


def test_late_failure_removes_partial_created_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    output = tmp_path / "created-output"

    def fail_after_inventory(*args, **kwargs):
        raise RuntimeError("late evidence write failure")

    monkeypatch.setattr(phaset3m_audit, "_write_json", fail_after_inventory)
    with pytest.raises(RuntimeError, match="late evidence write failure"):
        audit_phaset3m_candidate(
            load_config(_config(tmp_path, archive)), archive, output
        )
    assert not output.exists()


def test_late_failure_cleans_but_preserves_caller_output_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(tmp_path)
    output = tmp_path / "caller-output"
    output.mkdir()

    def fail_after_inventory(*args, **kwargs):
        raise RuntimeError("late evidence write failure")

    monkeypatch.setattr(phaset3m_audit, "_write_json", fail_after_inventory)
    with pytest.raises(RuntimeError, match="late evidence write failure"):
        audit_phaset3m_candidate(
            load_config(_config(tmp_path, archive)), archive, output
        )
    assert output.is_dir()
    assert not any(output.iterdir())


def test_nonempty_output_is_not_overwritten(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="absent or empty"):
        audit_phaset3m_candidate(
            load_config(_config(tmp_path, archive)), archive, output
        )
    assert (output / "existing.txt").read_text(encoding="utf-8") == "keep"
