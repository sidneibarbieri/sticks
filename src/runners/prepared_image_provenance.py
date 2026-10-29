"""Guard the provenance of prepared role images during a runtime refresh."""

from collections.abc import Mapping


ROLES = frozenset({"caldera", "attacker", "target-linux-1"})
ROLE_SPECIFIC_INPUTS = {
    "lab/vagrant/shared/caldera.sh": "caldera",
    "lab/vagrant/shared/caldera-runtime-requirements.txt": "caldera",
    "lab/vagrant/shared/attacker.sh": "attacker",
    "lab/vagrant/shared/target.sh": "target-linux-1",
}


def require_image_provenance(
    previous_inputs: Mapping[str, str],
    current_inputs: Mapping[str, str],
    previous_images: Mapping[str, str],
    current_images: Mapping[str, str],
) -> None:
    """Reject provenance changes that were not followed by a role-image rebuild."""
    if set(previous_images) != ROLES or set(current_images) != ROLES:
        raise ValueError("Prepared runtime must contain all three roles.")
    changed_inputs = {
        path
        for path in set(previous_inputs) | set(current_inputs)
        if previous_inputs.get(path) != current_inputs.get(path)
    }
    affected_roles = {
        ROLE_SPECIFIC_INPUTS[path]
        for path in changed_inputs
        if path in ROLE_SPECIFIC_INPUTS
    }
    if any(path not in ROLE_SPECIFIC_INPUTS for path in changed_inputs):
        affected_roles.update(ROLES)
    stale_roles = {
        role
        for role in affected_roles
        if previous_images[role] == current_images[role]
    }
    if stale_roles:
        raise ValueError(
            "Provisioning inputs changed without rebuilt images for "
            f"{', '.join(sorted(stale_roles))}."
        )
