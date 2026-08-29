"""Hindi TTS engine using Microsoft neural voices via edge-tts."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"

AVAILABLE_VOICES: dict[str, str] = {
    "Swara (Female)": "hi-IN-SwaraNeural",
    "Madhur (Male)": "hi-IN-MadhurNeural",
}

DEFAULT_VOICE = os.getenv("DEFAULT_VOICE", "hi-IN-SwaraNeural")
DEFAULT_FORMAT = os.getenv("OUTPUT_FORMAT", "wav").lower()
MAX_CHARS = int(os.getenv("MAX_CHARS", "50000"))
CHUNK_CHARS = 3000
TARGET_SAMPLE_RATE = 48000

_HINDI_PATTERN = re.compile(r"[\u0900-\u097F]")


def _winget_ffmpeg_paths() -> list[str]:
    paths: list[str] = []
    packages_root = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
    if packages_root.exists():
        for ffmpeg_exe in packages_root.glob("**/ffmpeg.exe"):
            paths.append(str(ffmpeg_exe))
    links_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"))
    if links_path.exists():
        paths.insert(0, str(links_path))
    return paths


def _ffmpeg_candidates() -> list[str]:
    candidates = [
        os.getenv("FFMPEG_PATH", "").strip(),
        shutil.which("ffmpeg") or "",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        *_winget_ffmpeg_paths(),
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _find_ffmpeg() -> str:
    for candidate in _ffmpeg_candidates():
        path = Path(candidate)
        if path.exists():
            return str(path)
    raise RuntimeError(
        "FFmpeg is required but not found. Install with: winget install ffmpeg\n"
        "Then restart your terminal, or set FFMPEG_PATH to the full path of ffmpeg.exe"
    )


def list_voices() -> dict[str, str]:
    return dict(AVAILABLE_VOICES)


def clean_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"[#*_>`|\\/\[\]{}<>]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def validate_text(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        raise ValueError("Please enter some Hindi text to convert.")
    if len(cleaned) > MAX_CHARS:
        raise ValueError(f"Text is too long ({len(cleaned)} chars). Max is {MAX_CHARS}.")
    if not _HINDI_PATTERN.search(cleaned):
        raise ValueError("No Hindi (Devanagari) text detected. Please enter Hindi script.")
    return cleaned


def read_text_file(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if file_path.suffix.lower() != ".txt":
        raise ValueError("Only .txt files are supported.")
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Text file must be UTF-8 encoded.") from exc


def speed_to_rate(speed: float) -> str:
    clamped = max(0.5, min(2.0, speed))
    percent = int(round((clamped - 1.0) * 100))
    return f"{percent:+d}%"


def estimate_duration_seconds(text: str, speed: float = 1.0) -> float:
    words = len(text.split())
    base_wpm = 130
    return max(1.0, (words / base_wpm) * 60 / speed)


def _split_text(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text]

    parts = re.split(r"(?<=[।.!?])\s+", text)
    chunks: list[str] = []
    current = ""

    for part in parts:
        if not part:
            continue
        candidate = f"{current} {part}".strip() if current else part
        if len(candidate) <= CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(part) <= CHUNK_CHARS:
            current = part
        else:
            for i in range(0, len(part), CHUNK_CHARS):
                chunks.append(part[i : i + CHUNK_CHARS])
            current = ""

    if current:
        chunks.append(current)
    return chunks or [text]


async def _synthesize_chunk(text: str, voice_id: str, rate: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice_id, rate=rate)
    await communicate.save(str(out_path))


async def _synthesize_all(
    chunks: list[str],
    voice_id: str,
    rate: str,
    progress_callback=None,
) -> list[Path]:
    temp_dir = Path(tempfile.mkdtemp(prefix="hindi_tts_"))
    paths: list[Path] = []
    try:
        for index, chunk in enumerate(chunks, start=1):
            chunk_path = temp_dir / f"chunk_{index:03d}.mp3"
            await _synthesize_chunk(chunk, voice_id, rate, chunk_path)
            paths.append(chunk_path)
            if progress_callback:
                progress_callback(index, len(chunks))
        return paths
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg = _find_ffmpeg()
    result = subprocess.run([ffmpeg, *args], capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Unknown ffmpeg error"
        raise RuntimeError(f"FFmpeg failed: {detail}")


def _export_audio(chunk_paths: list[Path], out_path: Path, output_format: str) -> None:
    if len(chunk_paths) == 1:
        input_path = chunk_paths[0]
        if output_format == "mp3":
            _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    str(input_path),
                    "-ar",
                    str(TARGET_SAMPLE_RATE),
                    "-ac",
                    "1",
                    "-b:a",
                    "320k",
                    str(out_path),
                ]
            )
        else:
            _run_ffmpeg(
                [
                    "-y",
                    "-i",
                    str(input_path),
                    "-ar",
                    str(TARGET_SAMPLE_RATE),
                    "-ac",
                    "1",
                    "-sample_fmt",
                    "s16",
                    str(out_path),
                ]
            )
        return

    temp_dir = chunk_paths[0].parent
    concat_file = temp_dir / "concat.txt"
    merged_path = temp_dir / "merged.mp3"
    lines = [f"file '{path.as_posix()}'" for path in chunk_paths]
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    _run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(merged_path),
        ]
    )

    if output_format == "mp3":
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(merged_path),
                "-ar",
                str(TARGET_SAMPLE_RATE),
                "-ac",
                "1",
                "-b:a",
                "320k",
                str(out_path),
            ]
        )
    else:
        _run_ffmpeg(
            [
                "-y",
                "-i",
                str(merged_path),
                "-ar",
                str(TARGET_SAMPLE_RATE),
                "-ac",
                "1",
                "-sample_fmt",
                "s16",
                str(out_path),
            ]
        )


def _default_output_name(output_format: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = "mp3" if output_format == "mp3" else "wav"
    return f"hindi_voice_{stamp}.{ext}"


def synthesize(
    text: str,
    voice_id: str = DEFAULT_VOICE,
    *,
    speed: float = 1.0,
    rate: str | None = None,
    output_format: str = DEFAULT_FORMAT,
    output_name: str | None = None,
    progress_callback=None,
) -> Path:
    """Convert Hindi text to speech and save an HD audio file."""
    _find_ffmpeg()
    cleaned = validate_text(text)
    if voice_id not in AVAILABLE_VOICES.values():
        raise ValueError(f"Unsupported voice: {voice_id}")

    output_format = output_format.lower()
    if output_format not in {"wav", "mp3"}:
        raise ValueError("output_format must be 'wav' or 'mp3'.")

    rate_value = rate or speed_to_rate(speed)
    chunks = _split_text(cleaned)

    async def run() -> list[Path]:
        return await _synthesize_all(chunks, voice_id, rate_value, progress_callback)

    chunk_paths = asyncio.run(run())
    temp_dir = chunk_paths[0].parent if chunk_paths else None

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        name = output_name or _default_output_name(output_format)
        if not name.endswith(f".{output_format}"):
            name = f"{name}.{output_format}"
        out_path = OUTPUT_DIR / name
        _export_audio(chunk_paths, out_path, output_format)
        return out_path
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
