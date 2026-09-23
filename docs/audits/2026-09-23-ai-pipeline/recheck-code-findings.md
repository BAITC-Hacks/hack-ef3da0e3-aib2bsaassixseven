# Current-code recheck: correction, review and provenance

Date: 2026-09-23. This is a fresh audit of the changed code, not an assertion that the earlier improvement plan was implemented. No production code, examples, prior reports, model weights, or remote Brev state were changed by this reviewer. All probes use the actual current Python functions; GPU/ASR/LLM are mocked where runtime integration is necessary.

## Verified change surface

Compared actual SHA-256 values with `code-fingerprints.json`:

| File | Current SHA-256 / status |
| --- | --- |
| `backend/ml_pipeline/__main__.py` | `6b021beaf0e59235a8d2478532bbda660c3902bde675b2479428b62452b174f5` |
| `backend/ml_pipeline/abstraction.py` | `a54202a504c456492e07a7477b382fb2f157af7c7eb77eae9f83e73c8b82dc03` |
| `backend/ml_pipeline/audio.py` | `ca7ec3fb7c71837d2402a9469b9a4a18645a72dc9b614ccac7ead11ad8b3ca80` |
| `backend/ml_pipeline/compare.py` | `153349eb38170280f96365217cfbbfc5c134621b89e7ba587b6aa1b35882d563` |
| `backend/ml_pipeline/runtime.py` | `691348aa808733e4cefafce34172abf674705a147ecfbcb84d8a92a5e2ed8b27` |
| `backend/ml_pipeline/review.py` | New file; no entry in old fingerprint file |
| `backend/ml_pipeline/models.py` | Unchanged against old fingerprint |
| Other entries in old fingerprint file | Unchanged |

`test_ml_reviewed_corrections.py` contains three tests: insertion and audit hash; rejection of wrong audio/speaker fields; one successful mocked runtime packaging path. Existing tests do not cover the packaging cases below. The independent verifier reports 103 current tests passing, and that previous E1–E4 exact counterexamples now pass their intended behavior; do not carry those old findings forward as still failing without rechecking them.

## Reproduced findings

### R1 — P2: rerunning with the output manifest fails after writing results

Location: `backend/ml_pipeline/runtime.py:195`.

Trigger: after a corrected run, pass `--reviewed-corrections <output-dir>/reviewed_corrections.json` and reuse the same `--output-dir`. This is a valid existing manifest and a natural reproducibility workflow.

Expected: complete successfully using the manifest, or reject this path combination before expensive processing and output writes.

Actual: `shutil.copyfile` raises `SameFileError` because source equals destination. The transcript, abstraction, and summary have already been overwritten at lines 175–183; the final provenance write at line 199 is skipped. A previous provenance file can therefore remain alongside new results. The probe ran the actual `run_pipeline` function with only expensive dependencies mocked and observed `SameFileError` naming the same path twice.

Impact: avoidable full-run failure and a partially refreshed result directory. High confidence; no real inference is required to reproduce it. This is not a claim the current Brev run used this path arrangement.

### R2 — P2: manifest edits during extraction break its recorded provenance

Locations: `backend/ml_pipeline/review.py:50`, `:75`; `backend/ml_pipeline/runtime.py:195`.

The correction function reads bytes once and hashes those bytes. Runtime later reopens the mutable input path using `copyfile`, after local LLM extraction. The original validated bytes are not retained for packaging.

Probe: the original manifest inserts `original correction`; a mocked extraction callback changes its text on disk to `changed after validation` before returning. This models a file edit while a long-running extraction is active.

Expected: the packaged correction file is the exact bytes actually applied, and its hash equals `provenance.reviewed_corrections.manifest_sha256`; alternatively fail explicitly before publishing a mixed result.

Actual:

```text
hash_matches=False
transcript_text=original correction
copied_text=changed after validation
```

