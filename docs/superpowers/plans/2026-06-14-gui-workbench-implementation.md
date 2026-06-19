# GUI Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local browser-based GUI workbench for generating daily reviews, generating next-day validations, browsing historical CSV reports, and launching by double-clicking a `.command` file.

**Architecture:** Add a small Python standard-library HTTP server under `src/ghzw/gui.py` that exposes JSON APIs and serves static assets from `src/ghzw/gui_assets/`. The GUI reuses existing pipeline and validation functions; the frontend is plain HTML/CSS/JS with client-side table filtering and sorting.

**Tech Stack:** Python 3.9 standard library, existing `ghzw` modules, browser HTML/CSS/JavaScript, macOS `.command` launcher.

---

## File Structure

- Create `src/ghzw/gui.py`: local HTTP server, report scanning, CSV reading, API handlers, browser launch.
- Create `src/ghzw/gui_assets/index.html`: workbench structure.
- Create `src/ghzw/gui_assets/styles.css`: quiet trading-workbench visual design.
- Create `src/ghzw/gui_assets/app.js`: API calls, table rendering, filtering, sorting, status UI.
- Create `tests/test_gui.py`: pure unit tests for report discovery, CSV JSON conversion, and API validation helpers.
- Create `启动股海贼王.command`: double-click launcher.
- Modify `README.md`: add GUI usage instructions.

## Task 1: Report Discovery And CSV Reading

**Files:**
- Create: `tests/test_gui.py`
- Create: `src/ghzw/gui.py`

- [ ] **Step 1: Write failing tests**

Test `list_reports`, `read_report_csv`, and path safety with temporary CSV files.

- [ ] **Step 2: Run tests and confirm failure**

Run: `PYTHONPATH=src python3 -m unittest tests.test_gui -v`
Expected: import failure for `ghzw.gui`.

- [ ] **Step 3: Implement minimal backend helpers**

Add helper functions in `src/ghzw/gui.py`:

- `list_reports(output_dir: Path) -> list[dict]`
- `read_report_csv(path: Path) -> dict`
- `safe_report_path(base_dir: Path, requested: str) -> Path`
- `json_error(message: str, status: int = 400) -> tuple[int, dict]`

- [ ] **Step 4: Run tests and confirm pass**

Run: `PYTHONPATH=src python3 -m unittest tests.test_gui -v`
Expected: all tests pass.

## Task 2: HTTP API

**Files:**
- Modify: `tests/test_gui.py`
- Modify: `src/ghzw/gui.py`

- [ ] **Step 1: Add tests for request parameter parsing**

Cover valid and invalid dates, default turnover limit, report path validation, and payload normalization.

- [ ] **Step 2: Implement API endpoints**

Add endpoints:

- `GET /api/reports`
- `GET /api/report?path=...`
- `POST /api/run-daily`
- `POST /api/validate`
- `GET /api/health`

The generation endpoints call existing `run_daily_pipeline` and validation helpers.

- [ ] **Step 3: Run tests**

Run: `PYTHONPATH=src python3 -m unittest tests.test_gui -v`
Expected: all tests pass.

## Task 3: Frontend Workbench

**Files:**
- Create: `src/ghzw/gui_assets/index.html`
- Create: `src/ghzw/gui_assets/styles.css`
- Create: `src/ghzw/gui_assets/app.js`
- Modify: `src/ghzw/gui.py`

- [ ] **Step 1: Serve static assets**

`gui.py` serves `/`, `/styles.css`, and `/app.js` from `gui_assets`.

- [ ] **Step 2: Build the page**

Create a single workbench with:

- Daily review form.
- Next-day validation form.
- Historical report list.
- Search/filter/sort table area.
- Status banners for running, success, and errors.

- [ ] **Step 3: Manual asset smoke test**

Run: `PYTHONPATH=src python3 -m ghzw.gui --no-browser --port 8765`
Expected: server starts and serves the page.

## Task 4: Double-Click Launcher

**Files:**
- Create: `启动股海贼王.command`

- [ ] **Step 1: Create launcher**

The launcher changes into the project directory and runs:

```bash
PYTHONPATH=src python3 -m ghzw.gui
```

- [ ] **Step 2: Make executable**

Run: `chmod +x 启动股海贼王.command`
Expected: file becomes executable.

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document GUI usage**

Add instructions for double-click launch and command-line launch.

- [ ] **Step 2: Run full tests**

Run: `PYTHONPATH=src python3 -m unittest discover -s tests -v`
Expected: all tests pass.

- [ ] **Step 3: Verify server starts**

Run: `PYTHONPATH=src python3 -m ghzw.gui --no-browser --port 8765`
Expected: local URL printed; stop server after confirming.

## Notes

- This project directory is not a git repository, so commit steps are intentionally omitted.
- The GUI must show friendly errors while keeping detailed traceback in terminal logs.
- First version must not add external Python or frontend dependencies.
