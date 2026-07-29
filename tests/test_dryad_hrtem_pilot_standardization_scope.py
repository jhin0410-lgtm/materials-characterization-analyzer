from pathlib import Path

import h5py
import numpy as np

from mca.tem_external_validation_pilot_contract import load_config
from mca.tem_external_validation_pilot_engine import inspect_pair

CONFIG = Path("case_studies/dryad_hrtem_pilot_pair_audit/case_config.json")


def test_patch_offsets_and_scales_are_diagnostic_not_fatal(tmp_path: Path) -> None:
    config = load_config(CONFIG)
    rng = np.random.default_rng(7)
    base = rng.normal(size=(512, 512))
    images = np.stack(
        [
            (base - base.mean()) / base.std(),
            2.5 * base + 4.0,
        ]
    )
    labels = np.zeros((2, 512, 512), dtype=np.uint8)
    labels[:, 100:200, 100:200] = 1
    image_path = tmp_path / "images.h5"
    label_path = tmp_path / "labels.h5"
    with h5py.File(image_path, "w") as handle:
        handle.create_dataset("images", data=images)
    with h5py.File(label_path, "w") as handle:
        handle.create_dataset("labels", data=labels)

    result = inspect_pair(image_path, label_path, config)

    assert result["patch_count"] == 2
    assert result["source_reported_standardization_scope"] == (
        "4096x4096_parent_image_before_512x512_patching"
    )
    assert not result["patch_level_zero_mean_unit_std_required"]
    assert result["patch_level_zero_mean_unit_std_count"] == 1
    assert result["patch_mean_max"] > 3.0
    assert result["patch_std_max"] > 2.0
