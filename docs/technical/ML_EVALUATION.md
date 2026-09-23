# ML evaluation and release evidence

Status on 2026-09-23: **not evaluated on real meetings**. The repository contains contract tests with generated silent WAV bytes and a fake GPU response. Those tests validate transport, persistence, review and export behavior; they measure neither speech recognition nor diarization quality. The synthetic prepared-example fixture also contains fictional text and is disabled for a stage demo by default.

## External inputs still required

1. **Consented recordings**: one Russian, one Kazakh and one mixed-language meeting, each with at least two speakers where possible. Keep audio outside Git. The available worktree has no verified meeting recording; personal audio filenames elsewhere on the workstation were not treated as consented test material and were not opened.
2. **Ground truth**: human-checked transcript with word/segment times, speaker changes, summary and action items linked to audible evidence. Record ambiguous speech and names as uncertain, never infer identity from participant names alone.
3. **NVIDIA service**: deployed GPU inference API and worker matching `docs/technical/API_CONTRACT.md`, reachable over TLS or a protected tunnel, with backend-only `GPU_API_URL` and `GPU_API_TOKEN`. Neither was configured in this worktree's environment during this inspection. The service, model weights, version strings, and actual throughput were unavailable here.
4. **Demo account and private fixture**: a dedicated Supabase user ID, a consented audio file, and a precomputed JSON fixture pinned to that file's SHA-256. The test fixture is synthetic and must not be presented as model output.

## Run and record for each language case

- Record the date, consented asset identifier and SHA-256 (without publishing the recording), duration, sample rate, channel count, language, speaker count, model versions, GPU hardware, and pipeline commit.
- Upload through the UI/API and observe `queued → processing → review_required`. Capture stage times, end-to-end latency, job ID/attempt, retry behavior, and safe failure codes. Check that upload bytes are deleted locally and GPU temporary data are deleted after ACK or TTL.
- Compare every transcript segment against the recording, including language switches, time bounds and speaker labels. Calculate WER/CER and diarization error rate only against an annotated reference using a stated normalization/scoring policy; do not report a number from synthetic fixtures.
- Review every summary/action item against the cited segment. Mark unsupported claims, missing actions, wrong assignees, uncertain due dates, and evidence outside its segment. Count supported items and omissions separately.
- Assign or explicitly mark speakers unknown, correct transcript/insights, approve, and extract the PDF to verify Russian/Kazakh glyphs, citations and times. Make another edit; ensure approval and old export are invalidated. Reopen after backend restart and with GPU unreachable.
- Test network loss after submit, durable lookup by `meeting_id:attempt`, storage failure before ACK, repeated ACK, and TTL expiry. Record whether cleanup is confirmed; `pending` is not success.

## Results table

| Case | Recording checked | GPU/model run | Human evidence review | PDF glyphs | Result |
| --- | --- | --- | --- | --- | --- |
| Russian | Pending | Pending | Pending | Pending | Not evaluated |
| Kazakh | Pending | Pending | Pending | Pending | Not evaluated |
| Mixed RU/KK | Pending | Pending | Pending | Pending | Not evaluated |

No accuracy, latency, or production-readiness claim is supported until these rows contain measured results from the same integrated build.
