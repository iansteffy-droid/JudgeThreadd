# System Upgrade Suggestions

## 2026-05-28 — Use `expected_answer` in judge scoring

The `expected_answer` field exists in every Ground Truth Case but is never used anywhere in the evaluation pipeline. Right now judges only compare the RAG-generated answer against `ground_truth_context`. Adding a comparison step that also scores the answer against `expected_answer` would give you a direct quality signal: not just "is the answer grounded in the right context?" but "is the answer actually correct?" This would catch cases where the LLM retrieves the right passage but still produces a wrong answer.

**Concrete action:** In `evaluation_graph.py`, pass `case["expected_answer"]` into `eval_state` and update at least one judge (e.g. Judge Faithful or a new Judge Accuracy) to score similarity between the generated answer and the expected answer.

## 2026-05-28 — Report file lifecycle management

Reports accumulate indefinitely in `data/reports/`. Add a one-click delete button next to each file in the Archived Council Verdicts list (calling a `DELETE /reports/{filename}` endpoint) so old reports can be cleaned up without going into the filesystem manually. This prevents the list from growing unwieldy during heavy batch evaluation sessions.
