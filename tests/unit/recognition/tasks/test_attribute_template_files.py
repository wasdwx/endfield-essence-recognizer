import os

import pytest

from endfield_essence_recognizer.core.path import get_root_dir

if os.getenv("GITHUB_ACTIONS") == "true":
    # importing endfield_essence_recognizer.core.recognition.tasks.attribute will fail in CI
    pytest.skip("Skipping test in CI environment", allow_module_level=True)

_DATA_ROOT = get_root_dir() / "resources" / "data" / "v2"
_REQUIRED_FILES = (
    "Weapon.json",
    "EssenceStat.json",
    "WeaponType.json",
    "RarityColor.json",
)
if any(not (_DATA_ROOT / name).is_file() for name in _REQUIRED_FILES):
    pytest.skip(
        "Skipping test because static game data files are unavailable.",
        allow_module_level=True,
    )


def get_attribute_templates():
    from endfield_essence_recognizer.core.recognition.tasks.attribute import (
        build_attribute_profile,
    )
    from endfield_essence_recognizer.game_data.static_game_data import StaticGameData

    static_game_data = StaticGameData(_DATA_ROOT)
    profile = build_attribute_profile(static_game_data)
    return profile.templates


@pytest.mark.parametrize(
    "template_descriptor", get_attribute_templates(), ids=lambda d: d.label
)
@pytest.mark.skip_in_ci(
    reason="CI environment does not include json files."
    " Currently the build_attribute_profile function depends on json files."
)
def test_attribute_template_file_exists(template_descriptor):
    """
    Test that each attribute template file exists in the repository.
    """
    assert template_descriptor.path.joinpath().exists(), (
        f"Template file for {template_descriptor.label} does not exist at {template_descriptor.path}"
    )
