# Review Quality Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve daily review quality with local reason attribution, cleaned core themes, role scoring, and market sentiment fields without requiring network access.

**Architecture:** Add focused modules for themes, reasons, and sentiment, then wire them into `pipeline.py` while preserving existing CLI/GUI flows. Existing analysis rules remain available, but market cycle and role labels become driven by richer intermediate data.

**Tech Stack:** Python 3.9 standard library, existing `ghzw` dataclasses and CSV pipeline, unittest.

---

## File Structure

- Create `src/ghzw/themes.py`: noise filtering, alias normalization, cleaned concept memberships, core theme selection.
- Create `src/ghzw/reasons.py`: local CSV reason loading, evidence matching, rule-based suspected reason fallback.
- Create `src/ghzw/sentiment.py`: market sentiment calculation and market-cycle classification.
- Modify `src/ghzw/models.py`: add `ReasonEvidence`, `MarketSentiment`, `RoleAssessment`; extend `DailyRecord`.
- Modify `src/ghzw/analysis.py`: add role scoring while preserving `assign_roles`.
- Modify `src/ghzw/pipeline.py`: use cleaned themes, reason attribution, sentiment, role assessments, and write new fields.
- Modify `src/ghzw/gui_assets/app.js`: prioritize new columns in the GUI table.
- Modify `README.md`: document new fields and local reason CSV.
- Create `tests/test_themes.py`, `tests/test_reasons.py`, `tests/test_sentiment.py`; update existing analysis/pipeline tests.
- Create `data/reasons/reasons.csv` with headers.

## Task 1: Theme Cleaning

- [ ] Write failing tests for noise filtering, alias normalization, cleaned memberships, and core theme selection.
- [ ] Implement `themes.py` minimally.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_themes -v`.

## Task 2: Reason Attribution

- [ ] Write failing tests for local reason CSV loading, date/code matching, priority, and suspected fallback.
- [ ] Implement `reasons.py` minimally.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_reasons -v`.

## Task 3: Market Sentiment

- [ ] Write failing tests for sentiment metrics, yesterday-limit-up performance, summary text, and cycle classification.
- [ ] Implement `sentiment.py` minimally.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_sentiment -v`.

## Task 4: Role Scoring

- [ ] Write failing tests showing role scoring distinguishes leader, capacity core, middle army, supplement, follower, and weak stock.
- [ ] Extend `models.py` and `analysis.py`.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_analysis -v`.

## Task 5: Pipeline Integration

- [ ] Update pipeline tests to assert `核心题材`, `市场情绪`, `角色分`, `角色依据`, and improved `上涨原因`.
- [ ] Wire new modules into `build_daily_records` and `run_daily_pipeline`.
- [ ] Create `data/reasons/reasons.csv` header file.
- [ ] Run `PYTHONPATH=src python3 -m unittest tests.test_pipeline -v`.

## Task 6: GUI And Docs

- [ ] Update GUI priority columns.
- [ ] Update README fields and local reason-library instructions.
- [ ] Run full test suite: `PYTHONPATH=src python3 -m unittest discover -s tests -v`.
- [ ] Run syntax checks: `PYTHONPYCACHEPREFIX=/private/tmp/ghzw_pycache PYTHONPATH=src python3 -m py_compile src/ghzw/themes.py src/ghzw/reasons.py src/ghzw/sentiment.py src/ghzw/analysis.py src/ghzw/pipeline.py` and `node --check src/ghzw/gui_assets/app.js`.

## Notes

- First phase must not require network access.
- Rule-based reasons must be prefixed with `疑似：`.
- `所属概念` remains raw source concepts; `核心题材` is cleaned/canonical.
- This project is not a git repository, so commit steps are omitted.
