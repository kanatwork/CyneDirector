"""Clip-relative sampled scene times; never substitute equal-duration scenes."""
import math


def sampled_time(frame, fps, milliseconds, previous=None):
    pts = milliseconds / 1000.0
    if math.isfinite(pts) and pts >= 0 and (previous is None or pts > previous):
        return pts, "decoder_pts"
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("No usable decoder timestamp or frame rate")
    fallback = frame / fps
    if previous is not None and fallback <= previous:
        raise ValueError("Non-monotonic source timestamps")
    return fallback, "estimated_cfr"


def scene_segments(scenes, duration, sample_interval):
    result = []
    for scene in scenes:
        start, end = scene["start"], scene.get("end", duration)
        if not 0 <= start < end <= duration:
            raise ValueError("Invalid sampled scene interval")
        result.append({"start": start, "end": end, "duration": end-start,
                       "representative_timestamp": scene.get("frame_time"),
                       "representative_frame": scene.get("frame_num"),
                       "cut_lower_bound": scene.get("cut_lower_bound", start),
                       "cut_upper_bound": start,
                       "precision": "sampled", "sample_interval": sample_interval,
                       "score": scene.get("score", 0),
                       "has_best_frame": scene.get("representative_available", scene.get("best_frame") is not None),
                       "frame_retained_for_caption": scene.get("best_frame") is not None})
    return result
