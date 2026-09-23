# Offline ML pipeline for completed meeting recordings

Run from `backend/`. This package does not use the web API, database, document export,
or frontend. Processing is local: FFmpeg converts the recording to 16 kHz mono WAV,
Silero VAD finds speech intervals, pyannote Community-1 diarizes the whole recording,
and the selected ASR model transcribes the intersections of VAD and speaker turns.
Every output timestamp is an offset from the original recording. `speaker_id` is an
anonymous diarization label and is never mapped to a participant name automatically.

The transcript is processed in chronological chunks by local Qwen. Each chunk is
strictly parsed as JSON, checked with Pydantic and checked against literal quotes
in its cited utterances. A sequential reconciliation pass sees earlier extracted
items and later transcript turns, so it can keep a correction or remove a cancelled
assignment. It still depends on model accuracy; `needs_review` marks uncertain
owners and dates. The Markdown summary is deterministic from the validated
abstraction and includes utterance IDs rather than making another LLM call.

## NVIDIA Brev setup

On the provided Brev instance, `nvidia-smi -L` reports one NVIDIA L40S and
`nvidia-smi` reports 46,068 MiB of device memory. `/data` is a mounted 256 GB
volume with 239 GB free at the time of inspection; use it for model weights and
the Hugging Face cache. The ML files have been staged at `/data/hackalem/backend`,
and the two test MP3 files at `/data/hackalem/recordings`. FFmpeg is installed.
Sync any later code changes to Brev, then run:

```bash
cd /data/hackalem/backend
nvidia-smi --query-gpu=index,name,memory.total,uuid --format=csv,noheader
uv sync --locked --extra ml

export HF_HOME=/data/hackalem/hf-cache
export MODELS_DIR=/data/hackalem/models
export HF_TOKEN='YOUR_HUGGING_FACE_READ_TOKEN'
# Accept the pyannote/speaker-diarization-community-1 access terms on Hugging Face first.
uv run --locked --extra ml python -m ml_pipeline prepare \
  --models-dir "$MODELS_DIR" --asr-model gigaam-large-ctc --llm-model qwen3.5-9b
unset HF_TOKEN
```

The preparation command downloads only Community-1, the selected ASR model and
the selected LLM. Use `--also gigaam-ctc rukk whisper-turbo qwen3-4b
issai-4b-kazakh` to prepare candidates for comparison. Model files and
`models.lock.json` remain in `MODELS_DIR`. The lock records immutable Hub commit
SHAs. Copy that lock to another persistent model directory before `prepare` to
download exactly the same revisions. Python dependency versions are in `uv.lock`.

```bash
uv run --offline --locked --extra ml python -m ml_pipeline run \
  --audio '/data/hackalem/recordings/Совещание №1.mp3' \
  --timezone Asia/Qyzylorda \
  --asr-model gigaam-large-ctc --llm-model qwen3.5-9b \
  --models-dir "$MODELS_DIR" --output-dir '/data/hackalem/results/meeting-1'
```

`--meeting-at` is optional. Omit it if unknown; relative deadlines then keep their
original wording and `due_date` is `null` with `needs_review=true`. `--timezone` is
an IANA time zone and is required even without a date. A bare ISO date/time is
interpreted in that zone. An ISO time with offset is converted to it. `--participant`
may be repeated or omitted. `--chunk-chars` controls the text chunk size (default
10,000). Absolute dates such as `2026-10-02` are accepted without a meeting date.
Unclear intervals such as “на следующей неделе” stay as `due_text` with no date.

For an audio-verified phrase lost at a diarization boundary, pass
`--reviewed-corrections path/to/review.json`. The optional JSON contains the exact
audio SHA-256 and time-bounded text insertions or exact replacements. An insertion
cannot assign a speaker label; its `speaker_id` is `null`. A replacement must
match the specified utterance ID and exactly one phrase within its time window.
The pipeline rejects a manifest
for a different recording, applies the corrections before abstraction, and
copies the manifest plus its SHA-256 into the output provenance. This keeps a
correction traceable and reproducible without editing generated ZIP files.
`examples/meeting-1-reviewed-corrections.json` records the audio-verified
"Тимур Болатович" address clipped around 03:34 and normalizes the spelling
of the same name around 01:42 in meeting 1. Use it only with the exact MP3
whose hash it names.

Outputs:

- `transcript.json`: meeting metadata and `utterances`, each with `id`, `start_ms`,
  `end_ms`, `speaker_id`, and `text`.
- `abstraction.json`: `key_facts`, `decisions`, and `tasks`. Every item has source
  utterance IDs and an exact evidence quote. Each task has `action`, `responsible`
  (or `null`), `due_date` (ISO date or `null`), `due_text` (original wording or
  `null`) and `needs_review`. `validation_warnings` lists model proposals that
  could not be grounded in cited speech and were excluded.
