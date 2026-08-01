from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "inspect_mendeley_microscopy_members.py"


def _module():
    spec = importlib.util.spec_from_file_location("mendeley_member_inspection", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pillow_tag_info_is_normalized_to_stable_string() -> None:
    module = _module()
    assert module._tag_name(256) == "ImageWidth"
    assert module._tag_name(257) == "ImageLength"
    assert isinstance(module._tag_name(65_000), str)
