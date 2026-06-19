# Futu And CNINFO Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Futu and CNINFO as real evidence providers for daily review reasons while preserving local reasons and suspected-rule fallback.

**Architecture:** Keep reason selection in `reasons.py`, add a direct CNINFO HTTP client with standard-library requests, and expose Futu evidence through the existing `FutuAShareClient`. Pipeline gathers evidence based on `--evidence-source` and resolves the best reason per stock.

**Tech Stack:** Python 3.9 standard library, existing Futu OpenD client, CNINFO public HTTP endpoints, unittest.

---

## File Structure

- Create `src/ghzw/cninfo_client.py`: CNINFO announcement and IRM evidence provider.
- Modify `src/ghzw/reasons.py`: evidence-source selection, evidence priority, resolved reason metadata.
- Modify `src/ghzw/futu_client.py`: Futu evidence provider method.
- Modify `src/ghzw/models.py`: add reason source/time fields to `DailyRecord`.
- Modify `src/ghzw/pipeline.py`: gather online evidence and write source/time fields.
- Modify `src/ghzw/cli.py`: add `--evidence-source`.
- Modify `src/ghzw/gui.py` and `src/ghzw/gui_assets/index.html`: expose evidence-source selection.
- Add tests for reason priority, Futu evidence normalization, CNINFO parsing/building.

## Task 1: Reason Resolution Metadata

- [ ] Write failing tests for selecting best evidence across local, CNINFO, Futu, and suspected reasons.
- [ ] Extend `reasons.py` with `ResolvedReason`, `resolve_reason_details`, and source priority.
- [ ] Extend `DailyRecord` fields: `reason_source`, `evidence_time`.

## Task 2: Futu Evidence Provider

- [ ] Write tests using a fake Futu context/client for research rating, buyback/dividend, and shareholder/insider evidence normalization.
- [ ] Add `get_reason_evidence(trade_date, codes)` to `FutuAShareClient`.
- [ ] Make every Futu sub-call failure non-fatal.

## Task 3: CNINFO Evidence Provider

- [ ] Write tests for CNINFO announcement JSON parsing and IRM JSON parsing.
- [ ] Implement `CninfoEvidenceProvider` with timeout, code normalization, announcement query, and IRM query.
- [ ] Ensure network failure returns no evidence and logs warning.

## Task 4: Pipeline And UI Wiring

- [ ] Add `evidence_source` to `run_daily_pipeline` and `build_daily_records`.
- [ ] Add CLI `--evidence-source`.
- [ ] Add GUI evidence-source select.
- [ ] Include `原因来源` and `证据时间` in CSV/GUI.

## Task 5: Docs And Verification

- [ ] Update README with Futu/CNINFO evidence-source behavior.
- [ ] Run full test suite.
- [ ] Run syntax checks for Python and JS.

## Notes

- Online providers must not block report generation on failure.
- Default `auto` means local + Futu + CNINFO + suspected fallback.
- Choice/Wind/iFinD are explicitly out of scope for this implementation.
