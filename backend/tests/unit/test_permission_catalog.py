from app.core.permission_labels_fa import (
    PERMISSION_GROUP_LABELS_FA,
    PERMISSION_LABELS_FA,
)
from app.core.permissions import ALL_PERMISSIONS, PERMISSION_CATALOG


def test_permission_labels_cover_the_authorization_catalog_exactly():
    keys = {key for _, permissions in PERMISSION_CATALOG for key in permissions}
    assert keys == set(ALL_PERMISSIONS)
    assert set(PERMISSION_LABELS_FA) == keys
    assert set(PERMISSION_GROUP_LABELS_FA) == {group for group, _ in PERMISSION_CATALOG}


def test_every_permission_label_is_nonempty():
    assert all(PERMISSION_LABELS_FA.values())
    assert all(PERMISSION_GROUP_LABELS_FA.values())
