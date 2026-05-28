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


def _add_clip(script: draft.ScriptFile, track_name: str, name: str, start: int, duration: int) -> None:
    segment = draft.VideoSegment(
        _make_video_material(name),
        draft.Timerange(start, duration),
        source_timerange=draft.Timerange(0, duration),
    )
    script.add_segment(segment, track_name)


def test_compose_segments_exports_combination_material() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True)
    script.add_track(draft.TrackType.video, "video", absolute_index=4)

    for index in range(3):
        _add_clip(script, "video", f"clip_{index}.mp4", index * 10_000_000, 10_000_000)

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
    assert video_segments[0]["render_index"] == 0
    assert video_segments[0]["track_render_index"] == 0

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
    assert len(nested_video_tracks) == 1
    assert nested_video_tracks[0]["flag"] == 0
    assert nested_video_tracks[0]["is_default_name"] is True
    assert nested_video_tracks[0]["name"] == ""

    nested_segments = [
        segment
        for segment in nested_video_tracks[0]["segments"]
    ]
    assert [segment["target_timerange"]["start"] for segment in nested_segments] == [
        0,
        10_000_000,
        20_000_000,
    ]
    assert {segment["render_index"] for segment in nested_segments} == {0}
    assert {segment["track_render_index"] for segment in nested_segments} == {0}
    assert len(nested["materials"]["videos"]) == 3
    assert {
        material.get("matting", {}).get("flag", 0)
        for material in nested["materials"]["videos"]
    } == {0}


def test_compose_segments_matches_jianying_multitrack_render_indices() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True, enable_render_index_track_mode=True)
    for track_name, render_index in [
        ("video_r0", 0),
        ("video_r5", 5),
        ("video_r10", 10),
        ("video_r13", 13),
        ("抠像轨道", 14),
        ("video_r15", 15),
        ("数字人轨道", 15),
    ]:
        script.add_track(draft.TrackType.video, track_name, absolute_index=render_index)
        if track_name == "抠像轨道":
            for index in range(3):
                _add_clip(script, track_name, f"matting_{index}.mp4", index * 10_000_000, 10_000_000)
        else:
            _add_clip(script, track_name, f"{track_name}.mp4", 0, 10_000_000)

    script.compose_segments("抠像轨道", name="复合片段1")
    exported = json.loads(script.dumps())

    outer_compound = next(
        segment
        for track in exported["tracks"]
        if track["type"] == "video" and track["name"] == "抠像轨道"
        for segment in track["segments"]
    )
    assert outer_compound["render_index"] == 16
    assert outer_compound["track_render_index"] == 4

    nested = exported["materials"]["drafts"][0]["draft"]
    nested_content_track = [
        track
        for track in nested["tracks"]
        if track["type"] == "video" and len(track["segments"]) > 0
    ][0]
    assert nested_content_track["flag"] == 2
    assert {
        segment["render_index"]
        for segment in nested_content_track["segments"]
    } == {14}
    assert {
        segment["track_render_index"]
        for segment in nested_content_track["segments"]
    } == {4}


@pytest.mark.parametrize(
    (
        "tracks",
        "target_track",
        "expected_outer_render_index",
        "expected_track_render_index",
        "expected_nested_track_flags",
    ),
    [
        ([("target", 0), ("middle", 4), ("top", 15)], "target", 0, 0, [0]),
        ([("low", 0), ("target", 4), ("top", 15)], "target", 16, 1, [0, 2]),
        ([("low", 0), ("middle", 4), ("target", 15)], "target", 5, 2, [0, 2]),
        ([("low", 3), ("target", 20), ("top", 50)], "target", 51, 1, [0, 2]),
        ([("low", 0), ("target", 10), ("peer", 10), ("top", 12)], "target", 13, 1, [0, 2]),
    ],
)
def test_compose_segments_matches_jianying_manual_render_index_layouts(
    tracks: list[tuple[str, int]],
    target_track: str,
    expected_outer_render_index: int,
    expected_track_render_index: int,
    expected_nested_track_flags: list[int],
) -> None:
    script = draft.ScriptFile(1080, 1920, 30, True, enable_render_index_track_mode=True)
    for track_name, render_index in tracks:
        script.add_track(draft.TrackType.video, track_name, absolute_index=render_index)
        clip_count = 2 if track_name == target_track else 1
        for index in range(clip_count):
            _add_clip(script, track_name, f"{track_name}_{index}.mp4", index * 10_000_000, 10_000_000)

    target_render_index = dict(tracks)[target_track]
    script.compose_segments(target_track, name="复合片段1")
    exported = json.loads(script.dumps())

    outer_compound = next(
        segment
        for track in exported["tracks"]
        if track["type"] == "video" and track["name"] == target_track
        for segment in track["segments"]
    )
    assert outer_compound["render_index"] == expected_outer_render_index
    assert outer_compound["track_render_index"] == expected_track_render_index

    nested = exported["materials"]["drafts"][0]["draft"]
    nested_video_tracks = [
        track
        for track in nested["tracks"]
        if track["type"] == "video"
    ]
    assert [track["flag"] for track in nested_video_tracks] == expected_nested_track_flags

    nested_content_track = [
        track
        for track in nested_video_tracks
        if track["type"] == "video" and len(track["segments"]) > 0
    ][0]
    assert {
        segment["render_index"]
        for segment in nested_content_track["segments"]
    } == {target_render_index}
    assert {
        segment["track_render_index"]
        for segment in nested_content_track["segments"]
    } == {expected_track_render_index}


