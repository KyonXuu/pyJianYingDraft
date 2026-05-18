import json
import uuid

import pyJianYingDraft as draft


def _make_video_material(name: str) -> draft.VideoMaterial:
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
    material.matting = draft.VideoMaterialMatting()
    return material


def test_compose_segments_exports_combination_material() -> None:
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
    assert exported["materials"]["videos"][0]["material_name"] == "复合片段1"
    assert exported["materials"]["videos"][0]["extra_type_option"] == 2
    assert video_segments[0]["material_id"] == exported["materials"]["videos"][0]["id"]
    assert exported["materials"]["drafts"][0]["id"] in video_segments[0]["extra_material_refs"]

    nested = exported["materials"]["drafts"][0]["draft"]
    nested_segments = [
        segment
        for track in nested["tracks"]
        if track["type"] == "video"
        for segment in track["segments"]
    ]
    assert [segment["target_timerange"]["start"] for segment in nested_segments] == [
        0,
        10_000_000,
        20_000_000,
    ]
    assert len(nested["materials"]["videos"]) == 3
    assert {
        material["matting"]["flag"]
        for material in nested["materials"]["videos"]
    } == {3}
