from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import shutil
import struct
import tempfile
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Mapping

import h5py
import numpy as np

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
CASE_ID = "zenodo_8132804_co3o4_mn3o4_audit"
SCHEMA_VERSION = "1.0"
RECORD_API = "https://zenodo.org/api/records/{record_id}"


class AuditContractError(ValueError):
    """Raised when the pinned audit contract or live source changes."""


def _json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AuditContractError("case config must contain a JSON object")
    return payload


def _mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise AuditContractError(f"{key} must be an object")
    return value


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuditContractError(f"{key} must be non-empty text")
    return value.strip()


def _integer(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditContractError(f"{key} must be an integer")
    return value


def validate_config(config: Mapping[str, Any]) -> None:
    if config.get("case_id") != CASE_ID:
        raise AuditContractError("case_id mismatch")
    source = _mapping(config, "source")
    bounded = _mapping(config, "bounded_transfer")
    expected = _mapping(config, "expected_disposition")
    members = config.get("members")
    if source.get("record_id") != "8132804":
        raise AuditContractError("record_id mismatch")
    if source.get("doi") != "10.5281/zenodo.8132804":
        raise AuditContractError("DOI mismatch")
    if source.get("archive_name") != "Multi_Modal_Data_Fusion_Chemical_Tomography.zip":
        raise AuditContractError("archive name mismatch")
    if _integer(source, "archive_bytes") <= 0:
        raise AuditContractError("archive_bytes must be positive")
    md5 = _text(source, "archive_md5").casefold()
    if len(md5) != 32 or any(ch not in "0123456789abcdef" for ch in md5):
        raise AuditContractError("archive_md5 must be hexadecimal")
    if bounded.get("full_archive_download_permitted") is not False:
        raise AuditContractError("full archive download must remain prohibited")
    budget = _integer(bounded, "maximum_compressed_member_bytes")
    if budget <= 0:
        raise AuditContractError("member transfer budget must be positive")
    if not isinstance(members, list) or len(members) != 2:
        raise AuditContractError("exactly two bounded HDF5 members are required")
    seen: set[str] = set()
    for index, member in enumerate(members):
        if not isinstance(member, Mapping):
            raise AuditContractError(f"members[{index}] must be an object")
        path = _text(member, "path")
        if path in seen or path.startswith("/") or ".." in Path(path).parts:
            raise AuditContractError(f"unsafe or duplicate member path: {path}")
        seen.add(path)
        if not path.endswith(".h5"):
            raise AuditContractError("bounded member must be HDF5")
        for key in ("local_header_offset", "compressed_bytes", "uncompressed_bytes"):
            if _integer(member, key) <= 0:
                raise AuditContractError(f"{key} must be positive")
        crc32 = _text(member, "crc32").casefold()
        sha256 = _text(member, "uncompressed_sha256").casefold()
        if len(crc32) != 8 or any(ch not in "0123456789abcdef" for ch in crc32):
            raise AuditContractError("member crc32 must be hexadecimal")
        if len(sha256) != 64 or any(ch not in "0123456789abcdef" for ch in sha256):
            raise AuditContractError("member sha256 must be hexadecimal")
        if not _mapping(member, "expected_datasets"):
            raise AuditContractError("expected_datasets must be non-empty")
    if sum(int(item["compressed_bytes"]) for item in members) > budget:
        raise AuditContractError("bounded members exceed transfer budget")
    if expected.get("external_validation_ready") is not False:
        raise AuditContractError("expected disposition must remain fail closed")
    if expected.get("model_inference_permitted") is not False:
        raise AuditContractError("model inference must remain prohibited")


def _fetch_record(record_id: str) -> tuple[dict[str, Any], bytes]:
    request = urllib.request.Request(
        RECORD_API.format(record_id=record_id),
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
        if int(response.status) != 200:
            raise RuntimeError(f"unexpected Zenodo API status: {response.status}")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("Zenodo API response is not an object")
    return payload, raw


def _archive_content_url(record: Mapping[str, Any], source: Mapping[str, Any]) -> str:
    if str(record.get("id")) != str(source["record_id"]):
        raise RuntimeError("Zenodo record identity mismatch")
    if str(record.get("doi", "")).casefold() != str(source["doi"]).casefold():
        raise RuntimeError("Zenodo DOI mismatch")
    if str(record.get("conceptdoi", "")).casefold() != str(source["concept_doi"]).casefold():
        raise RuntimeError("Zenodo concept DOI mismatch")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise RuntimeError("Zenodo metadata missing")
    if str(metadata.get("version", "")) != str(source["version"]):
        raise RuntimeError("Zenodo version mismatch")
    metadata_text = json.dumps(metadata, ensure_ascii=False).casefold()
    if not any(
        marker in metadata_text
        for marker in ("cc-by-4.0", "creativecommons.org/licenses/by/4.0")
    ):
        raise RuntimeError("CC BY 4.0 licence not resolved")
    files = record.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise RuntimeError("unexpected Zenodo file inventory")
    item = files[0]
    if not isinstance(item, Mapping):
        raise RuntimeError("invalid Zenodo file record")
    if item.get("key") != source["archive_name"]:
        raise RuntimeError("Zenodo archive name mismatch")
    if int(item.get("size", 0)) != int(source["archive_bytes"]):
        raise RuntimeError("Zenodo archive byte-count mismatch")
    if str(item.get("checksum", "")).casefold() != f"md5:{source['archive_md5']}".casefold():
        raise RuntimeError("Zenodo archive MD5 mismatch")
    links = item.get("links")
    if not isinstance(links, Mapping) or not isinstance(links.get("self"), str):
        raise RuntimeError("Zenodo archive content link missing")
    return str(links["self"])


def _range(url: str, start: int, end: int, total: int):
    if start < 0 or end < start or end >= total:
        raise RuntimeError("invalid bounded byte range")
    request = urllib.request.Request(
        url,
        headers={"Range": f"bytes={start}-{end}", "User-Agent": USER_AGENT},
    )
    response = urllib.request.urlopen(request, timeout=300)
    expected = f"bytes {start}-{end}/{total}"
    observed = response.headers.get("Content-Range")
    if int(response.status) != 206 or observed != expected:
        response.close()
        raise RuntimeError(
            f"archive range not honored: status={response.status}, "
            f"content-range={observed!r}, expected={expected!r}"
        )
    return response


def _zip_inventory(url: str, total: int, tail_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    tail_start = total - tail_bytes
    with _range(url, tail_start, total - 1, total) as response:
        tail = response.read(tail_bytes + 1)
    if len(tail) != tail_bytes:
        raise RuntimeError("ZIP tail byte-count mismatch")
    eocd_at = tail.rfind(b"PK\x05\x06")
    if eocd_at < 0:
        raise RuntimeError("ZIP EOCD not found")
    (
        _,
        disk,
        cd_disk,
        disk_entries,
        total_entries,
        cd_size,
        cd_offset,
        comment_length,
    ) = struct.unpack_from("<4s4H2LH", tail, eocd_at)
    if disk or cd_disk or disk_entries != total_entries:
        raise RuntimeError("multi-disk ZIP is unsupported")
    if any(value in (0xFFFF, 0xFFFFFFFF) for value in (total_entries, cd_size, cd_offset)):
        raise RuntimeError("ZIP64 is unsupported by this bounded audit")
    if eocd_at + 22 + comment_length > len(tail):
        raise RuntimeError("truncated ZIP EOCD")
    with _range(url, cd_offset, cd_offset + cd_size - 1, total) as response:
        central = response.read(cd_size + 1)
    if len(central) != cd_size:
        raise RuntimeError("ZIP central-directory byte-count mismatch")
    fmt = "<4s6H3L5H2L"
    fixed = struct.calcsize(fmt)
    cursor = 0
    entries: list[dict[str, Any]] = []
    while cursor < len(central):
        fields = struct.unpack_from(fmt, central, cursor)
        if fields[0] != b"PK\x01\x02":
            raise RuntimeError(f"invalid central-directory signature at {cursor}")
        flags, method, crc32 = fields[3], fields[4], fields[7]
        compressed, uncompressed = fields[8], fields[9]
        name_len, extra_len, note_len = fields[10], fields[11], fields[12]
        local_offset = fields[16]
        start = cursor + fixed
        raw_name = central[start : start + name_len]
        if len(raw_name) != name_len:
            raise RuntimeError("truncated ZIP member name")
        name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
        entries.append(
            {
                "path": name,
                "compressed_bytes": compressed,
                "uncompressed_bytes": uncompressed,
                "compression_method": method,
                "crc32": f"{crc32:08x}",
                "flags": flags,
                "local_header_offset": local_offset,
            }
        )
        cursor = start + name_len + extra_len + note_len
    if cursor != len(central) or len(entries) != total_entries:
        raise RuntimeError("ZIP central-directory parse mismatch")
    metadata = {
        "entry_count": total_entries,
        "central_directory_offset": cd_offset,
        "central_directory_bytes": cd_size,
        "tail_sha256": hashlib.sha256(tail).hexdigest(),
        "central_directory_sha256": hashlib.sha256(central).hexdigest(),
    }
    return entries, metadata, len(tail) + len(central)


def _normalize(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _normalize(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return _normalize(value.item())
        flat = value.reshape(-1)
        preview = [_normalize(item) for item in flat[:32]]
        return {
            "shape": list(value.shape),
            "dtype": str(value.dtype),
            "preview": preview,
            "truncated": int(flat.size) > len(preview),
        }
    return repr(value)


def inspect_hdf5(path: Path) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    datasets: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        root_attributes = {str(k): _normalize(v) for k, v in handle.attrs.items()}

        def visitor(name: str, obj: Any) -> None:
            attrs = {str(k): _normalize(v) for k, v in obj.attrs.items()}
            if isinstance(obj, h5py.Group):
                groups.append({"path": name, "attributes": attrs})
            elif isinstance(obj, h5py.Dataset):
                record: dict[str, Any] = {
                    "path": name,
                    "shape": list(obj.shape),
                    "dtype": str(obj.dtype),
                    "ndim": int(obj.ndim),
                    "size": int(obj.size),
                    "attributes": attrs,
                }
                if obj.size <= 64:
                    record["values"] = _normalize(obj[()])
                datasets.append(record)

        handle.visititems(visitor)
    return {
        "root_attributes": root_attributes,
        "group_count": len(groups),
        "dataset_count": len(datasets),
        "groups": groups,
        "datasets": datasets,
    }


def _extract_member(
    url: str,
    total: int,
    member: Mapping[str, Any],
    target: Path,
) -> tuple[dict[str, Any], int]:
    offset = int(member["local_header_offset"])
    with _range(url, offset, offset + 4095, total) as response:
        header = response.read(4096)
    if len(header) != 4096:
        raise RuntimeError("truncated ZIP local-header probe")
    (
        signature,
        _version,
        flags,
        method,
        _mtime,
        _mdate,
        _local_crc,
        _local_compressed,
        _local_uncompressed,
        name_len,
        extra_len,
    ) = struct.unpack_from("<4s5H3L2H", header, 0)
    if signature != b"PK\x03\x04":
        raise RuntimeError("invalid ZIP local-header signature")
    if flags & 0x1:
        raise RuntimeError("encrypted ZIP member is unsupported")
    if method != 8:
        raise RuntimeError("bounded member is not deflate-compressed")
    name_end = 30 + name_len
    extra_end = name_end + extra_len
    if extra_end > len(header):
        raise RuntimeError("ZIP local header exceeds probe window")
    name = header[30:name_end].decode("utf-8" if flags & 0x800 else "cp437")
    if name != member["path"]:
        raise RuntimeError("ZIP local member path mismatch")
    data_start = offset + extra_end
    compressed_bytes = int(member["compressed_bytes"])
    data_end = data_start + compressed_bytes - 1
    decompressor = zlib.decompressobj(-15)
    crc = 0
    compressed = 0
    uncompressed = 0
    digest = hashlib.sha256()
    with _range(url, data_start, data_end, total) as response, target.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            compressed += len(chunk)
            output = decompressor.decompress(chunk)
            if output:
                handle.write(output)
                digest.update(output)
                crc = binascii.crc32(output, crc)
                uncompressed += len(output)
        output = decompressor.flush()
        if output:
            handle.write(output)
            digest.update(output)
            crc = binascii.crc32(output, crc)
            uncompressed += len(output)
    if not decompressor.eof:
        raise RuntimeError("deflate stream did not terminate cleanly")
    if compressed != compressed_bytes:
        raise RuntimeError("compressed member byte-count mismatch")
    if uncompressed != int(member["uncompressed_bytes"]):
        raise RuntimeError("uncompressed member byte-count mismatch")
    if f"{crc & 0xFFFFFFFF:08x}" != str(member["crc32"]).casefold():
        raise RuntimeError("uncompressed member CRC32 mismatch")
    if digest.hexdigest() != str(member["uncompressed_sha256"]).casefold():
        raise RuntimeError("uncompressed member SHA-256 mismatch")
    return (
        {
            "path": member["path"],
            "compressed_bytes": compressed,
            "uncompressed_bytes": uncompressed,
            "crc32": f"{crc & 0xFFFFFFFF:08x}",
            "uncompressed_sha256": digest.hexdigest(),
            "hdf5": inspect_hdf5(target),
        },
        4096 + compressed,
    )


def _verify_datasets(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    datasets = {item["path"]: item for item in observed["datasets"]}
    if set(datasets) != set(expected):
        raise RuntimeError("HDF5 dataset inventory mismatch")
    for name, contract in expected.items():
        if datasets[name]["shape"] != list(contract["shape"]):
            raise RuntimeError(f"HDF5 shape mismatch: {name}")
        if datasets[name]["dtype"] != contract["dtype"]:
            raise RuntimeError(f"HDF5 dtype mismatch: {name}")


def _manifest(output: Path, artifacts: list[Path]) -> dict[str, Any]:
    records = []
    for path in artifacts:
        records.append(
            {
                "path": path.relative_to(output).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": CASE_ID,
        "artifact_count": len(records),
        "artifacts": records,
    }


def _report(summary: Mapping[str, Any]) -> str:
    return f"""# Zenodo 8132804 Co3O4-Mn3O4 audit

**Status:** `{summary['status']}`

## Supported

- The checksum-bound source contains real HAADF-STEM and EELS tomography arrays.
- The two audited HDF5 members match their pinned CRC32, SHA-256, shapes and dtypes.
- The released specimen is a mixed Co3O4-Mn3O4 core-shell system from one `Exp_1`.

## Scientific boundary

This is not target TEM/HRTEM segmentation validation data. It is a mixed-material,
single-experiment STEM/EELS tomography source without embedded sample/acquisition
lineage, pixel calibration, independent segmentation labels, or target-model non-use
evidence.

Registry disposition: `excluded_wrong_microscopy_modality`.

No annotation, model inference, retraining, parameter selection, performance
evaluation, or engineering claim is authorized.
"""


def run(config_path: Path, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    transient = Path(tempfile.mkdtemp(prefix="zenodo_8132804_", dir=output.parent))
    try:
        config = _json_object(config_path)
        validate_config(config)
        source = _mapping(config, "source")
        bounded = _mapping(config, "bounded_transfer")
        context = _mapping(config, "published_context")
        target = _mapping(config, "target_contract")
        expected = _mapping(config, "expected_disposition")
        record, raw_record = _fetch_record(str(source["record_id"]))
        archive_url = _archive_content_url(record, source)
        entries, zip_metadata, transferred = _zip_inventory(
            archive_url,
            int(source["archive_bytes"]),
            int(bounded["tail_probe_bytes"]),
        )
        if zip_metadata["entry_count"] != int(source["expected_zip_entry_count"]):
            raise RuntimeError("ZIP entry-count mismatch")
        if zip_metadata["central_directory_bytes"] != int(
            source["expected_central_directory_bytes"]
        ):
            raise RuntimeError("ZIP central-directory size mismatch")
        by_path = {entry["path"]: entry for entry in entries}
        audited_members = []
        for member in config["members"]:
            live_entry = by_path.get(member["path"])
            if live_entry is None:
                raise RuntimeError(f"pinned member missing: {member['path']}")
            for key in (
                "local_header_offset",
                "compressed_bytes",
                "uncompressed_bytes",
                "crc32",
            ):
                if live_entry[key] != member[key]:
                    raise RuntimeError(f"ZIP member metadata mismatch: {member['path']} {key}")
            target_path = transient / Path(member["path"]).name
            audited, member_transfer = _extract_member(
                archive_url, int(source["archive_bytes"]), member, target_path
            )
            transferred += member_transfer
            _verify_datasets(audited["hdf5"], member["expected_datasets"])
            audited_members.append(audited)
        if transferred > int(bounded["maximum_compressed_member_bytes"]) + 2 * 4096 + int(
            bounded["tail_probe_bytes"]
        ) + int(source["expected_central_directory_bytes"]):
            raise RuntimeError("observed bounded transfer exceeded policy")
        all_attributes_empty = all(
            not item["hdf5"]["root_attributes"]
            and all(not group["attributes"] for group in item["hdf5"]["groups"])
            and all(not dataset["attributes"] for dataset in item["hdf5"]["datasets"])
            for item in audited_members
        )
        raw_member = next(
            item for item in audited_members if item["path"].endswith("/raw_tilt_series.h5")
        )
        raw_datasets = {item["path"]: item for item in raw_member["hdf5"]["datasets"]}
        summary = {
            "schema_version": SCHEMA_VERSION,
            "case_id": CASE_ID,
            "audit_date": config["audit_date"],
            "status": expected["status"],
            "registry_candidate_status": expected["registry_candidate_status"],
            "record_id": source["record_id"],
            "doi": source["doi"],
            "archive_name": source["archive_name"],
            "archive_bytes": source["archive_bytes"],
            "archive_md5": source["archive_md5"],
            "record_metadata_sha256": hashlib.sha256(raw_record).hexdigest(),
            "verified_raw_stem_tomography_arrays": True,
            "target_tem_or_hrtem_arrays_available": False,
            "material": context["material"],
            "microscopy": context["microscopy"],
            "source_assigned_experiment_id": context["source_assigned_experiment_id"],
            "independent_sample_count": context["reported_independent_sample_count"],
            "independent_acquisition_count": context[
                "reported_independent_acquisition_count"
            ],
            "minimum_required_samples": target["minimum_independent_samples"],
            "minimum_required_acquisitions": target[
                "minimum_independent_acquisitions"
            ],
            "raw_haadf_tilt_series_shape": raw_datasets["haadf/tiltSeries"]["shape"],
            "raw_eels_tilt_series_shape": raw_datasets["eels/tiltSeries"]["shape"],
            "embedded_hdf5_attributes_available": not all_attributes_empty,
            "pixel_calibration_embedded": False,
            "immutable_sample_ids_available": False,
            "immutable_acquisition_ids_available": False,
            "independent_segmentation_labels_available": False,
            "target_model_nonuse_verified": False,
            "external_validation_ready": False,
            "annotation_ready": False,
            "model_inference_permitted": False,
            "model_inference_performed": False,
            "annotation_performed": False,
            "model_training_performed": False,
            "full_archive_downloaded": False,
            "source_members_retained": False,
            "observed_range_transfer_bytes": transferred,
            "scientific_closeout": {
                "status": "Supported",
                "strongest_evidence": (
                    "Two checksum-bound HDF5 members expose one mixed-material Exp_1 "
                    "with HAADF-STEM and EELS tomography arrays."
                ),
                "primary_limitation": (
                    "The source is mixed Co3O4-Mn3O4, wrong modality for target "
                    "TEM/HRTEM segmentation, single-experiment, unlabeled, and lacks "
                    "embedded lineage and calibration."
                ),
                "suitable_for": [
                    "bounded HDF5 ingestion diagnostics",
                    "cross-modality tomography research",
                ],
                "not_suitable_for": [
                    "target TEM/HRTEM segmentation validation",
                    "model selection or retraining",
                    "external performance claims",
                    "engineering release",
                ],
            },
        }
        record_path = output / "official_zenodo_record_summary.json"
        zip_path = output / "bounded_zip_inventory.json"
        hdf5_path = output / "bounded_hdf5_member_inventory.json"
        summary_path = output / "zenodo_8132804_co3o4_mn3o4_audit_summary.json"
        report_path = output / "zenodo_8132804_co3o4_mn3o4_audit_report.md"
        manifest_path = output / "zenodo_8132804_co3o4_mn3o4_audit_manifest.json"
        record_path.write_text(
            json.dumps(
                {
                    "record_id": source["record_id"],
                    "doi": source["doi"],
                    "concept_doi": source["concept_doi"],
                    "version": source["version"],
                    "license_verified": True,
                    "archive_name": source["archive_name"],
                    "archive_bytes": source["archive_bytes"],
                    "archive_md5": source["archive_md5"],
                    "record_metadata_sha256": summary["record_metadata_sha256"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        zip_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    **zip_metadata,
                    "entry_count": len(entries),
                    "entries": entries,
                    "full_archive_downloaded": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        hdf5_path.write_text(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "member_count": len(audited_members),
                    "members": audited_members,
                    "source_members_retained": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        report_path.write_text(_report(summary), encoding="utf-8")
        artifacts = [record_path, zip_path, hdf5_path, summary_path, report_path]
        manifest_path.write_text(
            json.dumps(_manifest(output, artifacts), indent=2) + "\n",
            encoding="utf-8",
        )
        return summary
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(transient, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit bounded Zenodo Co3O4-Mn3O4 STEM/EELS HDF5 members."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.config, args.output)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "registry_candidate_status": summary["registry_candidate_status"],
                "external_validation_ready": summary["external_validation_ready"],
                "observed_range_transfer_bytes": summary[
                    "observed_range_transfer_bytes"
                ],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
