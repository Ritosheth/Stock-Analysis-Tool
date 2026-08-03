# Position Lifecycle Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic high-position lifecycle risk scoring and a manual watchlist to daily review outputs.

**Architecture:** Put pure risk scoring and watchlist loading in `src/ghzw/lifecycle.py`, feed the result from `pipeline.py` into `DailyRecord`, and render the fields in CSV, HTML, and GUI. Keep the first version deterministic and based only on existing snapshots, history bars, and core theme grouping.

**Tech Stack:** Python dataclasses and unittest for backend logic; existing static HTML renderer and vanilla JS GUI table.

---

## File Structure

- Create `src/ghzw/lifecycle.py`: watchlist parsing and lifecycle risk scoring.
- Modify `src/ghzw/models.py`: add lifecycle fields to `DailyRecord.as_dict`.
- Modify `src/ghzw/pipeline.py`: merge watchlist codes into targets and attach lifecycle risk.
- Modify `src/ghzw/reporting.py`: add “强转弱观察” section.
- Modify `src/ghzw/gui_assets/app.js`: prioritize and filter lifecycle columns.
- Create `tests/test_lifecycle.py`: scorer and watchlist tests.
- Modify `tests/test_pipeline.py`: watchlist target inclusion.
- Modify `tests/test_reporting.py`: HTML lifecycle section.
- Modify `tests/test_gui_assets.py`: GUI column/filter constants.

## Tasks

### Task 1: Lifecycle Scoring Module

**Files:**
- Create: `src/ghzw/lifecycle.py`
- Test: `tests/test_lifecycle.py`

- [ ] Write tests for `load_watchlist` with missing file and normal CSV.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_lifecycle.py -q` and verify the module is missing.
- [ ] Implement `WatchlistEntry`, `LifecycleRisk`, `load_watchlist`, and `assess_lifecycle_risks`.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_lifecycle.py -q` and verify the tests pass.

### Task 2: DailyRecord Output Fields

**Files:**
- Modify: `src/ghzw/models.py`
- Test: `tests/test_models.py`

- [ ] Add a failing test that `DailyRecord.as_dict()` contains `观察备注`, `强转弱阶段`, `强转弱风险分`, `强转弱信号`, and `观察纪律`.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_models.py -q` and verify failure.
- [ ] Add the five fields to `DailyRecord`.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_models.py -q`.

### Task 3: Pipeline Integration

**Files:**
- Modify: `src/ghzw/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] Add a failing test that a watchlist stock not in limit-up or turnover TopN is included in records when snapshot data exists.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_pipeline.py -q` and verify failure.
- [ ] Add `watchlist_entries` to `build_daily_records`, merge watchlist codes into target codes, and attach lifecycle risk.
- [ ] Load `data/watchlist.csv` in `run_daily_pipeline`.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_pipeline.py -q`.

### Task 4: HTML Report Section

**Files:**
- Modify: `src/ghzw/reporting.py`
- Test: `tests/test_reporting.py`

- [ ] Add a failing test that HTML contains “强转弱观察” and a lifecycle signal.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_reporting.py -q` and verify failure.
- [ ] Add context filtering and section rendering.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_reporting.py -q`.

### Task 5: GUI Table Columns

**Files:**
- Modify: `src/ghzw/gui_assets/app.js`
- Test: `tests/test_gui_assets.py`

- [ ] Add a failing test that GUI assets include the lifecycle headers and filter.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_gui_assets.py -q` and verify failure.
- [ ] Add lifecycle headers to `priorityHeaders` and `强转弱阶段` to `filterFields`.
- [ ] Run `PYTHONPATH=src python3 -m pytest tests/test_gui_assets.py -q`.

### Task 6: Full Verification

**Files:**
- All touched files

- [ ] Run `PYTHONPATH=src python3 -m pytest -q`.
- [ ] Inspect `git diff --stat` and `git diff --check`.
- [ ] Update README with watchlist usage if the full test run is clean.

## Self-Review

- Spec coverage: daily scoring, watchlist, CSV, HTML, GUI, and tests are covered.
- Placeholder scan: no TBD/TODO/fill-in placeholders remain.
- Type consistency: `LifecycleRisk` fields map directly to new `DailyRecord` fields.
