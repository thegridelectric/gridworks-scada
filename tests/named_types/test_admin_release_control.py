"""Tests admin.release.control type, version 000"""

from gwsproto.named_types import AdminReleaseControl


def test_admin_release_control_generated() -> None:
    d = {
        "TypeName": "admin.release.control",
        "Version": "000",
    }

    d2 = AdminReleaseControl.model_validate(d).model_dump(exclude_none=True)

    assert d2 == d
