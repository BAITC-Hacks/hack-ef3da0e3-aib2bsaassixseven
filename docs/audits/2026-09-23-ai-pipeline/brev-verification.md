# Live Brev verification

23 September 2026. Accessed the user-specified JupyterLab at `https://jupyter-2km2nc4h1.gobrev.dev/lab` through its visible terminal UI. No external inference API, new GPU job, model download, deployment, process interruption or source edit was performed.

## Test evidence

Working directory: `/data/hackalem/backend`.

The ordinary command failed during conftest loading:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests/test_ml_pipeline.py tests/test_ml_compare.py tests/test_ml_runtime.py tests/test_ml_audio_contract.py tests/test_ml_real_regressions.py -q
ImportError while loading conftest '/data/hackalem/backend/tests/conftest.py'.
tests/conftest.py:7: in <module>
    from app.main import create_app
E   ModuleNotFoundError: No module named 'app'
```

The offline ML-only command succeeded:

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest --noconftest -p no:cacheprovider tests/test_ml_pipeline.py tests/test_ml_compare.py tests/test_ml_runtime.py tests/test_ml_audio_contract.py tests/test_ml_real_regressions.py -q
....................................................................... [100%]
71 passed in 1.12s
```

This establishes that the selected deterministic tests pass with the server's installed dependencies when unrelated web fixtures are disabled. It does not fix the standard command, cover the web application or measure ASR/LLM accuracy. No dependency installation was needed.

## Environment and consistency

- NVIDIA L40S: 46068 MiB total, 21657 MiB used, GPU utilization 97%, driver 565.57.01 at the initial snapshot.
- `/data`: 251G total, 32G used, 208G available, 14% used on `/dev/vdc`.
- Installed: torch 2.10.0, transformers 5.12.1, pyannote.audio 4.0.4, faster-whisper 1.2.1, pydantic 2.13.5.
- All 13 files listed in [code-fingerprints.json](code-fingerprints.json) matched remote SHA-256 output. This verifies ML source/config equality at that observation, not the completeness of the deployed repository.
- Remote model directory had `gigaam-ctc`, `gigaam-large-ctc`, `rukk`, `whisper-turbo`, `qwen3.5-9b`, and `diarization`; lock contained the corresponding pinned commits. Qwen3-4B and ISSAI candidates were not prepared.
- Existing `meeting-1/{transcript,abstraction,provenance}.json` and `meeting-2/{transcript,abstraction,provenance}.json` matched the supplied ZIP JSON hashes in [sample-metrics.json](sample-metrics.json) at the snapshot.
- Observed result mtimes: meeting 1 abstraction 2026-09-23 10:25:33 UTC; meeting 2 abstraction 10:31:15 UTC.
- Another existing process, PID 143250, was running `python -m ml_pipeline run` on `Совещание №1.mp3`. The audit did not create or stop it. Its output can change after this snapshot, so these archived statistics must not be relabeled as its eventual results.

## Reproducibility limitations

The current result provenance records model/audio hashes but not code/config/prompt hashes, stage timing, retries or peak GPU memory. There is no measured latency/throughput/cost result here. The 97% utilization sample is neither a speed measure nor an infrastructure problem by itself. Archived alternate-ASR probes in `results/audit_asr.json` were read as existing diagnostic evidence; no human audio gold labels or independent DER were established.

Remote audit terminal was opened for diagnostic commands only. The existing inference remains under its original task's control.