- `summary.md`: short facts, decisions and active assignments with source IDs.
- `provenance.json`: audio SHA-256, SHA-256 of the ML Python source files, and
  the locked Hub repository and commit SHA for every model used in the run.
  When a reviewed manifest is supplied, it also
  records the manifest hash and inserted utterance IDs, and the output includes
  `reviewed_corrections.json`.

Inference loads prepared local paths only. `run` sets `HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`, and disables Hugging Face and pyannote telemetry. Use the
`--offline` flag with `uv run` shown above to prevent package-index access too.
No audio or transcript is sent to external inference APIs.

## ASR and LLM candidates

`--asr-model` accepts `gigaam-ctc`, `gigaam-large-ctc`, `rukk`, or
`whisper-turbo`. GigaAM uses the `ctc` and `large_ctc` revisions of
`ai-sage/GigaAM-Multilingual`. `rukk` uses `asr/rukk` of
`alibiserikbay/kazakh-russian-mixed-stt`. Whisper Turbo uses the CTranslate2
checkpoint from `mobiuslabsgmbh/faster-whisper-large-v3-turbo`.

`--llm-model` accepts `qwen3.5-9b` (default), `qwen3-4b`, and
`issai-4b-kazakh`. The latter two are comparison candidates. The models are
loaded one stage at a time; ASR is released before loading Qwen. A total of
48 GB VRAM is an allocation, not proof that one 48 GB device exists. For multiple
GPUs, Qwen uses Transformers `device_map="auto"`.

## Candidate comparison

Create a JSON manifest with **time-aligned** reference utterances and final
active tasks. Each reference utterance must be at most 25 seconds. `language`
must be `ru`, `kk`, or `mixed`. `due_date` is an ISO date or `null`.

```json
{
  "recordings": [
    {
      "audio": "meeting-1.mp3",
      "meeting_at": "2026-09-23T10:00:00",
      "timezone": "Asia/Qyzylorda",
      "participants": ["Ерлан"],
      "reference_utterances": [
        {"start_ms": 1000, "end_ms": 4200, "language": "ru", "text": "Загрузка цеха 71 процент"},
        {"start_ms": 4500, "end_ms": 8200, "language": "mixed", "text": "Ерлан есепті дайындасын"}
      ],
      "reference_tasks": [
        {"action": "Подготовить отчёт", "responsible": "Ерлан", "due_date": "2026-10-02"}
      ]
    }
  ]
}
```

Audio paths are relative to the manifest. For each ASR and LLM combination,
the script runs the same recordings and writes `comparison.json`. For WER/CER it
transcribes each labeled interval directly with the selected ASR model (oracle
segmentation), avoiding double counting text when predicted intervals cross
reference boundaries. WER/CER are aggregated separately for Russian, Kazakh, and
mixed speech; missing labels produce `null` rates. These ASR scores isolate model
quality from VAD/diarization errors. Task metrics use the full pipeline and count
missed and extra assignments, plus responsible and deadline errors. Tasks are greedily
matched by action text similarity, so review
low-similarity matches manually. Put corrected final assignments in
`reference_tasks`, excluding cancelled ones.

```bash
uv run --offline --locked --extra ml python -m ml_pipeline compare \
  --manifest '/data/hackalem/recordings/reference.json' \
  --models-dir "$MODELS_DIR" --output-dir '/data/hackalem/results/benchmark' \
  --asr-models gigaam-ctc gigaam-large-ctc rukk whisper-turbo \
  --llm-models qwen3.5-9b qwen3-4b issai-4b-kazakh
```

The attached `Совещание №1.mp3` and `Совещание №2.mp3` are available, and the
Markdown protocols show the desired style. The protocols have no utterance
timestamps or `ru`/`kk`/`mixed` interval labels, so they cannot yet provide
valid language-specific WER/CER or task-error scores. No real meeting quality
metric is claimed here.

## Synthetic check

The following command creates three example outputs from a synthetic transcript
without loading the speech or LLM models:

```bash
uv run --locked python -m examples.synthetic_demo \
  --output-dir examples/synthetic-output
uv run --locked --extra ml pytest tests/test_ml_pipeline.py tests/test_ml_compare.py tests/test_ml_runtime.py tests/test_ml_audio_contract.py -q
```

See `examples/synthetic-output/`. This verifies the JSON schemas, evidence
validation, date handling and summary rendering; it does not measure real ASR,
diarization, or Qwen accuracy.

Model API references: [pyannote Community-1](https://github.com/pyannote/pyannote-audio),
[GigaAM Multilingual](https://huggingface.co/ai-sage/GigaAM-Multilingual),
[mixed kk+ru STT](https://huggingface.co/alibiserikbay/kazakh-russian-mixed-stt),
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B), and
[ISSAI Kazakh](https://huggingface.co/issai/Qwen3.5-4B-Kazakh).
