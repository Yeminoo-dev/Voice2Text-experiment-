"""Align WAV/transcript pairs with BAS WebMAUS Basic.

Run ``python webmaus_textgrids.py --dry-run`` to inspect the pairing first.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests


SERVICE_URL = "https://clarin.phonetik.uni-muenchen.de/BASWebServices/services/runMAUSBasic"
BASE_DIR = Path(__file__).resolve().parent
ALLOWED_DOWNLOAD_HOST = "clarin.phonetik.uni-muenchen.de"


def transcript_relative_path(audio_relative: Path) -> Path:
    """Map a WAV path to the transcript layout used by this project."""
    parts = list(audio_relative.parts)
    parts[0] += "_transcribed"
    return Path(*parts).with_suffix(".txt")


def find_pairs(audio_root: Path, transcript_root: Path) -> tuple[list[tuple[Path, Path, Path]], list[Path]]:
    pairs = []
    missing = []
    for audio in sorted(audio_root.rglob("*")):
        if not audio.is_file() or audio.suffix.lower() != ".wav":
            continue
        relative = audio.relative_to(audio_root)
        transcript = transcript_root / transcript_relative_path(relative)
        # Also accept a transcript tree that exactly mirrors voice_data.
        if not transcript.is_file():
            direct = (transcript_root / relative).with_suffix(".txt")
            transcript = direct if direct.is_file() else transcript
        if transcript.is_file() and transcript.stat().st_size:
            pairs.append((audio, transcript, relative.with_suffix(".TextGrid")))
        else:
            missing.append(relative)
    return pairs, missing


def download_url(response_xml: bytes) -> str:
    try:
        root = ET.fromstring(response_xml)
    except ET.ParseError as exc:
        raise ValueError("WebMAUS returned invalid XML") from exc
    if (root.findtext("success") or "").strip().lower() != "true":
        detail = (root.findtext("warnings") or root.findtext("output") or "unknown error").strip()
        raise ValueError(f"WebMAUS failed: {detail[:500]}")
    link = (root.findtext("downloadLink") or "").strip()
    parsed = urlparse(link)
    if parsed.hostname != ALLOWED_DOWNLOAD_HOST or parsed.scheme not in {"http", "https"}:
        raise ValueError("WebMAUS returned an unexpected download URL")
    # Some BAS responses contain HTTP links even though the service supports HTTPS.
    return urlunparse(parsed._replace(scheme="https", netloc=ALLOWED_DOWNLOAD_HOST))


def align_pair(session: requests.Session, audio: Path, transcript: Path, destination: Path,
               language: str, timeout: int) -> None:
    with audio.open("rb") as signal, transcript.open("rb") as text:
        response = session.post(
            SERVICE_URL,
            data={"LANGUAGE": language, "OUTFORMAT": "TextGrid"},
            files={"SIGNAL": (audio.name, signal, "audio/wav"),
                   "TEXT": (transcript.name, text, "text/plain")},
            timeout=timeout,
        )
    response.raise_for_status()
    url = download_url(response.content)
    result = session.get(url, timeout=timeout)
    result.raise_for_status()
    content = result.content
    if b'Object class = "TextGrid"' not in content[:500]:
        raise ValueError("Downloaded result is not a Praat TextGrid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        temporary.write_bytes(content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice-dir", type=Path, default=BASE_DIR / "voice_data")
    parser.add_argument("--transcript-dir", type=Path, default=BASE_DIR / "transcribed_data")
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "textGrid_data")
    parser.add_argument("--language", default="eng-US", help="WebMAUS language code (default: eng-US)")
    parser.add_argument("--dry-run", action="store_true", help="show pairs without uploading")
    parser.add_argument("--overwrite", action="store_true", help="replace existing TextGrids")
    parser.add_argument("--limit", type=int, help="process at most this many new pairs")
    parser.add_argument("--timeout", type=int, default=180, help="seconds per HTTP request")
    parser.add_argument("--workers", type=int, default=1, help="parallel API requests (default: 1)")
    args = parser.parse_args(argv)
    if not args.voice_dir.is_dir() or not args.transcript_dir.is_dir():
        parser.error("voice and transcript directories must exist")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")

    pairs, missing = find_pairs(args.voice_dir, args.transcript_dir)
    if not pairs:
        print("No WAV/transcript pairs found.", file=sys.stderr)
        return 1
    print(f"Found {len(pairs)} pairs; {len(missing)} WAV files lack a nonempty transcript.")
    for relative in missing:
        print(f"Missing transcript: {relative}", file=sys.stderr)
    pending = [(audio, txt, args.output_dir / relative)
               for audio, txt, relative in pairs
               if args.overwrite or not (args.output_dir / relative).is_file()]
    skipped = len(pairs) - len(pending)
    if args.limit is not None:
        pending = pending[:args.limit]
    print(f"{len(pending)} TextGrids to generate; {skipped} existing TextGrids skipped.")
    if args.dry_run:
        for audio, txt, destination in pending:
            print(f"{audio} + {txt} -> {destination}")
        return 0 if not missing else 1

    def process(item: tuple[Path, Path, Path]) -> Path:
        audio, txt, destination = item
        with requests.Session() as session:
            align_pair(session, audio, txt, destination, args.language, args.timeout)
        return destination

    succeeded = 0
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process, item): item for item in pending}
        for number, future in enumerate(as_completed(futures), 1):
            audio, _, destination = futures[future]
            try:
                future.result()
            except (requests.RequestException, OSError, ValueError) as exc:
                failures.append((audio, str(exc)))
                print(f"[{number}/{len(pending)}] FAILED {audio.relative_to(args.voice_dir)}: {exc}",
                      file=sys.stderr, flush=True)
            else:
                succeeded += 1
                print(f"[{number}/{len(pending)}] Saved {destination}", flush=True)
    print(f"Finished: {succeeded} saved, {len(failures)} failed, {len(missing)} missing transcripts.")
    for audio, error in failures:
        print(f"FAILED {audio}: {error}", file=sys.stderr)
    return 0 if not failures and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
