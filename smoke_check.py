"""Load the configured model and transcribe one WAV without writing a transcript."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from transcription import Recording, create_model, transcribe_recording


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python smoke_check.py path/to/recording.wav")
        return 2
    source = Path(sys.argv[1]).resolve()
    if not source.is_file() or source.suffix.lower() != ".wav":
        print(f"Not a WAV file: {source}")
        return 2

    started = time.monotonic()
    model = create_model()
    loaded_at = time.monotonic()
    text = transcribe_recording(model, Recording(source, source.with_suffix(".txt")))
    finished_at = time.monotonic()
    print(f"Model load: {loaded_at - started:.1f} seconds")
    print(f"Transcription: {finished_at - loaded_at:.1f} seconds")
    print(f"Transcript length: {len(text)} characters")
    print("No transcript file was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
