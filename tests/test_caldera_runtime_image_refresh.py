"""A runtime refresh must select a new image without rewriting old aliases."""

from pathlib import Path

import pytest

from scripts import freeze_prepared_c0045_runtime as freezer


@pytest.mark.parametrize('name', ('../escape', '/absolute/path', 'unqualified',
                                  'owner/../../escape', 'https://example.test/box'))
def test_prepared_box_rejects_non_alias_paths(name):
    with pytest.raises(ValueError, match='namespace/name'):
        freezer._box_root(name)


def test_new_caldera_alias_has_a_separate_box_root(tmp_path, monkeypatch):
    monkeypatch.setenv('VAGRANT_HOME', str(tmp_path))
    root = freezer._box_root('sticks/caldera-python-lock-arm64')
    assert root == tmp_path / 'boxes/sticks-VAGRANTSLASH-caldera-python-lock-arm64/0/arm64/libvirt'
    assert root != freezer._box_root(freezer.ROLE_BOX_NAMES['caldera'])


def test_freeze_forwards_only_caldera_alias_override(tmp_path, monkeypatch):
    captured = {}

    def record_inputs(inventory_dir, manifest_version, *, box_names):
        captured.update(box_names)
        raise ValueError('stop before writing frozen evidence')

    monkeypatch.setattr(freezer, '_prepared_manifest', record_inputs)
    with pytest.raises(ValueError, match='stop before writing'):
        freezer.freeze(Path(tmp_path), caldera_box_name='sticks/caldera-python-lock-arm64')
    assert captured['caldera'] == 'sticks/caldera-python-lock-arm64'
    assert captured['attacker'] == freezer.ROLE_BOX_NAMES['attacker']
    assert captured['target-linux-1'] == freezer.ROLE_BOX_NAMES['target-linux-1']
