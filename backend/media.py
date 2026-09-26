from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from backend.config import Settings
from backend.schemas import SpeechSegment, TimedSceneContext

DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
PTS_PATTERN = re.compile(r"pts_time[:=](\d+(?:\.\d+)?)")
SCORE_PATTERN = re.compile(r"lavfi\.scene_score=(\d+(?:\.\d+)?)")
SILENCE_START_PATTERN = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
SILENCE_END_PATTERN = re.compile(r"silence_end:\s*(\d+(?:\.\d+)?)")
SRT_TIME_PATTERN = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
SCENE_CONTEXT_LIST = TypeAdapter(list[TimedSceneContext])


class MediaProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class SceneCut:
    timestamp: float
    score: float


@dataclass(frozen=True)
class SilenceInterval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MediaProcessingError(f"Media command failed: {error}") from error
    if completed.returncode != 0:
        detail = "\n".join(completed.stderr.splitlines()[-8:])
        raise MediaProcessingError(detail or "FFmpeg returned a non-zero exit code")
    return completed


def assert_media_tools(settings: Settings) -> None:
    if shutil.which(settings.ffmpeg_binary) is None:
        raise MediaProcessingError("ffmpeg is not installed")


def probe_duration(path: Path, settings: Settings) -> float:
    if settings.ffprobe_binary:
        completed = _run(
            [
                settings.ffprobe_binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            timeout=60,
        )
        try:
            duration = float(json.loads(completed.stdout)["format"]["duration"])
            if duration > 0:
                return duration
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    completed = subprocess.run(
        [settings.ffmpeg_binary, "-hide_banner", "-nostdin", "-i", str(path)],
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    match = DURATION_PATTERN.search(completed.stderr)
    if not match:
        raise MediaProcessingError("Unable to determine video duration")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0:
        raise MediaProcessingError("Video duration must be greater than zero")
    return duration


def detect_scene_cuts(path: Path, settings: Settings) -> list[SceneCut]:
    filter_graph = (
        f"select=gt(scene\\,{settings.scene_threshold}),metadata=print:file=-"
    )
    completed = _run(
        [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-an",
            "-filter:v",
            filter_graph,
            "-vsync",
            "vfr",
            "-f",
            "null",
            "-",
        ],
        timeout=settings.max_analysis_seconds,
    )

    cuts: list[SceneCut] = []
    timestamp: float | None = None
    for line in completed.stdout.splitlines():
        timestamp_match = PTS_PATTERN.search(line)
        if timestamp_match:
            timestamp = float(timestamp_match.group(1))
        score_match = SCORE_PATTERN.search(line)
        if score_match and timestamp is not None:
            cuts.append(
                SceneCut(timestamp=timestamp, score=float(score_match.group(1)))
            )
            timestamp = None
    return merge_nearby_cuts(cuts)


def merge_nearby_cuts(
    cuts: list[SceneCut], minimum_scene_seconds: float = 2.5
) -> list[SceneCut]:
    merged: list[SceneCut] = []
    for cut in sorted(cuts, key=lambda item: item.timestamp):
        if not merged or cut.timestamp - merged[-1].timestamp >= minimum_scene_seconds:
            merged.append(cut)
        elif cut.score > merged[-1].score:
            merged[-1] = cut
    return merged


def normalise_scene_change(score: float, detection_threshold: float) -> float:
    strong_cut_score = max(detection_threshold * 2, 0.01)
    return max(0.0, min(1.0, score / strong_cut_score))


def detect_silences(
    path: Path, duration: float, settings: Settings
) -> list[SilenceInterval]:
    completed = _run(
        [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-vn",
            "-af",
            "silencedetect=noise=-34dB:d=0.25",
            "-f",
            "null",
            "-",
        ],
        timeout=settings.max_analysis_seconds,
    )
    intervals: list[SilenceInterval] = []
    current_start: float | None = None
    for line in completed.stderr.splitlines():
        start_match = SILENCE_START_PATTERN.search(line)
        if start_match:
            current_start = max(0.0, float(start_match.group(1)))
        end_match = SILENCE_END_PATTERN.search(line)
        if end_match:
            end = min(duration, float(end_match.group(1)))
            start = current_start if current_start is not None else 0.0
            if end > start:
                intervals.append(SilenceInterval(start=start, end=end))
            current_start = None
    if current_start is not None and duration > current_start:
        intervals.append(SilenceInterval(start=current_start, end=duration))
    return intervals


def silence_near(
    timestamp: float,
    intervals: list[SilenceInterval],
    tolerance: float = 0.45,
) -> float:
    eligible = [
        interval
        for interval in intervals
        if interval.start - tolerance <= timestamp <= interval.end + tolerance
    ]
    if not eligible:
        return 0.0
    return max(interval.duration for interval in eligible)


def extract_frame(
    path: Path, timestamp: float, output_path: Path, settings: Settings
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=512:-2",
            "-q:v",
            "3",
            "-y",
            str(output_path),
        ],
        timeout=120,
    )
    return output_path


def parse_sidecar_subtitles(video_path: Path) -> list[SpeechSegment]:
    subtitle_path = video_path.with_suffix(".srt")
    if not subtitle_path.exists():
        return []
    blocks = re.split(r"\n\s*\n", subtitle_path.read_text(encoding="utf-8").strip())
    segments: list[SpeechSegment] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line), None
        )
        if timing_index is None:
            continue
        match = SRT_TIME_PATTERN.search(lines[timing_index])
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        text = " ".join(lines[timing_index + 1 :])
        if end > start:
            segments.append(SpeechSegment(start=start, end=end, text=text))
    return segments


def load_timed_scene_contexts(video_path: Path) -> list[TimedSceneContext]:
    context_path = video_path.with_suffix(".scenes.json")
    if not context_path.is_file():
        return []
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
        contexts = sorted(
            SCENE_CONTEXT_LIST.validate_python(payload),
            key=lambda item: item.start,
        )
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise MediaProcessingError(f"Invalid scene context sidecar: {error}") from error
    if any(
        current.start < previous.end
        for previous, current in zip(contexts, contexts[1:], strict=False)
    ):
        raise MediaProcessingError("Scene context sidecar intervals must not overlap")
    return contexts
