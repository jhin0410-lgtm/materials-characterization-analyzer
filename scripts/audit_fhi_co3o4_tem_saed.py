from __future__ import annotations

import argparse
import csv
import hashlib
import html.parser
import json
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

USER_AGENT = "materials-characterization-analyzer-source-audit/1.0"
RESULT_AVAILABLE = (
    "institutional_exact_material_archives_inventoried_but_"
    "external_validation_metadata_incomplete"
)
RESULT_AUTH_BLOCKED = (
    "institutional_exact_material_record_confirmed_but_"
    "anonymous_source_download_requires_authentication"
)
NATIVE_MICROSCOPY_SUFFIXES = {
    ".dm3",
    ".dm4",
    ".emd",
    ".ser",
    ".emi",
    ".mrc",
    ".mrcs",
    ".tvips",
    ".h5",
    ".hdf5",
}
LOSSLESS_RASTER_SUFFIXES = {".tif", ".tiff", ".png"}
RENDERED_RASTER_SUFFIXES = {".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
FORBIDDEN_FINAL_SUFFIXES = {
    ".zip",
    *NATIVE_MICROSCOPY_SUFFIXES,
    *LOSSLESS_RASTER_SUFFIXES,
    *RENDERED_RASTER_SUFFIXES,
}
SUPPORTED_COMPRESSION = {
    zipfile.ZIP_STORED,
    zipfile.ZIP_DEFLATED,
    zipfile.ZIP_BZIP2,
    zipfile.ZIP_LZMA,
}


class FhiCo3O4AuditError(RuntimeError):
    """Raised when the institutional source fails the audit contract."""


class _RecordParser(html.parser.HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.text_parts: list[str] = []
        self.links: dict[str, str] = {}
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        self._anchor_href = href.strip() if isinstance(href, str) else None
        self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self.text_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._anchor_href is None:
            return
        text = " ".join("".join(self._anchor_text).split())
        if text:
            self.links[text] = urllib.parse.urljoin(self.base_url, self._anchor_href)
        self._anchor_href = None
        self._anchor_text = []

    @property
    def normalized_text(self) -> str:
        return " ".join(" ".join(self.text_parts).split())


class _LoginPageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.form_count = 0
        self.password_input_count = 0
        self.username_like_input_count = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        tag = tag.casefold()
        if tag == "form":
            self.form_count += 1
        if tag != "input":
            return
        input_type = str(values.get("type", "text")).casefold()
        name = str(values.get("name", "")).casefold()
        if input_type == "password":
            self.password_input_count += 1
        if input_type in {"text", "email"} and name in {
            "name",
            "username",
            "user",
            "email",
            "login",
        }:
            self.username_like_input_count += 1


class _NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, expected_host: str) -> None:
        super().__init__()
        self.expected_host = expected_host.casefold()

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        target = urllib.parse.urljoin(req.full_url, newurl)
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme != "https" or parsed.netloc.casefold() != self.expected_host:
            raise FhiCo3O4AuditError("download redirect leaves the pinned HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, target)


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {"case_id", "audit_date", "source", "limits", "scientific_boundary"}
    if set(payload) != expected:
        raise FhiCo3O4AuditError("unexpected top-level config keys")
    source = payload["source"]
    source_keys = {
        "repository",
        "record_id",
        "record_url",
        "expected_title",
        "expected_document_type",
        "expected_sample_number",
        "required_methods",
        "target_files",
    }
    if set(source) != source_keys:
        raise FhiCo3O4AuditError("unexpected source config keys")
    limit_keys = {
        "max_members_per_archive",
        "max_total_uncompressed_bytes_per_archive",
        "max_single_member_bytes",
        "max_compression_ratio",
    }
    if set(payload["limits"]) != limit_keys:
        raise FhiCo3O4AuditError("unexpected limits config keys")
    targets = source["target_files"]
    if not isinstance(targets, list) or not targets:
        raise FhiCo3O4AuditError("target_files must be a non-empty list")
    names = [str(item.get("name", "")) for item in targets]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise FhiCo3O4AuditError("target filenames must be non-empty and unique")
    expected_target_keys = {
        "name",
        "declared_role",
        "declared_size",
        "max_download_bytes",
    }
    for target in targets:
        if set(target) != expected_target_keys:
            raise FhiCo3O4AuditError("unexpected target file keys")
        if not isinstance(target["max_download_bytes"], int) or target[
            "max_download_bytes"
        ] <= 0:
            raise FhiCo3O4AuditError("max_download_bytes must be positive")
    return payload


def _open_same_host(url: str, *, accept: str) -> Any:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise FhiCo3O4AuditError("source URL must use HTTPS")
    opener = urllib.request.build_opener(_NoCrossHostRedirect(parsed.netloc))
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    return opener.open(request, timeout=180)


def _fetch_text(url: str) -> str:
    with _open_same_host(url, accept="text/html") as response:
        final = urllib.parse.urlparse(response.geturl())
        requested = urllib.parse.urlparse(url)
        if final.netloc.casefold() != requested.netloc.casefold():
            raise FhiCo3O4AuditError("record request left the pinned host")
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="strict")


def parse_record_html(html_text: str, base_url: str) -> tuple[str, dict[str, str]]:
    parser = _RecordParser(base_url)
    parser.feed(html_text)
    parser.close()
    return parser.normalized_text, parser.links


def verify_record(
    config: dict[str, Any], html_text: str
) -> tuple[dict[str, str], dict[str, Any]]:
    source = config["source"]
    page_text, links = parse_record_html(html_text, source["record_url"])
    folded = page_text.casefold()
    required_tokens = [
        source["record_id"],
        source["expected_title"],
        source["expected_document_type"],
        source["expected_sample_number"],
        *source["required_methods"],
        "Open Access",
    ]
    missing = [token for token in required_tokens if str(token).casefold() not in folded]
    if missing:
        raise FhiCo3O4AuditError(f"record page is missing pinned token: {missing[0]}")

    target_links: dict[str, str] = {}
    record_host = urllib.parse.urlparse(source["record_url"]).netloc.casefold()
    for target in source["target_files"]:
        name = target["name"]
        url = links.get(name)
        if not url:
            raise FhiCo3O4AuditError(f"record page is missing target link: {name}")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc.casefold() != record_host:
            raise FhiCo3O4AuditError(f"target link leaves pinned host: {name}")
        if not parsed.path.startswith("/send/"):
            raise FhiCo3O4AuditError(f"unexpected target download path: {name}")
        target_links[name] = url

    record = {
        "repository": source["repository"],
        "record_id": source["record_id"],
        "record_url": source["record_url"],
        "title": source["expected_title"],
        "document_type": source["expected_document_type"],
        "sample_number": source["expected_sample_number"],
        "required_methods_confirmed": list(source["required_methods"]),
        "open_access_marker_confirmed": True,
    }
    return target_links, record


def classify_html_authentication_block(body: bytes, content_type: str) -> bool:
    looks_html = "html" in content_type.casefold() or body.lstrip().lower().startswith(
        (b"<!doctype html", b"<html")
    )
    if not looks_html:
        return False
    parser = _LoginPageParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    return (
        parser.form_count >= 1
        and parser.password_input_count >= 1
        and parser.username_like_input_count >= 1
    )


def probe_download(url: str, *, max_probe_bytes: int = 1_000_000) -> dict[str, Any]:
    with _open_same_host(
        url,
        accept="application/zip,application/octet-stream;q=0.9,text/html;q=0.5",
    ) as response:
        body = response.read(max_probe_bytes)
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        final_path = urllib.parse.urlparse(final_url).path
        authentication_required = final_path == "/login" or classify_html_authentication_block(
            body, content_type
        )
        looks_zip = body.startswith(b"PK\x03\x04") or body.startswith(b"PK\x05\x06")
        looks_html = "html" in content_type.casefold() or body.lstrip().lower().startswith(
            (b"<!doctype html", b"<html")
        )
        state = (
            "authentication_required"
            if authentication_required
            else "direct_zip_available"
            if looks_zip
            else "unexpected_html_intermediary"
            if looks_html
            else "unexpected_binary_response"
        )
        return {
            "requested_url": url,
            "final_url": final_url,
            "http_status": response.status,
            "content_type": content_type,
            "content_length_header": response.headers.get("Content-Length"),
            "content_disposition": response.headers.get("Content-Disposition"),
            "sampled_bytes": len(body),
            "state": state,
            "authentication_required": authentication_required,
            "direct_zip_magic_confirmed": looks_zip,
        }


def _stream_download(url: str, destination: Path, *, max_bytes: int) -> dict[str, Any]:
    sha256 = hashlib.sha256()
    total = 0
    prefix = bytearray()
    with _open_same_host(url, accept="application/zip,application/octet-stream") as response:
        final_path = urllib.parse.urlparse(response.geturl()).path
        content_type = response.headers.get("Content-Type", "")
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise FhiCo3O4AuditError(
                    f"download exceeds configured byte limit for {destination.name}"
                )
            if len(prefix) < 512:
                prefix.extend(chunk[: 512 - len(prefix)])
            destination.write_bytes(b"") if total == len(chunk) else None
            with destination.open("ab") as handle:
                handle.write(chunk)
            sha256.update(chunk)
    authentication_required = final_path == "/login" or classify_html_authentication_block(
        bytes(prefix), content_type
    )
    if authentication_required:
        destination.unlink(missing_ok=True)
        raise FhiCo3O4AuditError(
            f"anonymous download requires authentication for {destination.name}"
        )
    if total <= 0:
        raise FhiCo3O4AuditError(f"empty download for {destination.name}")
    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise FhiCo3O4AuditError(f"download is not a ZIP archive: {destination.name}")
    return {"bytes": total, "sha256": sha256.hexdigest()}


def _safe_member_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or normalized.endswith("/"):
        return ""
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FhiCo3O4AuditError(f"unsafe archive member path: {name}")
    return path.as_posix()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _hash_member(handle: BinaryIO, expected_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while chunk := handle.read(1024 * 1024):
        total += len(chunk)
        if total > expected_bytes:
            raise FhiCo3O4AuditError("archive member expanded beyond declared size")
        digest.update(chunk)
    if total != expected_bytes:
        raise FhiCo3O4AuditError("archive member byte count mismatch")
    return total, digest.hexdigest()


def _representation_class(suffix: str) -> str:
    if suffix in NATIVE_MICROSCOPY_SUFFIXES:
        return "native_microscopy_container"
    if suffix in LOSSLESS_RASTER_SUFFIXES:
        return "lossless_or_lossless_capable_raster_export"
    if suffix in RENDERED_RASTER_SUFFIXES:
        return "rendered_raster"
    if suffix in {".txt", ".csv", ".json", ".xml", ".md", ".pdf", ".docx", ".xlsx"}:
        return "metadata_or_document"
    return "other_or_unresolved"


def _role_cues(path: str) -> list[str]:
    lower = path.casefold()
    cues: list[str] = []
    if "saed" in lower or "diffraction" in lower or "diff" in lower:
        cues.append("saed_or_diffraction_name_cue")
    if "hrtem" in lower or "high resolution" in lower:
        cues.append("hrtem_name_cue")
    elif "tem" in lower:
        cues.append("tem_name_cue")
    if "beam" in lower and "damage" in lower:
        cues.append("beam_damage_name_cue")
    if "calib" in lower or "camera" in lower or "center" in lower or "centre" in lower:
        cues.append("calibration_or_centre_name_cue")
    return cues


def inspect_zip(
    path: Path,
    source_name: str,
    limits: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_compressed = 0
    total_uncompressed = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > limits["max_members_per_archive"]:
            raise FhiCo3O4AuditError(f"too many members in {source_name}")
        for info in infos:
            normalized = _safe_member_name(info.filename)
            if not normalized:
                continue
            if normalized in seen:
                raise FhiCo3O4AuditError(f"duplicate archive path: {normalized}")
            seen.add(normalized)
            if _is_symlink(info):
                raise FhiCo3O4AuditError(f"symlink member: {normalized}")
            if info.flag_bits & 0x1:
                raise FhiCo3O4AuditError(f"encrypted member: {normalized}")
            if info.compress_type not in SUPPORTED_COMPRESSION:
                raise FhiCo3O4AuditError(f"unsupported compression: {normalized}")
            if info.file_size > limits["max_single_member_bytes"]:
                raise FhiCo3O4AuditError(f"oversized member: {normalized}")
            total_compressed += info.compress_size
            total_uncompressed += info.file_size
            if total_uncompressed > limits["max_total_uncompressed_bytes_per_archive"]:
                raise FhiCo3O4AuditError(f"archive expands beyond limit: {source_name}")
            if info.file_size / max(info.compress_size, 1) > limits[
                "max_compression_ratio"
            ]:
                raise FhiCo3O4AuditError(f"compression ratio exceeds limit: {normalized}")
        for info in infos:
            normalized = _safe_member_name(info.filename)
            if not normalized:
                continue
            with archive.open(info, "r") as handle:
                observed_bytes, sha256 = _hash_member(handle, info.file_size)
            suffix = PurePosixPath(normalized).suffix.casefold()
            rows.append(
                {
                    "source_archive": source_name,
                    "member_path": normalized,
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": observed_bytes,
                    "compression_ratio": observed_bytes / max(info.compress_size, 1),
                    "crc32": f"{info.CRC:08x}",
                    "sha256": sha256,
                    "suffix": suffix,
                    "representation_class": _representation_class(suffix),
                    "role_cues": _role_cues(normalized),
                }
            )
    return rows, {
        "member_count": len(rows),
        "total_compressed_bytes": total_compressed,
        "total_uncompressed_bytes": total_uncompressed,
        "overall_compression_ratio": total_uncompressed / max(total_compressed, 1),
        "member_hashing_complete": True,
        "crc_verification_complete": True,
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_probe_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "name",
        "declared_role",
        "declared_size",
        "requested_url",
        "final_url",
        "http_status",
        "content_type",
        "content_length_header",
        "content_disposition",
        "sampled_bytes",
        "state",
        "authentication_required",
        "direct_zip_magic_confirmed",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_member_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "source_archive",
        "member_path",
        "compressed_bytes",
        "uncompressed_bytes",
        "compression_ratio",
        "crc32",
        "sha256",
        "suffix",
        "representation_class",
        "role_cues",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "role_cues": "|".join(row["role_cues"])})


def _manifest(root: Path, artifacts: list[Path]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "case_id": "fhi_co3o4_tem_saed_source_audit",
        "artifact_count": len(artifacts),
        "artifacts": [
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _hash_file(path),
            }
            for path in artifacts
        ],
    }


def _report(summary: dict[str, Any]) -> str:
    target_lines = "\n".join(
        f"- `{item['name']}`: `{item['state']}`; final path "
        f"`{urllib.parse.urlparse(item['final_url']).path}`"
        for item in summary["download_probes"]
    )
    return f"""# FHI Co3O4 TEM/SAED source audit

## Result

- Status: `{summary['status']}`
- Evidence level: **Diagnostic**
- Record: `{summary['record']['record_id']}`
- Sample number: `{summary['record']['sample_number']}`
- Anonymous source download available: **{str(summary['anonymous_source_download_available']).lower()}**
- External-validation ready: **no**

## Download probes

{target_lines}

## Scientific closeout

The exact-material institutional record and its public metadata are supported. The record page labels the entry `Open Access`, but the observed anonymous file requests redirect to a login page. Therefore archive bytes, member identities, representations, checksums and calibration metadata are not verified by this audit.

No credentials were supplied or guessed. No source files were retained, and no image preprocessing, annotation, model inference, parameter selection or model retraining was performed. Independent TEM performance, calibrated SAED accuracy, phase indexing and engineering readiness remain inconclusive.
"""


def run_audit(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    if output_dir.exists():
        if output_dir.is_symlink() or any(output_dir.iterdir()):
            raise FhiCo3O4AuditError("output directory must be absent or empty")
        output_dir.rmdir()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        html_text = _fetch_text(config["source"]["record_url"])
        links, record = verify_record(config, html_text)
        probes: list[dict[str, Any]] = []
        for target in config["source"]["target_files"]:
            probes.append(
                {
                    "name": target["name"],
                    "declared_role": target["declared_role"],
                    "declared_size": target["declared_size"],
                    **probe_download(links[target["name"]]),
                }
            )

        auth_blocked = all(item["authentication_required"] for item in probes)
        direct_available = all(item["state"] == "direct_zip_available" for item in probes)
        if not auth_blocked and not direct_available:
            states = ", ".join(sorted({str(item["state"]) for item in probes}))
            raise FhiCo3O4AuditError(f"download probes are inconsistent or unsafe: {states}")

        archive_rows: list[dict[str, Any]] = []
        member_rows: list[dict[str, Any]] = []
        if direct_available:
            with tempfile.TemporaryDirectory(prefix="fhi-source-") as temp_name:
                source_root = Path(temp_name)
                for target in config["source"]["target_files"]:
                    archive_path = source_root / target["name"]
                    identity = _stream_download(
                        links[target["name"]],
                        archive_path,
                        max_bytes=target["max_download_bytes"],
                    )
                    rows, stats = inspect_zip(
                        archive_path,
                        target["name"],
                        config["limits"],
                    )
                    member_rows.extend(rows)
                    archive_rows.append(
                        {
                            "name": target["name"],
                            "declared_role": target["declared_role"],
                            "declared_size": target["declared_size"],
                            **identity,
                            **stats,
                        }
                    )

        summary = {
            "schema_version": "1.0",
            "case_id": config["case_id"],
            "audit_date": config["audit_date"],
            "status": RESULT_AVAILABLE if direct_available else RESULT_AUTH_BLOCKED,
            "record": record,
            "download_probes": probes,
            "anonymous_source_download_available": direct_available,
            "archives": archive_rows,
            "total_member_count": len(member_rows),
            "metadata_quality_flags": [
                "The institutional record page displays Open Access while both observed anonymous file requests redirect to /login."
            ]
            if auth_blocked
            else [],
            "evidence_assessment": {
                "institutional_record_identity": "Supported",
                "exact_co3o4_material_context": "Supported",
                "anonymous_public_downloadability": (
                    "Unsupported" if auth_blocked else "Supported"
                ),
                "archive_and_member_identity": (
                    "Inconclusive" if auth_blocked else "Supported"
                ),
                "independent_tem_segmentation_validation": "Inconclusive",
                "calibrated_static_saed_validation": "Inconclusive",
            },
            "processing": {
                "credentials_supplied_or_guessed": False,
                "source_files_retained": False,
                "pixels_extracted_or_modified": False,
                "preprocessing_performed": False,
                "annotations_created": False,
                "model_inference_performed": False,
                "parameter_selection_performed": False,
                "model_retraining_performed": False,
            },
            "readiness": {
                "external_validation_ready": False,
                "engineering_decision_ready": False,
                "allowed_use": [
                    "record-level source triage",
                    "authentication-blocker evidence",
                    "author or repository access request specification",
                ]
                if auth_blocked
                else [
                    "checksum-bound observed-source snapshot",
                    "archive and representation diagnostics",
                    "metadata-gap assessment",
                ],
            },
            "unresolved": [
                "anonymous or explicitly authorized source access",
                "source-authoritative archive checksums or versioned manifest",
                "member-level sample and acquisition identifiers",
                "independence and minimum count of samples and acquisitions",
                "pattern-specific centre and reciprocal calibration",
                "data-specific reuse authorization",
                "independent blinded TEM segmentation labels",
                "verified non-use in analyzer development and selection",
            ],
        }

        summary_path = stage / "fhi_co3o4_tem_saed_audit_summary.json"
        probe_path = stage / "fhi_co3o4_tem_saed_download_probe.csv"
        report_path = stage / "fhi_co3o4_tem_saed_audit_report.md"
        member_path = stage / "fhi_co3o4_tem_saed_member_inventory.csv"
        manifest_path = stage / "fhi_co3o4_tem_saed_audit_manifest.json"
        _write_json(summary_path, summary)
        _write_probe_csv(probe_path, probes)
        report_path.write_text(_report(summary), encoding="utf-8")
        artifacts = [summary_path, probe_path, report_path]
        if member_rows:
            _write_member_csv(member_path, member_rows)
            artifacts.append(member_path)
        _write_json(manifest_path, _manifest(stage, artifacts))
        leaked = [
            path
            for path in stage.rglob("*")
            if path.is_file() and path.suffix.casefold() in FORBIDDEN_FINAL_SUFFIXES
        ]
        if leaked:
            raise FhiCo3O4AuditError("source-like files leaked into final evidence")
        stage.rename(output_dir)
        return summary
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the FHI exact-material Co3O4 TEM/HRTEM/SAED record, "
            "recording authentication blockers without bypassing access controls."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_audit(args.config, args.output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
