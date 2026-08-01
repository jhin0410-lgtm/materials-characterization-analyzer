from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path("scripts/resolve_dryad_pilot_file_metadata.py")


def _module():
    spec = importlib.util.spec_from_file_location("resolve_dryad", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _raw(path: Path, file_id: int, name: str, version_id: int = 247105) -> Path:
    payload = {
        "id": file_id,
        "path": name,
        "size": 3,
        "_links": {
            "stash:version": {"href": f"https://datadryad.org/api/v2/versions/{version_id}"},
            "stash:download": {"href": f"https://datadryad.org/api/v2/files/{file_id}/download"},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resolver_preserves_raw_responses_and_writes_separate_enriched_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    bindings = [
        (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5")),
        (2451482, _raw(tmp_path / "label.json", 2451482, "label.h5")),
        (2451515, _raw(tmp_path / "metadata.json", 2451515, "metadata.csv")),
    ]
    originals = {path: path.read_bytes() for _, path in bindings}
    version_url = "https://datadryad.org/api/v2/versions/247105"
    files_url = version_url + "/files"
    records = [
        {"id": file_id, "path": json.loads(path.read_text())["path"], "digest": "sha256:" + str(file_id).zfill(64)[-64:], "size": 3}
        for file_id, path in bindings
    ]
    responses = {
        version_url: {"doi": "10.7941/D1SP93", "_links": {"stash:files": {"href": files_url}}},
        files_url: {"files": records},
    }
    monkeypatch.setattr(module, "_fetch", lambda url, attempts=5: responses[url])
    output = tmp_path / "out"
    module.resolve("10.7941/D1SP93", 247105, bindings, output)
    for path, payload in originals.items():
        assert path.read_bytes() == payload
    for file_id, _ in bindings:
        enriched = json.loads((output / f"dryad-file-{file_id}-enriched.json").read_text())
        assert enriched["source_version_id"] == 247105
        assert enriched["dataset_doi"] == "10.7941/D1SP93"


def test_resolver_rejects_wrong_source_version_before_inventory_fetch(tmp_path: Path) -> None:
    module = _module()
    binding = (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5", 999999))
    with pytest.raises(ValueError, match="source-version mismatch"):
        module.resolve("10.7941/D1SP93", 247105, [binding], tmp_path / "out")


def test_resolver_rejects_wrong_dataset_doi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    binding = (2451485, _raw(tmp_path / "image.json", 2451485, "image.h5"))
    version_url = "https://datadryad.org/api/v2/versions/247105"
    monkeypatch.setattr(module, "_fetch", lambda url, attempts=5: {"doi": "10.0000/WRONG"})
    with pytest.raises(ValueError, match="dataset DOI mismatch"):
        module.resolve("10.7941/D1SP93", 247105, [binding], tmp_path / "out")
