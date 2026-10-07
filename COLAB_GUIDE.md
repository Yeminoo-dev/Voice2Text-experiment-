# Colab transcription guide

Use [colab_transcribe.ipynb](colab_transcribe.ipynb) to transcribe the WAV recordings on a temporary Google Colab GPU runtime. The notebook contains code cells only. This guide holds the instructions and background information.

## Prepare Colab

1. Open [Google Colab](https://colab.research.google.com/) and choose **File → Upload notebook**. Select `colab_transcribe.ipynb` from this folder.
2. Choose **Runtime → Change runtime type → GPU**. Connect to the runtime.
3. Open the **Files** pane on the left. Use its **Upload to session storage** button to upload `Data_20260629.zip`. Wait until it appears as `/content/Data_20260629.zip` before running the processing cell. The notebook reads that exact file. The ZIP must contain `.wav` recordings.

## Run and collect the result

4. Run the notebook cells from top to bottom. The first checks the GPU; the second installs the required packages. The third writes the included transcription program into the temporary runtime. The fourth processes the uploaded ZIP with one model load. Progress shows counts and timings, without printing filenames or transcript text.
5. When the fourth cell reports **Transcript ZIP is ready**, run the last cell to download `transcribed_data_colab.zip`. Wait for the browser download to finish. A copy remains visible in Colab's Files pane if you need to download it manually. If processing reports failures, the cell prints the first error and still keeps the result ZIP available for download so you can read `processing_errors.txt` inside it.
6. On your computer, extract the downloaded ZIP next to the `voice_data` folder. It contains `transcribed_data` with the same subfolder layout and one plain-text `.txt` file per successful recording. Check whether `processing_errors.txt` is present in the ZIP; it lists any files that failed.
7. After checking the download, choose **Runtime → Disconnect and delete runtime**.

## What to expect

The notebook uses `faster-whisper` with Whisper `large-v3-turbo`, English transcription, and a GPU. It does not add timestamps, speaker labels, or cleanup of filler words. The local Windows app uses the larger `large-v3` model, so wording may differ. Review transcripts where exact wording matters.

The package installation cell pins `faster-whisper` 1.2.1 and PyAV 18.1.0. This pair was verified to decode a WAV inside a ZIP; the pin prevents the `metadata_errors` incompatibility that caused every recording to fail. If you already ran an older copy of the notebook, run the updated installation cell before processing again.

The WAV files are uploaded to Google's temporary Colab runtime for processing. The notebook does not mount Google Drive. Deleting the runtime removes the temporary virtual machine; it does not establish Google's internal data-retention policy. GPU availability and runtime duration depend on Colab. If the runtime disconnects before the result is downloaded, reconnect, upload the ZIP again, and rerun the cells. If processing stops with an error, inspect `/content/transcription_error.log` in the Files pane.
