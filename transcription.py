"""Local WAV-to-text transcription and folder mapping."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class Recording:
    source: Path
    destination: Path


def discover_recordings(source_folder: Path) -> list[Recording]:
    """Find WAV files and map each one into a sibling transcribed_data folder."""
    source_folder = source_folder.expanduser().resolve()
    if not source_folder.is_dir():
        raise ValueError(f"Input folder does not exist: {source_folder}")

    output_folder = source_folder.parent / "transcribed_data"
    if source_folder == output_folder:
        raise ValueError("Select the voice data folder, not transcribed_data.")

    recordings = [
        Recording(
            source=path,
            destination=output_folder / path.relative_to(source_folder).with_suffix(".txt"),
        )
        for path in source_folder.rglob("*")
        if path.is_file() and path.suffix.lower() == ".wav"
    ]
    recordings.sort(key=lambda item: str(item.source.relative_to(source_folder)).lower())

    # On Windows, names such as sample.wav and sample.WAV would target one .txt.
    destinations: set[str] = set()
    for item in recordings:
        key = str(item.destination).casefold()
        if key in destinations:
            raise ValueError(f"Two recordings map to the same transcript: {item.destination}")
        destinations.add(key)
    return recordings


def pending_recordings(
    recordings: Iterable[Recording], *, overwrite: bool = False
) -> tuple[list[Recording], int]:
    pending: list[Recording] = []
    skipped = 0
    for recording in recordings:
        if recording.destination.exists() and not overwrite:
            skipped += 1
        else:
            pending.append(recording)
    return pending, skipped


def create_model():
    """Load full-precision Whisper large-v3 on the local CPU."""
    from faster_whisper import WhisperModel

    return WhisperModel("large-v3", device="cpu", compute_type="float32")


def transcribe_recording(model, recording: Recording) -> str:
    """Return plain text without timestamps or post-processing away fillers."""
    segments, _ = model.transcribe(
        str(recording.source),
        language="en",
        task="transcribe",
        beam_size=5,
        without_timestamps=True,
        vad_filter=False,
    )
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


def save_transcript(destination: Path, text: str) -> None:
    """Write a complete transcript atomically, keeping failed writes out of sight."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", suffix=".tmp",
            prefix=".transcript-", dir=destination.parent, delete=False,
        ) as file:
            temporary_path = file.name
            file.write(text)
            file.write("\n")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def process_recordings(
    recordings: list[Recording],
    *,
    overwrite: bool = False,
    on_event: Callable[[str, object], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    model_factory: Callable[[], object] = create_model,
) -> dict[str, object]:
    """Process sequentially, reporting each result and stopping between files."""
    send = on_event or (lambda _kind, _value: None)
    stopping = should_stop or (lambda: False)
    pending, skipped = pending_recordings(recordings, overwrite=overwrite)
    summary: dict[str, object] = {
        "total": len(recordings), "completed": 0, "skipped": skipped,
        "failed": [], "stopped": False,
    }
    send("plan", {"total": len(recordings), "pending": len(pending), "skipped": skipped})
    if not pending or stopping():
        summary["stopped"] = stopping()
        return summary

    send("loading", None)
    model = model_factory()
    for index, recording in enumerate(pending, start=1):
        if stopping():
            summary["stopped"] = True
            break
        send("current", {"index": index, "count": len(pending), "source": recording.source})
        try:
            text = transcribe_recording(model, recording)
            save_transcript(recording.destination, text)
            summary["completed"] += 1
            send("saved", recording.destination)
        except Exception as error:
            summary["failed"].append((recording.source, str(error)))
            send("error", (recording.source, str(error)))
        send("progress", index)
    return summary
