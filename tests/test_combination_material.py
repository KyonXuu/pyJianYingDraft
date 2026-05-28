import json
import uuid

import pytest
import pyJianYingDraft as draft


def _make_video_material(name: str, *, smart_matting: bool = False) -> draft.VideoMaterial:
    material = draft.VideoMaterial.__new__(draft.VideoMaterial)
    material.material_id = uuid.uuid4().hex
    material.local_material_id = ""
    material.material_name = name
    material.path = f"C:/fake/{name}"
    material.duration = 10_000_000
    material.width = 1080
    material.height = 1920
    material.crop_settings = draft.CropSettings()
    material.material_type = "video"
    material.matting = draft.VideoMaterialMatting() if smart_matting else None
    return material


def test_compose_segments_exports_combination_material() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True)
    script.add_track(draft.TrackType.video, "video", absolute_index=4)

    for index in range(3):
        segment = draft.VideoSegment(
            _make_video_material(f"clip_{index}.mp4"),
            draft.Timerange(index * 10_000_000, 10_000_000),
            source_timerange=draft.Timerange(0, 10_000_000),
        )
        script.add_segment(segment, "video")

    combination_segment = script.compose_segments("video", name="复合片段1")
    exported = json.loads(script.dumps())

    video_segments = [
        segment
        for track in exported["tracks"]
        if track["type"] == "video"
        for segment in track["segments"]
    ]
    assert len(video_segments) == 1
    assert video_segments[0]["id"] == combination_segment.segment_id

    assert len(exported["materials"]["drafts"]) == 1
    assert len(exported["materials"]["videos"]) == 1
    assert exported["config"]["combination_max_index"] == 2
    assert exported["materials"]["videos"][0]["material_name"] == "复合片段1"
    assert exported["materials"]["videos"][0]["extra_type_option"] == 2
    assert video_segments[0]["material_id"] == exported["materials"]["videos"][0]["id"]
    assert exported["materials"]["drafts"][0]["id"] in video_segments[0]["extra_material_refs"]

    nested = exported["materials"]["drafts"][0]["draft"]
    assert nested["render_index_track_mode_on"] is True
    nested_video_tracks = [
        track
        for track in nested["tracks"]
        if track["type"] == "video"
    ]
    assert len(nested_video_tracks) == 2
    assert nested_video_tracks[0]["flag"] == 0
    assert nested_video_tracks[0]["is_default_name"] is True
    assert nested_video_tracks[0]["name"] == ""
    assert nested_video_tracks[0]["segments"] == []
    assert nested_video_tracks[1]["flag"] == 2
    assert nested_video_tracks[1]["is_default_name"] is True
    assert nested_video_tracks[1]["name"] == ""

    nested_segments = [
        segment
        for segment in nested_video_tracks[1]["segments"]
    ]
    assert [segment["target_timerange"]["start"] for segment in nested_segments] == [
        0,
        10_000_000,
        20_000_000,
    ]
    assert {segment["track_render_index"] for segment in nested_segments} == {4}
    assert len(nested["materials"]["videos"]) == 3
    assert {
        material.get("matting", {}).get("flag", 0)
        for material in nested["materials"]["videos"]
    } == {0}


def test_compound_segment_can_enable_smart_matting_on_outer_material() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True)
    script.add_track(draft.TrackType.video, "video")

    for index in range(3):
        segment = draft.VideoSegment(
            _make_video_material(f"clip_{index}.mp4"),
            draft.Timerange(index * 10_000_000, 10_000_000),
            source_timerange=draft.Timerange(0, 10_000_000),
        )
        script.add_segment(segment, "video")

    combination_segment = script.compose_segments("video", name="复合片段1")
    returned = combination_segment.add_smart_matting()
    exported = json.loads(script.dumps())

    assert returned is combination_segment
    assert len(exported["materials"]["videos"]) == 1
    assert exported["materials"]["videos"][0]["matting"]["flag"] == 3
    assert exported["materials"]["videos"][0]["matting"]["path"] == ""

    nested = exported["materials"]["drafts"][0]["draft"]
    assert {
        material.get("matting", {}).get("flag", 0)
        for material in nested["materials"]["videos"]
    } == {0}


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
    segment = draft.VideoSegment(
        _make_video_material("clip.mp4"),
        draft.Timerange(0, 10_000_000),
        source_timerange=draft.Timerange(0, 10_000_000),
    )

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
    segment = draft.VideoSegment(
        _make_video_material("clip.mp4"),
        draft.Timerange(0, 10_000_000),
        source_timerange=draft.Timerange(0, 10_000_000),
    )

    segment.add_smart_matting(
        path="##_draftpath_placeholder_##/matting/cache",
        reuse_cache=True,
    )

    assert (
        segment.material_instance.matting.export_json()["path"]
        == "##_draftpath_placeholder_##/matting/cache"
    )


def test_combination_material_drops_matting_cache_by_default() -> None:
    matting = draft.VideoMaterialMatting(
        path="##_draftpath_placeholder_##/matting/cache",
        has_use_quick_brush=True,
        interactive_time=[100],
        strokes=[{"x": 1}],
        reuse_cache=True,
    )
    combination = draft.CombinationMaterial(
        {"tracks": [], "materials": {"videos": []}},
        name="复合片段1",
        duration=10_000_000,
        width=1080,
        height=1920,
        matting=matting,
    )

    exported = combination.export_video_json()

    assert exported["matting"] == {
        "flag": 3,
        "has_use_quick_brush": False,
        "has_use_quick_eraser": False,
        "interactiveTime": [],
        "path": "",
        "strokes": [],
    }


def test_combination_material_can_reuse_matting_cache_explicitly() -> None:
    matting = draft.VideoMaterialMatting(
        path="##_draftpath_placeholder_##/matting/cache",
        strokes=[{"x": 1}],
        reuse_cache=True,
    )
    combination = draft.CombinationMaterial(
        {"tracks": [], "materials": {"videos": []}},
        name="复合片段1",
        duration=10_000_000,
        width=1080,
        height=1920,
        matting=matting,
        reuse_matting_cache=True,
    )

    assert (
        combination.export_video_json()["matting"]["path"]
        == "##_draftpath_placeholder_##/matting/cache"
    )
