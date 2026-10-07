from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath


def output_name(raw_name: str) -> str | None:
    if raw_name.startswith(("/", "\\")) or "\\" in raw_name:
        raise ValueError("Archive contains an unsafe path")
    parts = raw_name.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise ValueError("Archive contains an unsafe path")
    if parts[0].lower() == "voice_data":
        parts = parts[1:]
    if not parts or not parts[-1].lower().endswith(".wav"):
        return None
    relative = PurePosixPath(*parts).with_suffix(".txt")
    return str(PurePosixPath("transcribed_data") / relative)


def collect_recordings(archive: zipfile.ZipFile):
    recordings = []
    seen = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        destination = output_name(info.filename)
        if destination is None:
            continue
        key = destination.casefold()
        if key in seen:
            raise ValueError("ZIP contains duplicate WAV destinations")
        seen.add(key)
        recordings.append((info, destination))
    recordings.sort(key=lambda item: item[1].casefold())
    return recordings


def transcribe_archive(input_zip: Path, output_zip: Path, model_factory=None):
    with zipfile.ZipFile(input_zip) as archive:
        recordings = collect_recordings(archive)
        if not recordings:
            raise ValueError("Uploaded ZIP contains no WAV recordings")

        if model_factory is None:
            from faster_whisper import WhisperModel

            model_factory = lambda: WhisperModel(
                "large-v3-turbo", device="cuda", compute_type="float16"
            )

        print(f"Found {len(recordings)} WAV files. Loading the GPU model...", flush=True)
        model = model_factory()
        completed = 0
        failures = []
        first_failure = None
        started = time.monotonic()
        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as result:
            for index, (info, destination) in enumerate(recordings, start=1):
                file_started = time.monotonic()
                try:
                    with archive.open(info) as audio_file:
                        audio = io.BytesIO(audio_file.read())
                    segments, _ = model.transcribe(
                        audio,
                        language="en",
                        task="transcribe",
                        beam_size=5,
                        without_timestamps=True,
                        vad_filter=False,
                    )
                    transcript = " ".join(
                        segment.text.strip() for segment in segments if segment.text.strip()
                    )
                    result.writestr(destination, transcript + "\n")
                    completed += 1
                except Exception as error:
                    failures.append(f"{info.filename}: {type(error).__name__}: {error}")
                    if first_failure is None:
                        message = str(error).replace(info.filename, "[recording]")
                        message = message.replace(str(input_zip), "[archive]")
                        first_failure = f"{type(error).__name__}: {message}"
                print(
                    f"Processed {index}/{len(recordings)} in "
                    f"{time.monotonic() - file_started:.1f}s",
                    flush=True,
                )
            if failures:
                result.writestr("processing_errors.txt", "\n".join(failures) + "\n")

    print(
        f"Completed {completed}; failed {len(failures)}; "
        f"processing time {time.monotonic() - started:.1f}s."
    )
    if first_failure is not None:
        print(f"First failure: {first_failure}")
    return completed, len(failures)


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: colab_worker.py OUTPUT.zip INPUT.zip")
        return 2
    output_zip = Path(sys.argv[1])
    input_zip = Path(sys.argv[2])
    if not input_zip.is_file():
        print("Input ZIP is missing")
        return 2
    try:
        completed, failed = transcribe_archive(input_zip, output_zip)
    except Exception as error:
        print(f"Processing stopped: {type(error).__name__}: {error}")
        return 1
    if completed == 0 and failed:
        print("Processing stopped: all recordings failed; download the result ZIP and read processing_errors.txt.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
