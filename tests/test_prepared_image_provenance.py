import pytest

from runners.prepared_image_provenance import require_image_provenance


def test_changed_caldera_input_requires_caldera_image_rebuild() -> None:
    previous_images = {
        "caldera": "a" * 64,
        "attacker": "b" * 64,
        "target-linux-1": "c" * 64,
    }
    previous_inputs = {"lab/vagrant/shared/caldera.sh": "d" * 64}
    current_inputs = {"lab/vagrant/shared/caldera.sh": "e" * 64}

    with pytest.raises(ValueError, match="caldera"):
        require_image_provenance(
            previous_inputs, current_inputs, previous_images, previous_images
        )

    rebuilt_caldera = {**previous_images, "caldera": "f" * 64}
    require_image_provenance(
        previous_inputs, current_inputs, previous_images, rebuilt_caldera
    )

    rebuilt_attacker = {**previous_images, "attacker": "f" * 64}
    with pytest.raises(ValueError, match="caldera"):
        require_image_provenance(
            previous_inputs, current_inputs, previous_images, rebuilt_attacker
        )


def test_shared_input_change_requires_all_role_images() -> None:
    images = {role: role for role in ("caldera", "attacker", "target-linux-1")}
    with pytest.raises(ValueError, match="attacker, caldera, target-linux-1"):
        require_image_provenance(
            {"lab/vagrant/shared/base.sh": "old"},
            {"lab/vagrant/shared/base.sh": "new"},
            images,
            images,
        )


def test_unchanged_inputs_need_no_rebuild() -> None:
    images = {role: role for role in ("caldera", "attacker", "target-linux-1")}
    require_image_provenance({}, {}, images, images)