Impact: the packaged manifest cannot reproduce the recorded transcript, despite successful completion. SHA verification does reveal the mismatch to a later explicit checker, but runtime itself accepts and publishes the inconsistent bundle. High confidence, conditional on an input file changing during processing. The same lifetime distinction is worth reviewing for the new end-of-run code fingerprint, but that separate concern was not reproduced by modifying production sources.

### R3 — P2: disabling corrections leaves a stale correction file in the bundle

Location: `backend/ml_pipeline/runtime.py:193` (conditional packaging, no corresponding handling of an existing file on an uncorrected run).

Trigger: corrected run into an output directory, then a normal run into the same directory with `reviewed_corrections=None`.

Expected: output contents describe only the current run; a stale correction manifest is absent or unmistakably outside the current result package.

Actual probe:

```text
reviewed_corrections.json exists=True
current provenance has reviewed_corrections=False
```

The current transcript contains no reviewed insertion in this probe, but packaging the directory still includes the old correction manifest. Impact: ambiguous/misleading result artifacts and unsafe manual reproduction when a consumer selects the supplied manifest. A consumer that treats provenance as authoritative can avoid the confusion. High confidence; reproducible without concurrent mutation.

### R4 — P2: an isolated reviewed name attaches to an unrelated much later task

Locations: `backend/ml_pipeline/abstraction.py:295` (`_immediate_direct_address`), `:316` (early return in `_addressed_owner`).

The new direct-address path treats adjacent entries in the transcript list as immediate conversation context. It checks neither time distance nor a topic transition in the action turn. It also accepts a preceding insertion whose `speaker_id` is deliberately unknown.

Minimal executable probe (from `backend`, only Pydantic required):

```python
from ml_pipeline.models import Utterance, Task, Abstraction
from ml_pipeline.abstraction import validate_evidence

turns = [
    Utterance(id="r00001", start_ms=100, end_ms=500,
              speaker_id=None, text="Тимур Болатович"),
    Utterance(id="u00001", start_ms=600000, end_ms=602000,
              speaker_id="S2",
              text="Теперь обсудим станки. Проверьте станок номер три."),
]
task = Task(action="Проверить станок номер три",
            source_utterance_ids=["u00001"], evidence_quote=turns[1].text)
validate_evidence(Abstraction(tasks=[task]), turns)
print(task.responsible, task.source_utterance_ids, task.needs_review)
```

Expected: owner remains unknown: an isolated name ten minutes earlier does not assign this task, particularly after an explicit transition.

Actual: `Тимур Болатович ['u00001', 'r00001'] True`.

Impact: the correction's text is factual, but its downstream use creates an unsupported responsibility link. `needs_review=True` mitigates severity, hence P2. Confidence is high for the deterministic mutation; this synthetic example does not establish that the real meeting-1 insertion is incorrect. The inserted span retaining an anonymous speaker is useful, but alone is insufficient to constrain task attribution.

## Probe evidence and boundaries

R1–R3 used an audio file containing the literal bytes `recording`, valid model-lock placeholders, a single reviewed insertion, empty fake speech output, and a fake LLM returning empty sections. The actual runtime, manifest parsing, audio hash check, insertion merge, artifact writes, manifest copy and provenance generation executed unmodified. Scratch artifacts are in `recheck-probe-data/normal` and `recheck-probe-data/mutated` beside this report. They are synthetic audit fixtures, not meeting results.

R2 can be inspected directly by hashing `recheck-probe-data/mutated/reviewed_corrections.json` and comparing it with that directory's provenance. R3 can be inspected in `normal`: a correction file exists although current provenance omits the correction entry. R1 was observed in the intermediate rerun before the subsequent R3 rerun.

No P0 or P1 was established in this bounded review-flow audit. The addition is an explicit manual correction input, not new evidence of automatic ASR recall improvement. No overlap rejection requirement was assumed: reviewed insertions may intentionally overlap the tail of an ASR turn, as the supplied example does. No new model compatibility claim was made. Parent/independent audit owns full-suite and Brev evidence.
