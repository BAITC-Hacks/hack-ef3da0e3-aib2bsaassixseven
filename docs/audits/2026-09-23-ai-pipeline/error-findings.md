# AI pipeline: reproduced code defects

Date: 2026-09-23. Scope: current, uncommitted `backend/ml_pipeline` code. Production files were not changed. No inference, model downloads, or remote Brev operations were performed by this reviewer. Findings are synthetic counterexamples against real functions, not claims about frequency in the two meetings. No P0 was established.

## Findings

| ID | Priority | Location | Reproduced defect |
| --- | --- | --- | --- |
| E1 | P1 | `backend/ml_pipeline/abstraction.py:140`, `:72` | Date normalization silently ignores an explicit year and negation. |
| E2 | P1 | `backend/ml_pipeline/abstraction.py:176`, `:446` | Cancelling one contract removes a different contract task. |
| E3 | P1 | `backend/ml_pipeline/abstraction.py:613` | Evidence salvage resurrects a task that validation removed as cancelled. |
| E4 | P2 | `backend/ml_pipeline/abstraction.py:220`, `:332` | An earlier addressee is promoted to task owner after an explicit topic change. |
| E5 | P2 | `backend/ml_pipeline/compare.py:80` | Deadline scoring cannot detect incorrect relative deadlines when dates are null. |

### E1: explicit year and negation produce wrong, supposedly certain dates

With meeting date `2026-09-23`, actual calls return:

```python
normalize_deadline("до 2 октября 2027 года", meeting)
# (date(2026, 10, 2), False) -- should preserve 2027, or abstain.
normalize_deadline("не завтра, а через три дня", meeting)
# (date(2026, 9, 24), False) -- tomorrow is explicitly negated.
```

The named-month parser hardcodes `today.year`; the relative parser selects the first recognized expression without resolving negation. `False` is the uncertainty flag, so downstream `finalize_deadlines` can publish the wrong date without adding review for the date. This is independent of ASR/LLM quality. Confidence: high, directly reproduced. Scope: these constructions; not every date is wrong.

### E2: a shared four-letter stem causes cross-task cancellation

Input transcript:

- u1: `Подготовьте договор поставки оборудования.`
- u2: `Договор аренды офиса отменяем.`

A task with action `Подготовить договор поставки оборудования`, evidence equal to u1, and source `[u1]` is removed by `validate_evidence`. Actual `abstraction.tasks == []`.

`_subject_overlap` accepts one common stem occurring in at most two transcript utterances. `дого` therefore links supply and office rental contracts. The cancellation pass then deletes the task, without leaving a validation warning. Consequence: valid assignments silently disappear. Confidence: high, directly reproduced. A same-topic cancellation should still work; the missing distinction is task/object identity.

### E3: salvage bypasses the validator's task removal

Transcript u1 `Проверьте договор.` followed by u2 `Проверку договора отменяем.`. The scripted generator repeatedly returns a task quoting u1 plus one invalid fact with quote `absent`.

After three evidence attempts, `_parse_with_evidence` enters item-by-item salvage. `validate_evidence(single, ...)` correctly empties `single.tasks`, but line 613 appends the original `item` instead of consuming the filtered collection. Actual result contains the cancelled task. Only the bad fact is reported as dropped.

Consequence: a model's unrelated citation error changes cancellation semantics and revives inactive assignments. Confidence: high, directly reproduced with a deterministic generator; no model calls required. The fallback-state branch also warrants a cancellation regression test, but that separate branch was not established as a finding here.

### E4: owner inference crosses a topic boundary

Three turns from the same chair:

- u1: `Айнур Каировна, подготовьте отчёт.`
- u2: `Теперь обсудим обслуживание станков.`
- u3: `Проверьте станок номер три.`

Task u3 initially has `responsible=None`. Validation sets it to `Айнур Каировна` and appends u1 to its sources. No turn actually assigns the machine inspection to her. The four-turn lookback has no topic/reset or explicit task-link condition. `needs_review=True` mitigates severity, but the structured owner field and rendered summary still contain the inferred person. Confidence: high for the observed mutation; actual conversational intention is unknown, hence owner should remain unresolved rather than be asserted.

### E5: null dates hide relative deadline errors in evaluation

`score_tasks` receives identical action/owner, reference `due_date=None, due_text="tomorrow"`, and prediction `due_date=None, due_text="in three weeks"`. Actual `deadline_errors=0`.

Only `due_date` is compared. For recordings without meeting dates, the documented pipeline correctly leaves relative dates null; this makes incorrect, omitted, stale and correct relative deadlines indistinguishable to this metric. The existing manifest does not require an annotated relative deadline field. This is an evaluation limitation, not a claim that the metric violates its narrow date-only implementation. It matters when interpreting it as task/deadline quality for the two undated meetings. Confidence: high, directly reproduced.

## Minimal combined reproduction

