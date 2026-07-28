"""Strict contracts for the public TEM parent-overlap audit."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
PUBLIC_CASE_ID = "public_cobalt_oxide_tem_parent_overlap_audit"
PUBLIC_DOI = "10.5281/zenodo.14927582"
PUBLIC_DATASET_VERSION = "v1"
PUBLIC_LICENSE = "CC-BY-4.0"
PUBLIC_TRAINING_NAME = "training_images.h5"
PUBLIC_TRAINING_MD5 = "caac404a7ea2c65b2403aee5728a70eb"
PUBLIC_TRAINING_SHA256 = "e709b7f1fa383bd111bb0b7e8d4662452b46198f52e4e88b19bb3f3e222c0926"
PUBLIC_ARCHIVE_NAME = "TEM_images.zip"
PUBLIC_ARCHIVE_MD5 = "d1e991346d07b8a112c4b6dbfd8367ba"
PUBLIC_ARCHIVE_SHA256 = "a9e4618f697205bf8560ab14bc5e313d4011b51aaa6dbf8a5c62ddc22bc558d8"
PUBLIC_PREFIXES = (
    "Co0_2", "Co0_4", "Co0_5", "Co0_7", "Co0_8",
    "DW0_6", "DW0_7", "DW0_43", "DW0_85", "DW1_0",
)

OVERLAP_EQUIVALENT = "content_equivalent_to_training_candidate_parent"
OVERLAP_REVIEW = "possible_training_parent_overlap_review_required"
OVERLAP_NOT_DETECTED = "no_content_equivalent_training_parent_overlap_detected"
CLOSEOUT_RESULT = "no_independent_external_validation_set_available"
LABEL_STATUS = "source_predicted_masks_not_independent_validation_labels"

LIMITATIONS = (
    "The training HDF5 file has no authoritative parent-image IDs; four contiguous 64-patch blocks are reconstructed candidates, not source-issued identities.",
    "The audit detects content equivalence under the pinned aligned tiling and standardization path; a negative result cannot exclude unknown crops, transforms, or unpublished acquisitions.",
    "Public masks are source-predicted outputs, not independent hand labels, so non-overlapping images are not external validation samples.",
    "Standardized public arrays do not preserve detector-intensity units, and no pixel calibration or physical-size conversion is applied.",
    "No training, inference, segmentation accuracy, causal claim, optimization, or engineering-release decision is performed.",
)


@dataclass(frozen=True)
class FileSpec:
    name: str
    url: str
    md5: str
    sha256: str


@dataclass(frozen=True)
class ArchiveSpec:
    name: str
    url: str
    md5: str
    sha256: str
    expected_members: tuple[str, ...]


@dataclass(frozen=True)
class SourceMemberSpec:
    source_id: str
    image_member: str


@dataclass(frozen=True)
class ParentOverlapAuditConfig:
    case_id: str
    record_id: int
    doi: str
    dataset_version: str
    license: str
    source_description: str
    training_file: FileSpec
    source_archive: ArchiveSpec
    source_members: tuple[SourceMemberSpec, ...]
    training_dataset_name: str
    source_dataset_name: str
    training_shape: tuple[int, int, int]
    source_member_shape: tuple[int, int, int]
    dtype: str
    attributes_expected: bool
    parent_count: int
    grid_rows: int
    grid_columns: int
    tile_height: int
    tile_width: int
    image_mean_abs_tolerance: float
    image_std_abs_tolerance: float
    quantization_decimals: int
    signature_block_size: int
    review_ncc_threshold: float
    independent_label_status: str
    notebook_repository: str
    notebook_commit: str
    tiling_notebook: str
    tiling_notebook_blob_sha: str
    normalization_notebook: str
    normalization_notebook_blob_sha: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ParentOverlapAuditConfig":
        _reject_unknown(payload, {
            "case_id", "source", "training_file", "source_archive", "source_members",
            "hdf5_contract", "parent_reconstruction", "comparison_contract",
            "label_contract", "notebook_contract",
        }, "config")
        source = _object(payload, "source")
        hdf5 = _object(payload, "hdf5_contract")
        parent = _object(payload, "parent_reconstruction")
        compare = _object(payload, "comparison_contract")
        label = _object(payload, "label_contract")
        notebook = _object(payload, "notebook_contract")
        entries = payload.get("source_members")
        if not isinstance(entries, list) or not entries:
            raise ValueError("source_members must be a non-empty list.")
        members = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                raise ValueError(f"source_members[{i}] must be an object.")
            _reject_unknown(entry, {"source_id", "image_member"}, f"source_members[{i}]")
            members.append(SourceMemberSpec(_text(entry, "source_id"), _text(entry, "image_member")))
        config = cls(
            case_id=_text(payload, "case_id"),
            record_id=int(source["record_id"]),
            doi=_text(source, "doi"),
            dataset_version=_text(source, "dataset_version"),
            license=_text(source, "license"),
            source_description=_text(source, "source_description"),
            training_file=_file_spec(_object(payload, "training_file")),
            source_archive=_archive_spec(_object(payload, "source_archive")),
            source_members=tuple(members),
            training_dataset_name=_text(hdf5, "training_dataset_name"),
            source_dataset_name=_text(hdf5, "source_dataset_name"),
            training_shape=_shape(hdf5, "training_shape"),
            source_member_shape=_shape(hdf5, "source_member_shape"),
            dtype=_text(hdf5, "dtype"),
            attributes_expected=_bool(hdf5, "attributes_expected"),
            parent_count=int(parent["parent_count"]),
            grid_rows=int(parent["grid_rows"]),
            grid_columns=int(parent["grid_columns"]),
            tile_height=int(parent["tile_height"]),
            tile_width=int(parent["tile_width"]),
            image_mean_abs_tolerance=float(compare["image_mean_abs_tolerance"]),
            image_std_abs_tolerance=float(compare["image_std_abs_tolerance"]),
            quantization_decimals=int(compare["quantization_decimals"]),
            signature_block_size=int(compare["signature_block_size"]),
            review_ncc_threshold=float(compare["review_ncc_threshold"]),
            independent_label_status=_text(label, "independent_label_status"),
            notebook_repository=_text(notebook, "repository"),
            notebook_commit=_digest(notebook, "commit", 40),
            tiling_notebook=_text(notebook, "tiling_notebook"),
            tiling_notebook_blob_sha=_digest(notebook, "tiling_notebook_blob_sha", 40),
            normalization_notebook=_text(notebook, "normalization_notebook"),
            normalization_notebook_blob_sha=_digest(notebook, "normalization_notebook_blob_sha", 40),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9_]+", self.case_id):
            raise ValueError("case_id must use lowercase letters, digits, and underscores.")
        if len(self.training_shape) != 3 or len(self.source_member_shape) != 3:
            raise ValueError("training and source shapes must be three-dimensional.")
        tiles_per_parent = self.grid_rows * self.grid_columns
        if self.parent_count * tiles_per_parent != self.training_shape[0]:
            raise ValueError("parent grid does not cover all training patches.")
        if self.training_shape[1:] != (self.tile_height, self.tile_width):
            raise ValueError("training patch shape does not match tile dimensions.")
        if self.source_member_shape[1:] != (
            self.grid_rows * self.tile_height,
            self.grid_columns * self.tile_width,
        ):
            raise ValueError("source frame shape does not match the parent grid.")
        if self.attributes_expected:
            raise ValueError("the pinned public HDF5 contract has no attributes.")
        if self.image_mean_abs_tolerance <= 0 or self.image_std_abs_tolerance <= 0:
            raise ValueError("standardization tolerances must be positive.")
        if self.quantization_decimals < 0 or self.signature_block_size <= 0:
            raise ValueError("comparison parameters must be non-negative/positive.")
        if self.tile_height % self.signature_block_size or self.tile_width % self.signature_block_size:
            raise ValueError("signature_block_size must divide each tile dimension.")
        if not -1.0 <= self.review_ncc_threshold <= 1.0:
            raise ValueError("review_ncc_threshold must be between -1 and 1.")
        if self.independent_label_status != LABEL_STATUS:
            raise ValueError("independent label status changed from the supported boundary.")
        ids = [item.source_id for item in self.source_members]
        names = [item.image_member for item in self.source_members]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("source IDs and member names must be unique.")
        for name in self.source_archive.expected_members:
            _validate_member_name(name)
        if tuple(names) != self.source_archive.expected_members:
            raise ValueError("source member map must equal archive expected_members in order.")


def load_config(path: str | Path) -> ParentOverlapAuditConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("case config must contain a JSON object.")
    return ParentOverlapAuditConfig.from_mapping(payload)


def validate_public_config(config: ParentOverlapAuditConfig) -> None:
    expected_members = tuple(f"{prefix}_TEM_images.h5" for prefix in PUBLIC_PREFIXES)
    fixed = {
        "case_id": PUBLIC_CASE_ID,
        "record_id": 14927582,
        "doi": PUBLIC_DOI,
        "dataset_version": PUBLIC_DATASET_VERSION,
        "license": PUBLIC_LICENSE,
        "training_dataset_name": "images",
        "source_dataset_name": "images",
        "training_shape": (256, 512, 512),
        "source_member_shape": (5, 4096, 4096),
        "dtype": "float64",
        "attributes_expected": False,
        "parent_count": 4,
        "grid_rows": 8,
        "grid_columns": 8,
        "tile_height": 512,
        "tile_width": 512,
        "image_mean_abs_tolerance": 1e-10,
        "image_std_abs_tolerance": 1e-12,
        "quantization_decimals": 9,
        "signature_block_size": 16,
        "review_ncc_threshold": 0.995,
        "independent_label_status": LABEL_STATUS,
        "notebook_repository": "ScottLabUCB/NN_training",
        "notebook_commit": "9f92235102a805abc76e3d60065d677ee2068c90",
        "tiling_notebook": "model training for HRTEM.ipynb",
        "tiling_notebook_blob_sha": "a21bf95fb41f63efb0c33b1563bc43a073afed58",
        "normalization_notebook": "model training for HRTEM.ipynb",
        "normalization_notebook_blob_sha": "a21bf95fb41f63efb0c33b1563bc43a073afed58",
    }
    for field, expected in fixed.items():
        actual = getattr(config, field)
        if actual != expected:
            raise ValueError(f"public config mismatch for {field}: {actual!r} != {expected!r}")
    expected_training = FileSpec(
        PUBLIC_TRAINING_NAME,
        "https://zenodo.org/records/14927582/files/training_images.h5?download=1",
        PUBLIC_TRAINING_MD5,
        PUBLIC_TRAINING_SHA256,
    )
    expected_archive = ArchiveSpec(
        PUBLIC_ARCHIVE_NAME,
        "https://zenodo.org/records/14927582/files/TEM_images.zip?download=1",
        PUBLIC_ARCHIVE_MD5,
        PUBLIC_ARCHIVE_SHA256,
        expected_members,
    )
    if config.training_file != expected_training or config.source_archive != expected_archive:
        raise ValueError("public source file specifications changed from the pinned contract.")
    expected_map = tuple(
        SourceMemberSpec(prefix.lower(), f"{prefix}_TEM_images.h5")
        for prefix in PUBLIC_PREFIXES
    )
    if config.source_members != expected_map:
        raise ValueError("public source-member map changed from the pinned contract.")


def _object(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object.")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text.")
    return value.strip()


def _bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean.")
    return value


def _shape(payload: Mapping[str, Any], key: str) -> tuple[int, int, int]:
    value = payload.get(key)
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{key} must contain three values.")
    return tuple(int(item) for item in value)


def _digest(payload: Mapping[str, Any], key: str, length: int) -> str:
    value = _text(payload, key).lower()
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"{key} must be a {length}-character hexadecimal digest.")
    return value


def _file_spec(payload: Mapping[str, Any]) -> FileSpec:
    _reject_unknown(payload, {"name", "url", "md5", "sha256"}, "file")
    return FileSpec(_text(payload, "name"), _text(payload, "url"), _digest(payload, "md5", 32), _digest(payload, "sha256", 64))


def _archive_spec(payload: Mapping[str, Any]) -> ArchiveSpec:
    _reject_unknown(payload, {"name", "url", "md5", "sha256", "expected_members"}, "archive")
    members = payload.get("expected_members")
    if not isinstance(members, list) or not members:
        raise ValueError("expected_members must be a non-empty list.")
    return ArchiveSpec(
        _text(payload, "name"), _text(payload, "url"),
        _digest(payload, "md5", 32), _digest(payload, "sha256", 64),
        tuple(str(member) for member in members),
    )


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"unknown {label} fields: {unknown}")


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe ZIP member path: {name}")
    if len(path.parts) != 1 or not name.endswith(".h5"):
        raise ValueError(f"unsupported ZIP member name: {name}")
