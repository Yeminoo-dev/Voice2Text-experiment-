# Local Voice Transcriber

A Windows desktop app that turns WAV recordings into plain-text transcripts using
Whisper large-v3 locally. It uses the CPU at full `float32` precision.

## Setup

Install Anaconda or Miniconda. In PowerShell, from this folder, run:

```powershell
conda env create -f environment.yml
```

This creates the Conda environment named `ExperimentalApp` with Python 3.12,
Tk, and faster-whisper. If it already exists, update it with
`conda env update -f environment.yml --prune`.

The first transcription downloads the large-v3 model. Allow several gigabytes
of free disk space. Once the model is cached, transcription runs locally without
uploading recordings. On an 8 GB RAM computer, close other memory-heavy apps;
full precision may exceed available memory. The app reports an error if model
loading fails and does not change precision automatically.

On the development computer, a 73-second WAV took about 149 seconds to
transcribe after the model loaded and the process used about 6.5 GB of RAM.
Processing all recordings may take several hours. Speed and memory use depend
on the computer and other running programs.

## Use

Double-click `run_app.bat`, or run:

```powershell
conda run -n ExperimentalApp python app.py
```

Select the `voice_data` folder, then click **Start transcription**. The app
recursively finds `.wav` files and creates a sibling `transcribed_data` folder.
For example:

```text
voice_data\p11\11.1.1.wav → transcribed_data\p11\11.1.1.txt
```

Filenames and subfolder names are preserved. Existing `.txt` files are skipped
unless you check **Transcribe again and replace existing .txt files**. The app
works through files one at a time, shows file-level progress, and can stop
after the current file. A failed file is logged and later files continue.

The output contains only transcript text, with no timestamps or speaker labels.
The language is set to English, and no text cleanup removes filler words.
Whisper may still omit some fillers or mishear accented speech, so review is
necessary when exact wording matters.

## Align transcripts with WebMAUS Basic

WebMAUS uploads each WAV and its matching transcript to the BAS web service and
downloads a Praat `.TextGrid` with word and phone alignment. Install the updated
dependencies, then preview the matching files and run the batch:

```powershell
conda env update -f environment.yml --prune
conda run -n ExperimentalApp python webmaus_textgrids.py --dry-run --limit 5
conda run -n ExperimentalApp python webmaus_textgrids.py
```

The script maps, for example,
`voice_data\Data_20260629\p11\11.1.1.wav` and
`transcribed_data\Data_20260629_transcribed\p11\11.1.1.txt` to
`textGrid_data\Data_20260629\p11\11.1.1.TextGrid`. It uses English (US)
by default; change this with `--language` if appropriate. Existing TextGrids
are skipped when rerunning; use `--overwrite` to replace them. Use `--limit 1`
for one real API call. `--workers 3` can speed up a large batch. Failed files are
printed and the remaining files continue.
Review transcript wording before alignment, since WebMAUS aligns the supplied
words rather than correcting them.

## Extract word-level F0 to Excel

`extract_word_f0.py` pairs every WAV with the same relative `.TextGrid` path,
runs `word_f0.praat` with the filtered-autocorrelation settings shown in the
script, and creates one workbook per pair in `word_level_data`. For example,
`textGrid_data\Data_20260629\p11\11.1.1.TextGrid` becomes
`word_level_data\Data_20260629\p11\11.1.1.xlsx`. The matching WAV comes from
`voice_data`. Each workbook contains one row per nonempty `ORT-MAU` interval.
The participant comes from the `p11` folder, and repeated words are numbered
within a recording. Undefined F0 values become 0, matching the supplied Praat
script. Pitch range is max F0 minus min F0 when both are defined.

```powershell
python extract_word_f0.py --dry-run --limit 3
python extract_word_f0.py
```

The script uses the installed Praat executable and the bundled Node spreadsheet
runtime. If Praat is elsewhere, pass `--praat C:\path\to\Praat.exe`. It skips
existing workbooks; use `--overwrite` to regenerate them. `--workers` controls
how many Praat processes run at once (default 2).

## Optional: temporary Colab GPU processing

Upload `colab_transcribe.ipynb` to Colab and put `Data_20260629.zip` in the
runtime's **Files** pane. Run the code cells to produce one transcript ZIP.
The complete instructions are in [COLAB_GUIDE.md](COLAB_GUIDE.md).