def test_compose_segments_matches_jianying_manual_nested_frame_layout() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True, enable_render_index_track_mode=True)
    script.add_track(draft.TrackType.video, "抠像轨道", absolute_index=14)

    ranges = [
        (10_066_666, 7_200_000, 7_200_000),
        (17_266_666, 5_400_000, 5_400_000),
        (22_666_666, 7_866_667, 7_866_667),
        (30_533_333, 6_333_333, 6_333_333),
        (54_000_000, 5_500_000, 5_500_000),
        (59_500_000, 6_166_666, 6_166_666),
        (79_400_000, 4_066_666, 4_067_000),
    ]
    for index, (start, target_duration, source_duration) in enumerate(ranges):
        material = _make_video_material(f"matting_{index}.mp4")
        material.duration = start + source_duration
        segment = draft.VideoSegment(
            material,
            draft.Timerange(start, target_duration),
            source_timerange=draft.Timerange(start, target_duration),
        )
        if source_duration != target_duration:
            segment.source_timerange.duration = source_duration
            segment.speed.speed = 1.0
        script.add_segment(segment, "抠像轨道")

    script.compose_segments("抠像轨道", name="复合片段1")
    exported = json.loads(script.dumps())
    nested = exported["materials"]["drafts"][0]["draft"]
    nested_content_track = [
        track
        for track in nested["tracks"]
        if track["type"] == "video" and len(track["segments"]) > 0
    ][0]
    nested_segments = nested_content_track["segments"]

    assert [segment["target_timerange"] for segment in nested_segments] == [
        {"start": 0, "duration": 7_200_000},
        {"start": 7_200_000, "duration": 5_400_000},
        {"start": 12_600_000, "duration": 7_866_666},
        {"start": 20_466_666, "duration": 6_333_334},
        {"start": 43_933_333, "duration": 5_500_000},
        {"start": 49_433_333, "duration": 6_166_667},
        {"start": 69_333_333, "duration": 4_066_667},
    ]
    assert nested_segments[-1]["source_timerange"] == {
        "start": 79_400_000,
        "duration": 4_067_000,
    }
    assert nested_segments[-1]["speed"] == 1.0


def test_video_track_export_matches_jianying_main_and_overlay_flags() -> None:
    script = draft.ScriptFile(1080, 1920, 30, True, enable_render_index_track_mode=True)
    for track_name, render_index in [
        ("main", 3),
        ("overlay", 20),
    ]:
        script.add_track(draft.TrackType.video, track_name, absolute_index=render_index)
        _add_clip(script, track_name, f"{track_name}.mp4", 0, 10_000_000)

    exported = json.loads(script.dumps())
    video_tracks = [track for track in exported["tracks"] if track["type"] == "video"]

    assert video_tracks[0]["name"] == "main"
    assert video_tracks[0]["flag"] == 0
    assert video_tracks[0]["segments"][0]["render_index"] == 0
    assert video_tracks[0]["segments"][0]["track_render_index"] == 0

    assert video_tracks[1]["name"] == "overlay"
    assert video_tracks[1]["flag"] == 2
    assert video_tracks[1]["segments"][0]["render_index"] == 20
    assert video_tracks[1]["segments"][0]["track_render_index"] == 1


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
