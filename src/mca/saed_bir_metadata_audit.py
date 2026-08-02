"""Metadata-only audit for the BIR-MicroED 200 keV SAED candidate.

The audit consumes a Zenodo record JSON document and a pinned local contract.
It never downloads archive bytes, decodes diffraction arrays, estimates a
pattern centre, infers reciprocal calibration, or runs the SAED analyzer.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import __version__

CASE_ID = "saed_bir_200kev_metadata_audit"
SCHEMA_VERSION = "1.0"
RESULT = "metadata_resolved_but_source_not_ready_for_saed_evaluation"
EXPECTED_RECORD_ID = "10999587"
EXPECTED_DOI = "10.5281/zenodo.10999587"
EXPECTED_PUBLICATION_DOI = "10.1107/S2052252524012132"


class BIRMetadataContractError(ValueError):
    """Raised when source metadata or the pinned audit contract fails closed."""


@dataclass(frozen=True)
class ExpectedFile:
    name: str
    md5: str
    material_group: str
    temperature_k: int

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], index: int) -> "ExpectedFile":
        _reject_unknown(
            payload,
            {"name", "md5", "material_group", "temperature_k"},
            f"source.expected_files[{index}]",
        )
        item = cls(
            name=_filename(payload, "name"),
            md5=_hex(payload, "md5", 32),
            material_group=_text(payload, "material_group"),
            temperature_k=_positive_integer(payload, "temperature_k"),
        )
        if not item.name.endswith(".zip"):
            raise BIRMetadataContractError("expected archive names must end with .zip")
        return item


@dataclass(frozen=True)
class PublicationEvidence:
    microscope: str
    detector: str
    detector_native_frame_rate_hz: int
    integrated_native_frames_per_output: int
    output_frame_rate_hz: float
    output_shape: tuple[int, int]
    output_format: str
    stage_rotation_during_stationary_series: bool
    selected_area_aperture_um: int
    projected_selected_area_diameter_um: float
    illuminated_area_diameter_um: float
    small_molecule_duration_s: int
    macromolecule_duration_s: int
    source_preprocessing: tuple[str, ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "PublicationEvidence":
        allowed = {
            "microscope",
            "detector",
            "detector_native_frame_rate_hz",
            "integrated_native_frames_per_output",
            "output_frame_rate_hz",
            "output_shape",
            "output_format",
            "stage_rotation_during_stationary_series",
            "selected_area_aperture_um",
            "projected_selected_area_diameter_um",
            "illuminated_area_diameter_um",
            "small_molecule_duration_s",
            "macromolecule_duration_s",
            "source_preprocessing",
        }
        _reject_unknown(payload, allowed, "publication_evidence")
        shape = payload.get("output_shape")
        if (
            not isinstance(shape, list)
            or len(shape) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in shape)
        ):
            raise BIRMetadataContractError("output_shape must contain exactly two integers")
        item = cls(
            microscope=_text(payload, "microscope"),
            detector=_text(payload, "detector"),
            detector_native_frame_rate_hz=_positive_integer(
                payload, "detector_native_frame_rate_hz"
            ),
            integrated_native_frames_per_output=_positive_integer(
                payload, "integrated_native_frames_per_output"
            ),
            output_frame_rate_hz=_positive_float(payload, "output_frame_rate_hz"),
            output_shape=(shape[0], shape[1]),
            output_format=_text(payload, "output_format"),
            stage_rotation_during_stationary_series=_boolean(
                payload, "stage_rotation_during_stationary_series"
            ),
            selected_area_aperture_um=_positive_integer(
                payload, "selected_area_aperture_um"
            ),
            projected_selected_area_diameter_um=_positive_float(
                payload, "projected_selected_area_diameter_um"
            ),
            illuminated_area_diameter_um=_positive_float(
                payload, "illuminated_area_diameter_um"
            ),
            small_molecule_duration_s=_positive_integer(
                payload, "small_molecule_duration_s"
            ),
            macromolecule_duration_s=_positive_integer(
                payload, "macromolecule_duration_s"
            ),
            source_preprocessing=_texts(payload, "source_preprocessing"),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.microscope != "Talos F200C":
            raise BIRMetadataContractError("microscope must remain Talos F200C")
        if self.detector != "DE Apollo direct electron detector":
            raise BIRMetadataContractError("unexpected 200 keV detector")
        if self.detector_native_frame_rate_hz != 60:
            raise BIRMetadataContractError("native detector frame rate must remain 60 Hz")
        if self.integrated_native_frames_per_output != 30:
            raise BIRMetadataContractError("30 native frames must remain integrated")
        if self.output_frame_rate_hz != 2.0:
            raise BIRMetadataContractError("effective output frame rate must remain 2 Hz")
        if self.output_shape != (2048, 2048):
            raise BIRMetadataContractError("publication output shape must remain 2048x2048")
        if self.output_format.casefold() != "mrc":
            raise BIRMetadataContractError("output_format must remain MRC")
        if self.stage_rotation_during_stationary_series:
            raise BIRMetadataContractError("stationary series must preserve no stage rotation")
        required = {"native_frame_integration", "spatial_binning"}
        if not required.issubset(set(self.source_preprocessing)):
            raise BIRMetadataContractError(
                "source_preprocessing must include native_frame_integration and spatial_binning"
            )


@dataclass(frozen=True)
class AuditConfig:
    case_id: str
    search_date: str
    record_id: str
    doi: str
    record_url: str
    title: str
    publication_doi: str
    expected_files: tuple[ExpectedFile, ...]
    publication_evidence: PublicationEvidence
    minimum_independent_series: int
    require_raw_or_demonstrably_lossless: bool
    require_immutable_sample_ids: bool
    require_immutable_acquisition_ids: bool
    require_traceable_pattern_center: bool
    require_traceable_reciprocal_calibration: bool
    require_explicit_reuse_terms: bool
    require_analyzer_development_nonuse: bool

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AuditConfig":
        _reject_unknown(
            payload,
            {
                "case_id",
                "search_date",
                "source",
                "publication_evidence",
                "readiness_contract",
            },
            "config",
        )
        source = _mapping(payload, "source")
        contract = _mapping(payload, "readiness_contract")
        _reject_unknown(
            source,
            {
                "record_id",
                "doi",
                "record_url",
                "title",
                "publication_doi",
                "expected_files",
            },
            "source",
        )
        _reject_unknown(
            contract,
            {
                "minimum_independent_series",
                "require_raw_or_demonstrably_lossless",
                "require_immutable_sample_ids",
                "require_immutable_acquisition_ids",
                "require_traceable_pattern_center",
                "require_traceable_reciprocal_calibration",
                "require_explicit_reuse_terms",
                "require_analyzer_development_nonuse",
            },
            "readiness_contract",
        )
        raw_files = source.get("expected_files")
        if not isinstance(raw_files, list) or not raw_files:
            raise BIRMetadataContractError("expected_files must be a non-empty list")
        config = cls(
            case_id=_text(payload, "case_id"),
            search_date=_iso_date(payload, "search_date"),
            record_id=_text(source, "record_id"),
            doi=_text(source, "doi"),
            record_url=_https(source, "record_url"),
            title=_text(source, "title"),
            publication_doi=_text(source, "publication_doi"),
            expected_files=tuple(
                ExpectedFile.from_mapping(_mapping_value(item, f"expected_files[{index}]"), index)
                for index, item in enumerate(raw_files)
            ),
            publication_evidence=PublicationEvidence.from_mapping(
                _mapping(payload, "publication_evidence")
            ),
            minimum_independent_series=_positive_integer(
                contract, "minimum_independent_series"
            ),
            require_raw_or_demonstrably_lossless=_boolean(
                contract, "require_raw_or_demonstrably_lossless"
            ),
            require_immutable_sample_ids=_boolean(
                contract, "require_immutable_sample_ids"
            ),
            require_immutable_acquisition_ids=_boolean(
                contract, "require_immutable_acquisition_ids"
            ),
            require_traceable_pattern_center=_boolean(
                contract, "require_traceable_pattern_center"
            ),
            require_traceable_reciprocal_calibration=_boolean(
                contract, "require_traceable_reciprocal_calibration"
            ),
            require_explicit_reuse_terms=_boolean(
                contract, "require_explicit_reuse_terms"
            ),
            require_analyzer_development_nonuse=_boolean(
                contract, "require_analyzer_development_nonuse"
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.case_id != CASE_ID:
            raise BIRMetadataContractError(f"case_id must equal {CASE_ID!r}")
        if self.record_id != EXPECTED_RECORD_ID:
            raise BIRMetadataContractError("unexpected BIR 200 keV record_id")
        if self.doi != EXPECTED_DOI:
            raise BIRMetadataContractError("unexpected BIR 200 keV DOI")
        if self.publication_doi != EXPECTED_PUBLICATION_DOI:
            raise BIRMetadataContractError("unexpected publication DOI")
        if self.minimum_independent_series < 2:
            raise BIRMetadataContractError("minimum_independent_series must be at least 2")
        required_flags = (
            self.require_raw_or_demonstrably_lossless,
            self.require_immutable_sample_ids,
            self.require_immutable_acquisition_ids,
            self.require_traceable_pattern_center,
            self.require_traceable_reciprocal_calibration,
            self.require_explicit_reuse_terms,
            self.require_analyzer_development_nonuse,
        )
        if not all(required_flags):
            raise BIRMetadataContractError("all fail-closed readiness requirements must remain true")
        names = [item.name for item in self.expected_files]
        if len(names) != len(set(names)):
            raise BIRMetadataContractError("expected archive names must be unique")
        checksums = [item.md5 for item in self.expected_files]
        if len(checksums) != len(set(checksums)):
            raise BIRMetadataContractError("expected archive MD5 values must be unique")


@dataclass(frozen=True)
class RecordFile:
    name: str
    bytes: int
    checksum_algorithm: str
    checksum: str
    mimetype: str

    @property
    def md5(self) -> str:
        if self.checksum_algorithm != "md5":
            raise BIRMetadataContractError(
                f"{self.name} must expose an archive-level MD5 checksum"
            )
        return self.checksum


def load_config(path: str | Path) -> AuditConfig:
    payload = _load_json_strict(Path(path), "audit config")
    return AuditConfig.from_mapping(payload)


def load_record(path: str | Path) -> Mapping[str, Any]:
    return _load_json_strict(Path(path), "Zenodo record JSON")


def audit_bir_metadata(
    config: AuditConfig,
    record: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output, created_output = _prepare_output(output_dir)
    try:
        record_bytes = _canonical_json_bytes(record)
        record_sha256 = hashlib.sha256(record_bytes).hexdigest()
        identity = _record_identity(record)
        _validate_record_identity(config, identity)
        files = _record_files(record)
        _validate_files(config, files)
        rights = _record_rights(record)
        publication = config.publication_evidence
        total_bytes = sum(item.bytes for item in files)
        smallest = min(files, key=lambda item: (item.bytes, item.name))
        gates = {
            "record_identity_verified": True,
            "record_file_inventory_verified": True,
            "archive_level_md5_values_verified": True,
            "files_publicly_described_as_mrc_series": True,
            "static_selected_area_acquisition_supported_by_publication": True,
            "microscope_and_detector_supported_by_publication": True,
            "accelerating_voltage_supported": True,
            "native_detector_frames_released": False,
            "released_representation_is_acquisition_derived": True,
            "released_representation_is_demonstrably_lossless_to_native_frames": False,
            "archive_member_inventory_verified": False,
            "minimum_independent_series_verified": False,
            "immutable_sample_ids_verified": False,
            "immutable_acquisition_ids_verified": False,
            "pattern_center_traceable": False,
            "reciprocal_calibration_traceable": False,
            "explicit_reuse_terms_verified": bool(rights),
            "analyzer_development_nonuse_verified": False,
            "ready_for_bounded_archive_download": False,
            "ready_for_saed_validation_intake": False,
            "ready_for_predeclared_external_evaluation": False,
        }
        blockers = [
            "released_mrc_integrates_30_native_frames_and_is_spatially_binned",
            "native_60_hz_detector_frames_not_released_by_this_record",
            "archive_member_inventory_not_verified_without_archive_access",
            "minimum_independent_series_count_not_verified",
            "immutable_sample_ids_not_bound_to_series",
            "immutable_acquisition_ids_not_bound_to_series",
            "pattern_center_not_traceable",
            "reciprocal_calibration_not_traceable",
            "analyzer_development_nonuse_not_verified",
        ]
        if not rights:
            blockers.append("explicit_data_reuse_terms_not_declared_in_record_metadata")
        file_rows = [
            {
                "name": item.name,
                "bytes": item.bytes,
                "md5": item.md5,
                "mimetype": item.mimetype,
                "material_group": _expected_file(config, item.name).material_group,
                "temperature_k": _expected_file(config, item.name).temperature_k,
                "archive_member_count_verified": False,
                "bounded_subset_selected": item.name == smallest.name,
            }
            for item in sorted(files, key=lambda item: item.name)
        ]
        gap_rows = _gap_rows(gates)
        request_items = _author_request_items(config)
        subset_plan = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "selected_archive": smallest.name,
            "selected_archive_bytes": smallest.bytes,
            "selection_basis": (
                "smallest checksum-bound 200 keV archive; download remains prohibited "
                "until member count, sample/acquisition lineage, centre, calibration, "
                "reuse terms, and analyzer-development non-use are resolved"
            ),
            "download_authorized_now": False,
            "required_pre_download_evidence": request_items,
            "minimum_independent_series": config.minimum_independent_series,
            "full_record_download_prohibited": True,
            "total_record_bytes": total_bytes,
        }
        summary: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "software_version": __version__,
            "result": RESULT,
            "search_date": config.search_date,
            "source": {
                "repository": "Zenodo",
                "record_id": identity["record_id"],
                "doi": identity["doi"],
                "record_url": config.record_url,
                "title": identity["title"],
                "record_metadata_sha256": record_sha256,
                "observed_created": identity["created"],
                "observed_updated": identity["updated"],
                "archive_count": len(files),
                "total_archive_bytes": total_bytes,
                "rights": rights,
            },
            "publication_evidence": {
                "publication_doi": config.publication_doi,
                "microscope": publication.microscope,
                "detector": publication.detector,
                "accelerating_voltage_kv": 200,
                "detector_native_frame_rate_hz": publication.detector_native_frame_rate_hz,
                "integrated_native_frames_per_output": (
                    publication.integrated_native_frames_per_output
                ),
                "effective_output_frame_rate_hz": publication.output_frame_rate_hz,
                "output_shape": list(publication.output_shape),
                "output_format": publication.output_format,
                "stage_rotation_during_stationary_series": (
                    publication.stage_rotation_during_stationary_series
                ),
                "selected_area_aperture_um": publication.selected_area_aperture_um,
                "projected_selected_area_diameter_um": (
                    publication.projected_selected_area_diameter_um
                ),
                "illuminated_area_diameter_um": (
                    publication.illuminated_area_diameter_um
                ),
                "small_molecule_duration_s": publication.small_molecule_duration_s,
                "macromolecule_duration_s": publication.macromolecule_duration_s,
                "source_preprocessing": list(publication.source_preprocessing),
            },
            "evidence_gates": gates,
            "blockers": blockers,
            "recommended_next_action": (
                "Resolve the publication-correspondence metadata request, then inspect "
                f"only {smallest.name} as the bounded first archive if all pre-download "
                "gates pass."
            ),
            "scientific_closeout": {
                "status": "Inconclusive",
                "strongest_evidence": (
                    "The official record identity, four archive names and MD5 values, "
                    "and publication-level 200 keV stationary SAED acquisition method "
                    "are supported."
                ),
                "primary_limitation": (
                    "The released MRC series are integrated and binned acquisition-derived "
                    "frames, while archive members, immutable lineage, centre, reciprocal "
                    "calibration, reuse terms, and analyzer-development non-use remain unresolved."
                ),
                "evidence_that_would_change_conclusion": (
                    "Authoritative series-to-crystal lineage, archive member inventory, "
                    "direct-beam/centre procedure, reciprocal calibration, explicit data "
                    "reuse terms, and analyzer-development non-use, followed by a checksum-bound "
                    "bounded archive audit."
                ),
                "suitable_for": [
                    "source metadata triage",
                    "bounded-download planning",
                    "author metadata request preparation",
                ],
                "not_suitable_for": [
                    "SAED analyzer execution",
                    "parameter selection",
                    "d-spacing validation",
                    "reflection or phase indexing",
                    "engineering release",
                ],
            },
        }

        inventory_path = output / "bir_archive_inventory.csv"
        gaps_path = output / "bir_metadata_gap_matrix.csv"
        summary_path = output / "bir_metadata_audit_summary.json"
        plan_path = output / "bir_bounded_subset_plan.json"
        request_path = output / "bir_author_metadata_request.md"
        report_path = output / "bir_metadata_audit_report.md"
        manifest_path = output / "bir_metadata_audit_manifest.json"

        _write_csv(inventory_path, file_rows)
        _write_csv(gaps_path, gap_rows)
        _write_json(summary_path, summary)
        _write_json(plan_path, subset_plan)
        request_path.write_text(_build_author_request(config, request_items), encoding="utf-8")
        report_path.write_text(
            _build_report(summary, file_rows, subset_plan), encoding="utf-8"
        )
        _write_json(
            manifest_path,
            _artifact_manifest(
                output,
                [
                    inventory_path,
                    gaps_path,
                    summary_path,
                    plan_path,
                    request_path,
                    report_path,
                ],
                record_sha256,
            ),
        )
        return summary
    except Exception:
        _cleanup_failed_output(output, created_output)
        raise


def _record_identity(record: Mapping[str, Any]) -> dict[str, str]:
    metadata = _mapping_or_empty(record.get("metadata"))
    pids = _mapping_or_empty(record.get("pids"))
    doi_node = _mapping_or_empty(pids.get("doi"))
    record_id = str(record.get("id", "")).strip()
    doi = str(
        record.get("doi")
        or doi_node.get("identifier")
        or metadata.get("doi")
        or ""
    ).strip()
    title = str(record.get("title") or metadata.get("title") or "").strip()
    created = str(record.get("created") or "").strip()
    updated = str(record.get("updated") or record.get("modified") or "").strip()
    if not record_id or not doi or not title:
        raise BIRMetadataContractError(
            "Zenodo record must expose id, DOI, and title"
        )
    return {
        "record_id": record_id,
        "doi": doi,
        "title": title,
        "created": created,
        "updated": updated,
    }


def _validate_record_identity(
    config: AuditConfig, identity: Mapping[str, str]
) -> None:
    if identity["record_id"] != config.record_id:
        raise BIRMetadataContractError("Zenodo record_id mismatch")
    if identity["doi"].casefold() != config.doi.casefold():
        raise BIRMetadataContractError("Zenodo DOI mismatch")
    if _normalize_space(identity["title"]) != _normalize_space(config.title):
        raise BIRMetadataContractError("Zenodo title mismatch")


def _record_files(record: Mapping[str, Any]) -> list[RecordFile]:
    raw_files = record.get("files")
    values: list[Any]
    if isinstance(raw_files, list):
        values = raw_files
    elif isinstance(raw_files, Mapping):
        entries = raw_files.get("entries")
        if isinstance(entries, Mapping):
            values = list(entries.values())
        elif all(isinstance(value, Mapping) for value in raw_files.values()):
            values = list(raw_files.values())
        else:
            raise BIRMetadataContractError(
                "Zenodo files object must expose an entries mapping"
            )
    else:
        raise BIRMetadataContractError("Zenodo record must expose files")
    result: list[RecordFile] = []
    for index, raw in enumerate(values):
        item = _mapping_value(raw, f"files[{index}]")
        name = str(
            item.get("key") or item.get("filename") or item.get("name") or ""
        ).strip()
        size = item.get("size", item.get("filesize"))
        checksum_raw = str(item.get("checksum") or "").strip().casefold()
        mimetype = str(item.get("mimetype") or item.get("type") or "").strip()
        if not name or isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise BIRMetadataContractError(
                f"files[{index}] must expose name and positive byte size"
            )
        algorithm, checksum = _split_checksum(checksum_raw)
        result.append(
            RecordFile(
                name=name,
                bytes=size,
                checksum_algorithm=algorithm,
                checksum=checksum,
                mimetype=mimetype,
            )
        )
    if not result:
        raise BIRMetadataContractError("Zenodo record contains no files")
    names = [item.name for item in result]
    if len(names) != len(set(names)):
        raise BIRMetadataContractError("Zenodo file names must be unique")
    return result


def _validate_files(config: AuditConfig, files: Sequence[RecordFile]) -> None:
    expected = {item.name: item for item in config.expected_files}
    observed = {item.name: item for item in files}
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        unexpected = sorted(set(observed) - set(expected))
        raise BIRMetadataContractError(
            f"Zenodo file inventory mismatch: missing={missing}, unexpected={unexpected}"
        )
    for name, expected_item in expected.items():
        observed_item = observed[name]
        if observed_item.md5 != expected_item.md5:
            raise BIRMetadataContractError(
                f"archive MD5 mismatch for {name}: "
                f"{observed_item.md5} != {expected_item.md5}"
            )
        if not name.endswith(".zip"):
            raise BIRMetadataContractError(f"unexpected non-ZIP record file: {name}")


def _record_rights(record: Mapping[str, Any]) -> list[str]:
    metadata = _mapping_or_empty(record.get("metadata"))
    raw = metadata.get("rights")
    if raw is None:
        raw = metadata.get("license")
    if raw is None:
        return []
    values = raw if isinstance(raw, list) else [raw]
    rights: list[str] = []
    for item in values:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, Mapping):
            title = item.get("title")
            if isinstance(title, Mapping):
                value = str(title.get("en") or next(iter(title.values()), "")).strip()
            else:
                value = str(
                    item.get("id")
                    or item.get("identifier")
                    or title
                    or ""
                ).strip()
        else:
            continue
        if value and value not in rights:
            rights.append(value)
    return rights


def _gap_rows(gates: Mapping[str, bool]) -> list[dict[str, Any]]:
    categories = {
        "record_identity_verified": "source_identity",
        "record_file_inventory_verified": "source_identity",
        "archive_level_md5_values_verified": "source_identity",
        "files_publicly_described_as_mrc_series": "representation",
        "static_selected_area_acquisition_supported_by_publication": "acquisition",
        "microscope_and_detector_supported_by_publication": "instrument",
        "accelerating_voltage_supported": "instrument",
        "native_detector_frames_released": "representation",
        "released_representation_is_demonstrably_lossless_to_native_frames": "representation",
        "archive_member_inventory_verified": "source_identity",
        "minimum_independent_series_verified": "independence",
        "immutable_sample_ids_verified": "lineage",
        "immutable_acquisition_ids_verified": "lineage",
        "pattern_center_traceable": "calibration",
        "reciprocal_calibration_traceable": "calibration",
        "explicit_reuse_terms_verified": "reuse",
        "analyzer_development_nonuse_verified": "independence",
        "ready_for_bounded_archive_download": "readiness",
        "ready_for_saed_validation_intake": "readiness",
        "ready_for_predeclared_external_evaluation": "readiness",
    }
    return [
        {
            "gate": key,
            "category": categories.get(key, "other"),
            "supported": value,
            "blocking": not value,
        }
        for key, value in gates.items()
        if key != "released_representation_is_acquisition_derived"
    ]


def _author_request_items(config: AuditConfig) -> list[str]:
    return [
        "Confirm whether the released MRC arrays are integer sums or averages of the 30 native Apollo frames and document any spatial-binning operation.",
        "Provide an archive member inventory or identify at least two independent stationary series within AVAAGA_200kV_293K.zip before download.",
        "Bind every proposed series filename to an immutable crystal/sample identifier and acquisition identifier.",
        "Provide the diffraction camera length or a traceable reciprocal-space calibration for the released 2048x2048 MRC arrays.",
        "Provide the direct-beam position or the exact reproducible centre-calibration procedure used for the released arrays.",
        "Confirm detector pixel geometry after integration and binning, including any crop, transpose, flip, or coordinate convention.",
        "State whether the proposed series or their derived outputs were used to develop, tune, or select the current analyzer.",
        "Provide explicit data reuse terms for the Zenodo record files.",
        f"Confirm that at least {config.minimum_independent_series} proposed series represent independent acquisitions rather than exports or repeated processing of one acquisition.",
    ]


def _build_author_request(config: AuditConfig, items: Sequence[str]) -> str:
    numbered = "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))
    return f"""# BIR-MicroED 200 keV metadata request

