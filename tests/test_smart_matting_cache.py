from types import SimpleNamespace

import pytest
import pyJianYingDraft as draft


def test_smart_matting_cache_requires_explicit_reuse() -> None:
    with pytest.raises(ValueError, match="reuse_cache=True"):
        draft.VideoMaterialMatting(path="##_draftpath_placeholder_##/matting/cache")

    with pytest.raises(ValueError, match="reuse_cache=True"):
        draft.VideoMaterialMatting(
            has_use_quick_brush=True,
            interactive_time=[100],
            strokes=[{"x": 1}],
        )


def test_smart_matting_cache_can_be_reused_explicitly() -> None:
    matting = draft.VideoMaterialMatting(
        path="##_draftpath_placeholder_##/matting/cache",
        has_use_quick_brush=True,
        has_use_quick_eraser=True,
        interactive_time=[100],
        strokes=[{"x": 1}],
        reuse_cache=True,
    )

    assert matting.export_json() == {
        "flag": 3,
        "has_use_quick_brush": True,
        "has_use_quick_eraser": True,
        "interactiveTime": [100],
        "path": "##_draftpath_placeholder_##/matting/cache",
        "strokes": [{"x": 1}],
    }


def test_add_smart_matting_defaults_to_fresh_cache() -> None:
    segment = draft.VideoSegment.__new__(draft.VideoSegment)
    segment.material_instance = SimpleNamespace(matting=None)

    with pytest.raises(ValueError, match="reuse_cache=True"):
        segment.add_smart_matting(
            path="##_draftpath_placeholder_##/matting/cache",
        )

    segment.add_smart_matting()

    assert segment.material_instance.matting.export_json() == {
        "flag": 3,
        "has_use_quick_brush": False,
        "has_use_quick_eraser": False,
        "interactiveTime": [],
        "strokes": [],
    }


def test_add_smart_matting_can_reuse_cache_explicitly() -> None:
    segment = draft.VideoSegment.__new__(draft.VideoSegment)
    segment.material_instance = SimpleNamespace(matting=None)

    segment.add_smart_matting(
        path="##_draftpath_placeholder_##/matting/cache",
        reuse_cache=True,
    )

    assert (
        segment.material_instance.matting.export_json()["path"]
        == "##_draftpath_placeholder_##/matting/cache"
    )
