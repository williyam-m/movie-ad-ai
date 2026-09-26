from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.config import Settings

MEDIA_GENERATION_LOCK = threading.Lock()

SCENES: tuple[dict[str, Any], ...] = (
    {
        "title": "THE JOURNEY HOME",
        "color": "#061A2D",
        "frequency": 196,
        "duration": 14.0,
        "subtitle": "বাড়ি ফেরার পথে ট্রেনযাত্রা। A calm train journey home.",
    },
    {
        "title": "FAMILY REUNION",
        "color": "#E8C8A0",
        "frequency": 246,
        "duration": 14.0,
        "subtitle": "পরিবার বাড়িতে আবার একত্রিত হয়। A joyful family reunion at home.",
    },
    {
        "title": "DINNER TOGETHER",
        "color": "#7E1A12",
        "frequency": 294,
        "duration": 14.0,
        "subtitle": (
            "বন্ধুরা রান্নাঘরে একসঙ্গে খাবার রান্না করছে। "
            "Friends cook dinner together in the kitchen."
        ),
    },
    {
        "title": "A QUIET FAREWELL",
        "color": "#D8D8D8",
        "frequency": 164,
        "duration": 14.0,
        "subtitle": (
            "অন্ত্যেষ্টির পরে পরিবার শোক করছে। "
            "A family mourns quietly after a funeral."
        ),
    },
    {
        "title": "STARS AFTER RAIN",
        "color": "#08102D",
        "frequency": 330,
        "duration": 14.0,
        "subtitle": "তারাভরা রাতের আকাশ দেখা। Friends are stargazing under the night sky.",
    },
)


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, check=False, text=True)
    if completed.returncode != 0:
        detail = "\n".join(completed.stderr.splitlines()[-12:])
        raise RuntimeError(detail or "FFmpeg media generation failed")


def _font_path() -> Path | None:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    )
    return next((path for path in candidates if path.exists()), None)


def _video_filter(title: str) -> str:
    filters = [
        "drawbox=x=0:y=0:w=iw:h=12:color=white@0.16:t=fill",
        "drawbox=x=70:y=70:w=220:h=220:color=white@0.06:t=fill",
        "drawbox=x=iw-310:y=ih-190:w=240:h=120:color=black@0.15:t=fill",
    ]
    font_path = _font_path()
    if font_path:
        escaped_title = title.replace("'", "\\'").replace(":", "\\:")
        filters.append(
            "drawtext="
            f"fontfile='{font_path}':text='{escaped_title}':"
            "fontcolor=white:fontsize=34:x=70:y=h-105"
        )
        filters.append(
            "drawtext="
            f"fontfile='{font_path}':text='MOVIE AD AI DEMO':"
            "fontcolor=white@0.65:fontsize=13:x=72:y=h-62"
        )
    return ",".join(filters)


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _write_demo_subtitles(path: Path) -> None:
    blocks: list[str] = []
    cursor = 0.0
    for index, scene in enumerate(SCENES, start=1):
        start = cursor + 0.8
        end = cursor + float(scene["duration"]) - 1.25
        blocks.append(
            f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{scene['subtitle']}"
        )
        cursor += float(scene["duration"])
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _generate_atomically(output_path: Path, builder: Callable[[Path], None]) -> None:
    partial_path = output_path.with_name(
        f".{output_path.stem}.partial{output_path.suffix}"
    )
    partial_path.unlink(missing_ok=True)
    try:
        builder(partial_path)
        partial_path.replace(output_path)
    finally:
        partial_path.unlink(missing_ok=True)


def _build_demo_video(output_path: Path, settings: Settings) -> None:
    with tempfile.TemporaryDirectory(prefix="movie-ad-ai-demo-") as temporary:
        temporary_path = Path(temporary)
        segments: list[Path] = []
        for index, scene in enumerate(SCENES):
            segment_path = temporary_path / f"scene-{index:02}.mp4"
            duration = float(scene["duration"])
            sound_duration = duration - 1.2
            scene_filter = _video_filter(str(scene["title"]))
            _run(
                [
                    settings.ffmpeg_binary,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={scene['color']}:s=960x540:r=24:d={duration}",
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={scene['frequency']}:sample_rate=48000:duration={sound_duration}",
                    "-filter_complex",
                    f"[0:v]{scene_filter}[v];"
                    "[1:a]volume=0.25,apad=pad_dur=1.2[a]",
                    "-map",
                    "[v]",
                    "-map",
                    "[a]",
                    "-t",
                    str(duration),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "27",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "64k",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(segment_path),
                ]
            )
            segments.append(segment_path)

        concat_path = temporary_path / "segments.txt"
        concat_path.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in segments),
            encoding="utf-8",
        )
        _run(
            [
                settings.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                "-y",
                str(output_path),
            ]
        )


def _build_ad(
    output_path: Path, brand: dict[str, Any], index: int, settings: Settings
) -> None:
    duration = float(brand.get("duration_seconds", 6))
    _run(
        [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c={brand['color']}:s=960x540:r=24:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={360 + index * 34}:sample_rate=48000:duration={duration}",
            "-filter_complex",
            f"[0:v]{_video_filter(str(brand['name']))}[v];"
            "[1:a]volume=0.035[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "27",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
    )


def ensure_demo_media(settings: Settings | None = None) -> Path:
    active_settings = settings or Settings()
    active_settings.ensure_directories()
    if shutil.which(active_settings.ffmpeg_binary) is None:
        raise RuntimeError("ffmpeg is required to generate demo media")

    demo_path = active_settings.demo_dir / "movie-ad-ai-demo.mp4"
    with MEDIA_GENERATION_LOCK:
        subtitle_path = demo_path.with_suffix(".srt")
        if not demo_path.exists():
            _generate_atomically(
                demo_path,
                lambda output_path: _build_demo_video(output_path, active_settings),
            )
        _write_demo_subtitles(subtitle_path)

        catalogue = json.loads(
            (active_settings.root_dir / "data" / "brands.json").read_text(
                encoding="utf-8"
            )
        )["brands"]
        for index, brand in enumerate(catalogue):
            output_path = active_settings.ads_dir / f"{brand['id']}.mp4"
            if not output_path.exists():
                _generate_atomically(
                    output_path,
                    lambda partial_path, item=brand, item_index=index: _build_ad(
                        partial_path, item, item_index, active_settings
                    ),
                )
    return demo_path


if __name__ == "__main__":
    generated_path = ensure_demo_media()
    print(generated_path)
