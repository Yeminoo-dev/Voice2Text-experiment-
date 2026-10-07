"""Measure word-level F0 from matching WAV and WebMAUS TextGrid files.

Uses the installed Praat executable, then writes one Excel workbook per pair.
Run with ``python extract_word_f0.py``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TEXTGRID_DIR = BASE_DIR / "textGrid_data"
DEFAULT_VOICE_DIR = BASE_DIR / "voice_data"
DEFAULT_OUTPUT_DIR = BASE_DIR / "word_level_data"
BUILDER = BASE_DIR / ".word_f0_runtime" / "build_xlsx.mjs"
PRAAT_SCRIPT = BASE_DIR / "word_f0.praat"
DEFAULT_PRAAT = Path.home() / "OneDrive - Shizuoka University/Desktop/Praat.exe"
BUNDLED_NODE = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"


def find_pairs(textgrid_dir: Path, voice_dir: Path, output_dir: Path) -> tuple[list[tuple[Path, Path, Path]], list[Path]]:
    pairs = []
    missing = []
    for tg in sorted(textgrid_dir.rglob("*")):
        if not tg.is_file() or tg.suffix.lower() != ".textgrid":
            continue
        relative = tg.relative_to(textgrid_dir)
        wav = (voice_dir / relative).with_suffix(".wav")
        if wav.is_file():
            pairs.append((wav, tg, (output_dir / relative).with_suffix(".xlsx")))
        else:
            missing.append(relative)
    return pairs, missing


def extract_one(job: tuple[Path, Path, Path], praat_exe: str, floor: float,
                ceiling: float, tier_name: str) -> dict:
    wav, tg_path, output = job
    match = re.fullmatch(r"p(\d+)", tg_path.parent.name, flags=re.IGNORECASE)
    if match is None:
        raise ValueError(f"Cannot derive participant from folder {tg_path.parent.name!r}")
    participant = f"P{match.group(1)}"
    with tempfile.TemporaryDirectory(prefix="word_f0_") as temp_dir:
        tsv = Path(temp_dir) / "measurements.tsv"
        command = [
            praat_exe, "--run", "--utf8", str(PRAAT_SCRIPT),
            wav.as_posix(), tg_path.as_posix(), tsv.as_posix(), tier_name,
            str(floor), str(ceiling),
        ]
        completed = subprocess.run(command, cwd=BASE_DIR, capture_output=True,
                                   text=True, encoding="utf-8", errors="replace")
        if completed.returncode or not tsv.is_file():
            detail = (completed.stderr or completed.stdout or "Praat produced no output").strip()
            raise RuntimeError(detail[:500])
        with tsv.open("r", encoding="utf-8-sig", newline="") as handle:
            measurements = list(csv.DictReader(handle, delimiter="\t"))

    counts: Counter[str] = Counter()
    rows = []
    for measure in measurements:
        word = measure["word"].strip()
        if not word:
            continue
        counts[word] += 1
        mean = float(measure["mean_f0"])
        minimum = float(measure["min_f0"])
        maximum = float(measure["max_f0"])
        rows.append([
            participant, len(rows) + 1, "word", f"{word}_{counts[word]}",
            mean, float(measure["duration"]), minimum, maximum,
            round(maximum - minimum, 2) if minimum and maximum else 0.0,
        ])
    return {"output": str(output), "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--textgrid-dir", type=Path, default=DEFAULT_TEXTGRID_DIR)
    parser.add_argument("--voice-dir", type=Path, default=DEFAULT_VOICE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tier", default="ORT-MAU")
    parser.add_argument("--pitch-floor", type=float, default=50)
    parser.add_argument("--pitch-ceiling", type=float, default=800)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit", type=int, help="process only this many new pairs")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--praat", type=Path, default=DEFAULT_PRAAT if DEFAULT_PRAAT.is_file() else None)
    parser.add_argument("--node", type=Path, default=BUNDLED_NODE if BUNDLED_NODE.is_file() else None)
    args = parser.parse_args(argv)
    if not args.textgrid_dir.is_dir() or not args.voice_dir.is_dir():
        parser.error("TextGrid and voice directories must exist")
    if args.pitch_floor <= 0 or args.pitch_ceiling <= args.pitch_floor:
        parser.error("pitch ceiling must exceed a positive pitch floor")
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    pairs, missing = find_pairs(args.textgrid_dir, args.voice_dir, args.output_dir)
    pending = [job for job in pairs if args.overwrite or not job[2].is_file()]
    if args.limit is not None:
        pending = pending[:args.limit]
    print(f"Found {len(pairs)} pairs; {len(missing)} WAV files missing; {len(pending)} workbooks to create.", flush=True)
    for relative in missing:
        print(f"Missing WAV: {relative}", file=sys.stderr)
    if args.dry_run:
        for wav, tg, output in pending:
            print(f"{wav} + {tg} -> {output}")
        return 0 if not missing else 1
    if not pending:
        return 0 if not missing else 1

    node = str(args.node) if args.node else shutil.which("node")
    praat_exe = str(args.praat) if args.praat else shutil.which("praat")
    if not praat_exe or not PRAAT_SCRIPT.is_file():
        parser.error("Praat executable or word_f0.praat is missing")
    if not node or not BUILDER.is_file():
        parser.error("Node.js or the XLSX builder is missing")
    manifest = BASE_DIR / ".word_f0_runtime" / "manifest.json"
    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(extract_one, job, praat_exe, args.pitch_floor, args.pitch_ceiling, args.tier): job
                   for job in pending}
        for number, future in enumerate(as_completed(futures), 1):
            wav, _, _ = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                failures.append((wav, str(exc)))
                print(f"[{number}/{len(pending)}] FAILED {wav}: {exc}", file=sys.stderr, flush=True)
            else:
                results.append(result)
                print(f"[{number}/{len(pending)}] Measured {wav.name}: {len(result['rows'])} words", flush=True)

    if results:
        results.sort(key=lambda item: item["output"])
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run([node, str(BUILDER), str(manifest)], check=False)
        if completed.returncode:
            print(f"XLSX export failed. Measurements remain in {manifest}", file=sys.stderr)
            return completed.returncode
        for result in results:
            Path(result["output"] + ".inspect.ndjson").unlink(missing_ok=True)
    print(f"Finished: {len(results)} workbooks, {len(failures)} extraction failures, {len(missing)} missing WAV files.")
    for wav, error in failures:
        print(f"FAILED {wav}: {error}", file=sys.stderr)
    return 0 if not failures and not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