This request concerns Zenodo record `{config.doi}` and publication `{config.publication_doi}`.

The public record and article already support a 200 keV Talos F200C acquisition using a DE Apollo detector, stationary selected-area diffraction, 30-frame integration, 2048×2048 binned MRC output, and four checksum-bound archives. The following fields are still required before any bounded archive download or SAED analyzer execution:

{numbered}

No phase, reflection, zone-axis, centre, calibration, or d-spacing result will be used to tune the analyzer. Archive download should remain limited to the smallest qualifying subset after these fields are resolved.
"""


def _build_report(
    summary: Mapping[str, Any],
    file_rows: Sequence[Mapping[str, Any]],
    subset_plan: Mapping[str, Any],
) -> str:
    source = summary["source"]
    evidence = summary["publication_evidence"]
    lines = [
        "# BIR-MicroED 200 keV metadata audit",
        "",
        f"- Result: `{summary['result']}`",
        f"- Record: `{source['doi']}`",
        f"- Record metadata SHA-256: `{source['record_metadata_sha256']}`",
        f"- Archive count: `{source['archive_count']}`",
        f"- Total archive bytes: `{source['total_archive_bytes']}`",
        f"- Publication DOI: `{evidence['publication_doi']}`",
        f"- Microscope: `{evidence['microscope']}`",
        f"- Detector: `{evidence['detector']}`",
        f"- Released representation: `{evidence['output_shape'][0]}x{evidence['output_shape'][1]} {evidence['output_format']}`",
        "",
        "## Archive inventory",
        "",
    ]
    for row in file_rows:
        lines.append(
            f"- `{row['name']}` — {row['bytes']} bytes — MD5 `{row['md5']}`"
        )
    lines.extend(
        [
            "",
            "## Bounded subset decision",
            "",
            f"- Selected first archive: `{subset_plan['selected_archive']}`",
            f"- Download authorized now: `{str(subset_plan['download_authorized_now']).lower()}`",
            "- Reason: smallest checksum-bound archive, but member inventory, lineage, centre, calibration, reuse, and non-use remain unresolved.",
            "",
            "## Scientific boundary",
            "",
            "The metadata audit does not download archive bytes, inspect ZIP members, decode MRC arrays, estimate the pattern centre, infer reciprocal calibration, run the analyzer, or validate crystallographic assignments.",
            "",
        ]
    )
    return "\n".join(lines)


def _artifact_manifest(
    output: Path, paths: Sequence[Path], record_sha256: str
) -> dict[str, Any]:
    rows = [
        {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _hash_file(path),
        }
        for path in paths
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "record_metadata_sha256": record_sha256,
        "artifact_count": len(rows),
        "artifacts": rows,
    }


def _expected_file(config: AuditConfig, name: str) -> ExpectedFile:
    for item in config.expected_files:
        if item.name == name:
            return item
    raise BIRMetadataContractError(f"unexpected archive: {name}")


def _split_checksum(value: str) -> tuple[str, str]:
    if ":" not in value:
        if re.fullmatch(r"[0-9a-f]{32}", value):
            return "md5", value
        raise BIRMetadataContractError("file checksum must include an algorithm")
    algorithm, checksum = value.split(":", 1)
    algorithm = algorithm.strip().casefold()
    checksum = checksum.strip().casefold()
    expected_length = {"md5": 32, "sha256": 64}.get(algorithm)
    if expected_length is None or not re.fullmatch(
        rf"[0-9a-f]{{{expected_length}}}", checksum
    ):
        raise BIRMetadataContractError("unsupported or malformed file checksum")
    return algorithm, checksum


def _load_json_strict(path: Path, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise BIRMetadataContractError(f"could not read {label}: {path}") from exc
    if not isinstance(payload, Mapping):
        raise BIRMetadataContractError(f"{label} root must be an object")
    return payload


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _prepare_output(path: str | Path) -> tuple[Path, bool]:
    output = Path(path)
    if output.exists():
        if not output.is_dir() or output.is_symlink() or any(output.iterdir()):
            raise FileExistsError("output must be an absent or empty directory")
        return output, False
    output.mkdir(parents=True)
    return output, True


def _cleanup_failed_output(output: Path, created_output: bool) -> None:
    if not output.exists() or not output.is_dir() or output.is_symlink():
        return
    if created_output:
        shutil.rmtree(output, ignore_errors=True)
        return
    for child in output.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise BIRMetadataContractError(f"cannot write empty CSV: {path.name}")
    columns = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BIRMetadataContractError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_unknown(
    payload: Mapping[str, Any], allowed: set[str], context: str
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise BIRMetadataContractError(
            f"unknown {context} field: {unknown[0]}"
        )


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise BIRMetadataContractError(f"{key} must be an object")
    return value


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_value(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BIRMetadataContractError(f"{context} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BIRMetadataContractError(f"{key} must be a non-empty string")
    return value.strip()


def _https(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if not value.startswith("https://"):
        raise BIRMetadataContractError(f"{key} must be an HTTPS URL")
    return value


def _filename(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    if "/" in value or "\\" in value or value in {".", ".."}:
        raise BIRMetadataContractError(f"{key} must be a basename")
    return value


def _hex(payload: Mapping[str, Any], key: str, length: int) -> str:
    value = _text(payload, key).casefold()
    if not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise BIRMetadataContractError(f"{key} must be {length} hexadecimal characters")
    return value


def _texts(payload: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise BIRMetadataContractError(f"{key} must be a non-empty string array")
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BIRMetadataContractError(f"{key} must contain non-empty strings")
        cleaned.append(item.strip())
    if len(cleaned) != len(set(cleaned)):
        raise BIRMetadataContractError(f"{key} must not contain duplicates")
    return tuple(cleaned)


def _boolean(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise BIRMetadataContractError(f"{key} must be boolean")
    return value


def _positive_integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BIRMetadataContractError(f"{key} must be a positive integer")
    return value


def _positive_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise BIRMetadataContractError(f"{key} must be a positive number")
    return float(value)


def _iso_date(payload: Mapping[str, Any], key: str) -> str:
    value = _text(payload, key)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise BIRMetadataContractError(f"{key} must be YYYY-MM-DD") from exc
    return value


def _normalize_space(value: str) -> str:
    return " ".join(value.split())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit BIR-MicroED 200 keV Zenodo metadata without downloading archives."
    )
    parser.add_argument("--config", required=True, help="Pinned audit contract JSON")
    parser.add_argument("--record-json", required=True, help="Zenodo record JSON")
    parser.add_argument("--output", required=True, help="Absent or empty output directory")
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = audit_bir_metadata(
        load_config(args.config),
        load_record(args.record_json),
        args.output,
    )
    print(
        json.dumps(
            {
                "result": summary["result"],
                "archive_count": summary["source"]["archive_count"],
                "total_archive_bytes": summary["source"]["total_archive_bytes"],
                "recommended_next_action": summary["recommended_next_action"],
                "ready_for_bounded_archive_download": summary["evidence_gates"][
                    "ready_for_bounded_archive_download"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