Run from `backend` with its existing `.venv/Scripts/python.exe`; requires only Pydantic and standard library, no ML packages. On Windows set `PYTHONIOENCODING=utf-8` for readable Cyrillic output.

```python
import json
from datetime import datetime
from ml_pipeline.abstraction import normalize_deadline, validate_evidence, _parse_with_evidence
from ml_pipeline.models import Utterance, Task, Abstraction
from ml_pipeline.compare import score_tasks

def u(i, text):
    return Utterance(id=f"u{i}", start_ms=i*1000, end_ms=(i+1)*1000,
                     speaker_id="S1", text=text)

meeting = datetime(2026, 9, 23)
print(normalize_deadline("до 2 октября 2027 года", meeting))
print(normalize_deadline("не завтра, а через три дня", meeting))

turns = [u(1, "Подготовьте договор поставки оборудования."),
         u(2, "Договор аренды офиса отменяем.")]
task = Task(action="Подготовить договор поставки оборудования",
            source_utterance_ids=["u1"], evidence_quote=turns[0].text)
result = Abstraction(tasks=[task])
validate_evidence(result, turns)
print("cross_task_cancellation", result.model_dump())

turns = [u(1, "Айнур Каировна, подготовьте отчёт."),
         u(2, "Теперь обсудим обслуживание станков."),
         u(3, "Проверьте станок номер три.")]
task = Task(action="Проверить станок номер три",
            source_utterance_ids=["u3"], evidence_quote=turns[2].text)
result = Abstraction(tasks=[task])
validate_evidence(result, turns)
print("stale_owner", task.responsible)

turns = [u(1, "Проверьте договор."), u(2, "Проверку договора отменяем.")]
task = Task(action="Проверить договор", source_utterance_ids=["u1"],
            evidence_quote=turns[0].text)
class Generator:
    def generate(self, prompt):
        return json.dumps({
            "key_facts": [{"text": "bad", "source_utterance_ids": ["u1"],
                           "evidence_quote": "absent"}],
            "decisions": [], "tasks": [task.model_dump(mode="json")],
        })
warnings = []
result = _parse_with_evidence(Generator(), "probe", turns, warnings)
print("resurrected_tasks", len(result.tasks), warnings)

base = dict(action="Prepare report", responsible=None, due_date=None)
print(score_tasks([dict(base, due_text="tomorrow")],
                  [dict(base, due_text="in three weeks")]))
```

## Validation and limits

`tests/test_ml_pipeline.py` + `tests/test_ml_real_regressions.py`: **43 passed in 0.18s** on current local code, using `.venv/Scripts/python.exe -m pytest ... -q -p no:cacheprovider`. Thus the above defects are not covered by those passing tests.

The initial five-file test command could not collect `test_ml_audio_contract.py` because this local environment lacks NumPy. An initial attempt at the wider non-audio subset also used a nonexistent parent for the temporary directory; that is test-harness setup, not a repository defect. No inference accuracy or GPU compatibility conclusion follows from these unit tests.

Potential concerns deliberately not promoted to confirmed defects: Rukk blank-token/index logic (research agent reports it agrees with upstream model README); missing sub-100ms speech; whole-utterance speaker contamination from Community-1; interrupted runs losing transcript checkpoints; model-directory/lock drift. These need separate targeted evidence or are documented design limits.

The independent verifier separately confirmed E1/E2/E3 with its own execution and reported 62 non-audio plus 9 audio-contract tests passing in its available runtime. This does not replace real-model or acoustic evaluation.

## Archived results versus current validator

I loaded `Downloads/meeting-1-results.zip` and `meeting-2-results.zip` directly, parsed the complete archived transcript and abstraction, and ran only current `validate_evidence`. No files in the archives were altered. Both replay calls completed without exceptions.

- Meeting 1 retained all 10 tasks; it added owners to archived tasks 6 (Гульмира Сериковна), 9 (Нурлан Сагатович), and 10 (Айнур Каировна).
- Meeting 2 retained all 8 tasks. Task 2's archived stale deadline changed from `за две недели` to `неделя максимум десять дней`, with a conflict warning. Tasks 6 and 7 lost the incorrectly shared `не больше недели` deadline. Their owners also changed from Салтанат Ерболовна to null.
- Meeting 2 task 3 gained Жандос Талгатович. Task 4 (brief after contractor meeting) changed from Ерболат Мухтарович to Жандос Талгатович. These owner changes are outputs of the heuristic, not independently established speaker/name correctness. The known fused turn around 93.080–98.412 seconds still requires acoustic verification.

Therefore the archive's supplier deadline and template deadline leakage should be reported as **historical defects corrected in current validator replay**, not as proof those exact outputs remain in the current code. Conversely, current replay is not a fresh end-to-end inference run and does not establish that extraction recalls all tasks or that the newly inferred owners are correct.
