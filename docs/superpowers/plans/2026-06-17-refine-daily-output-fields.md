# Refine Daily Output Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make daily review outputs use finer-grained sector labels, show the board count for limit-up stocks, and display turnover in units of 100 million yuan.

**Architecture:** Keep raw financial values in yuan inside `DailyRecord` so scoring, sorting, and validation stay stable. Add deterministic presentation helpers in `themes.py`, `models.py`, and `pipeline.py`; then update CSV readers and GUI column priorities to match the new output schema.

**Tech Stack:** Python 3.9 standard library, `unittest`, existing `ghzw` package modules, static browser assets in plain JavaScript.

---

## File Structure

- Modify `src/ghzw/themes.py`: add refined industry/sector formatting based on industry memberships plus high-signal concept plate memberships.
- Modify `tests/test_themes.py`: cover refined sector formatting and noise filtering.
- Modify `src/ghzw/models.py`: add `limit_up_boards` to `DailyRecord`, output `成交额(亿元)` instead of raw `成交额`, and keep internal `turnover` as yuan.
- Create `tests/test_models.py`: cover `DailyRecord.as_dict()` output headers and display units.
- Modify `src/ghzw/pipeline.py`: pass refined industry labels and limit-up board labels into `DailyRecord`; update empty CSV headers.
- Modify `tests/test_pipeline.py`: verify refined `所属行业`, `涨停板数`, and internal turnover behavior.
- Modify `src/ghzw/validation.py`: read both old `成交额` reports and new `成交额(亿元)` reports.
- Modify `tests/test_validation.py`: cover the new report reader unit conversion.
- Modify `src/ghzw/gui_assets/app.js`: prioritize `涨停板数` and `成交额(亿元)` columns in the workbench.
- Modify `tests/test_gui_assets.py`: assert the GUI priority list uses the new headers.
- Modify `README.md`: update output field documentation and explain the display units.

### Task 1: Refined Sector Labels

**Files:**
- Modify: `src/ghzw/themes.py`
- Modify: `tests/test_themes.py`

- [ ] **Step 1: Write the failing theme tests**

Append this test to `tests/test_themes.py` and update the import line to include `refine_industry_names`:

```python
from ghzw.themes import clean_plate_memberships, clean_theme_names, refine_industry_names, select_core_theme
```

```python
    def test_refine_industry_names_uses_high_signal_concepts_under_industry(self):
        memberships = [
            PlateMembership(code="HY001", name="半导体", plate_type="INDUSTRY"),
            PlateMembership(code="GN001", name="融资融券", plate_type="CONCEPT"),
            PlateMembership(code="GN002", name="存储器", plate_type="CONCEPT"),
            PlateMembership(code="GN003", name="MCU芯片", plate_type="CONCEPT"),
            PlateMembership(code="GN004", name="昨日首板", plate_type="CONCEPT"),
        ]

        result = refine_industry_names(memberships)

        self.assertEqual(result, "半导体-存储器/MCU芯片")

    def test_refine_industry_names_falls_back_to_industry_when_no_detail_exists(self):
        memberships = [
            PlateMembership(code="HY002", name="银行", plate_type="INDUSTRY"),
            PlateMembership(code="GN001", name="融资融券", plate_type="CONCEPT"),
        ]

        result = refine_industry_names(memberships)

        self.assertEqual(result, "银行")
```

- [ ] **Step 2: Run the theme tests to verify failure**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_themes -v
```

Expected: FAIL with `ImportError: cannot import name 'refine_industry_names'`.

- [ ] **Step 3: Add refined sector implementation**

Add this code to `src/ghzw/themes.py` after `_ALIAS_BY_NAME`:

```python
DETAIL_THEME_NAMES = {
    "存储器",
    "MCU芯片",
    "汽车芯片",
    "先进封装(Chiplet)",
    "高带宽存储器HBM",
    "半导体设备概念",
    "半导体材料概念",
    "光刻胶",
    "光刻机",
    "OLED",
    "MiniLED",
    "MicroLED",
    "柔性屏",
    "PCB概念",
    "玻璃基板封装",
    "消费电子代工",
    "被动元件概念",
    "MLCC",
    "机器人概念",
    "人形机器人",
    "机器视觉",
    "工业母机",
    "工业4.0",
    "新型工业化",
    "智能电网",
    "特高压",
    "储能概念",
    "充电桩",
    "光伏概念",
    "固态电池",
    "电子树脂",
    "创新药",
    "中药概念",
    "生物医药",
    "新冠药物",
    "医疗器械概念",
    "健康中国",
    "电子布",
    "水利建设",
    "新型城镇化建设",
    "铝概念",
    "铜概念",
}
```

Add this function to `src/ghzw/themes.py` after `clean_plate_memberships`:

```python
def refine_industry_names(memberships: Sequence[PlateMembership], max_details: int = 3) -> str:
    industries: List[str] = []
    details: List[str] = []
    for item in memberships:
        name = normalize_theme_name(item.name)
        if not name:
            continue
        plate_type = item.plate_type.upper()
        if plate_type == "INDUSTRY" and name not in industries:
            industries.append(name)
            continue
        if plate_type == "CONCEPT" and name in DETAIL_THEME_NAMES and name not in details:
            details.append(name)

    if not industries:
        return "、".join(details[:max_details])
    if not details:
        return "、".join(industries)
    detail_text = "/".join(details[:max_details])
    return "、".join("%s-%s" % (industry, detail_text) for industry in industries)
```

- [ ] **Step 4: Run the theme tests to verify pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_themes -v
```

Expected: PASS, including both new refined sector tests.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add src/ghzw/themes.py tests/test_themes.py
git commit -m "feat: refine industry output with detailed plates"
```

Expected: Commit succeeds.

### Task 2: DailyRecord Display Schema

**Files:**
- Modify: `src/ghzw/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_models.py` with this content:

```python
import unittest

from ghzw.models import DailyRecord


class DailyRecordModelTest(unittest.TestCase):
    def test_as_dict_outputs_turnover_in_yi_and_limit_up_boards(self):
        record = DailyRecord(
            date="2026-06-17",
            code="SH.600001",
            name="Alpha",
            record_type="涨停",
            close_price=11,
            prev_close_price=10,
            change_pct=10,
            turnover=1_234_567_890,
            turnover_rate=8.88,
            volume_ratio=1.23,
            industries="半导体-存储器/MCU芯片",
            concepts="存储器",
            market_cycle="上升",
            theme_rank=1,
            theme_tier="主线",
            role="龙头",
            stage="连板",
            next_action="观察验证",
            net_inflow=100,
            main_net_inflow=50,
            reason_type="不明",
            review="测试",
            limit_up_boards="2板",
        )

        result = record.as_dict()

        self.assertEqual(result["涨停板数"], "2板")
        self.assertNotIn("成交额", result)
        self.assertEqual(result["成交额(亿元)"], 12.35)
        self.assertEqual(record.turnover, 1_234_567_890)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the model tests to verify failure**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_models -v
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'limit_up_boards'`.

- [ ] **Step 3: Add display fields to DailyRecord**

In `src/ghzw/models.py`, add this field to `DailyRecord` after `record_type`:

```python
    limit_up_boards: str = ""
```

In `DailyRecord.as_dict()`, replace the `"类型"` and `"成交额"` entries with these entries in the same relative positions:

```python
            "类型": self.record_type,
            "涨停板数": self.limit_up_boards,
            "收盘价": round(self.close_price, 3),
            "昨收": round(self.prev_close_price, 3),
            "涨幅": round(self.change_pct, 2),
            "成交额(亿元)": round(self.turnover / 100_000_000, 2),
```

- [ ] **Step 4: Run the model tests to verify pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_models -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add src/ghzw/models.py tests/test_models.py
git commit -m "feat: output turnover in yi and board count"
```

Expected: Commit succeeds.

### Task 3: Pipeline Sector And Board Labels

**Files:**
- Modify: `src/ghzw/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing pipeline assertions**

In `tests/test_pipeline.py`, update the `memberships` for `SH.600001` in `test_build_daily_records_merges_limit_up_turnover_theme_stage_and_flow` to include detailed concepts:

```python
            "SH.600001": [
                PlateMembership(code="HY001", name="半导体", plate_type="INDUSTRY"),
                PlateMembership(code="GN000", name="融资融券", plate_type="CONCEPT"),
                PlateMembership(code="GN001", name="存储器", plate_type="CONCEPT"),
                PlateMembership(code="GN002", name="MCU芯片", plate_type="CONCEPT"),
                PlateMembership(code="GN003", name="人工智能", plate_type="CONCEPT"),
            ],
```

Replace these two assertions:

```python
        self.assertEqual(by_code["SH.600001"].industries, "软件服务")
        self.assertEqual(by_code["SH.600001"].concepts, "人工智能")
```

with:

```python
        self.assertEqual(by_code["SH.600001"].industries, "半导体-存储器/MCU芯片")
        self.assertEqual(by_code["SH.600001"].concepts, "存储器、MCU芯片、人工智能")
        self.assertEqual(by_code["SH.600001"].limit_up_boards, "1板")
        self.assertEqual(by_code["SH.600001"].as_dict()["涨停板数"], "1板")
        self.assertEqual(by_code["SH.600001"].as_dict()["成交额(亿元)"], 0.0)
```

Add this test to `PipelineTest`:

```python
    def test_limit_up_board_label_falls_back_to_news_consecutive_board_text(self):
        snapshots = [
            StockSnapshot(
                code="SH.600003",
                name="Gamma",
                last_price=10.98,
                prev_close_price=10,
                turnover=100_000_000,
            )
        ]
        memberships = {
            "SH.600003": [
                PlateMembership(code="HY003", name="工业金属", plate_type="INDUSTRY"),
                PlateMembership(code="GN003", name="铝概念", plate_type="CONCEPT"),
            ]
        }

        records = build_daily_records(
            trade_date=date(2026, 6, 17),
            snapshots=snapshots,
            memberships_by_code=memberships,
            history_by_code={"SH.600003": []},
            capital_flow_by_code={"SH.600003": CapitalFlow(code="SH.600003")},
            turnover_limit=0,
            online_reasons=[
                ReasonEvidence(
                    date="2026-06-17",
                    code="SH.600003",
                    reason_type="新闻",
                    summary="3连板Gamma：生产经营正常",
                    source="东方财富新闻",
                    published_at="2026-06-17 17:00:00",
                )
            ],
        )

        self.assertEqual(records[0].limit_up_boards, "3板")
        self.assertEqual(records[0].industries, "工业金属-铝概念")
```

- [ ] **Step 2: Run the pipeline tests to verify failure**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_pipeline -v
```

Expected: FAIL because `limit_up_boards` is empty and `industries` still uses raw industry names.

- [ ] **Step 3: Add pipeline formatting helpers**

Update the imports at the top of `src/ghzw/pipeline.py`:

```python
import csv
import re
from collections import defaultdict
```

Update the themes import line:

```python
from .themes import clean_plate_memberships, refine_industry_names, select_core_theme
```

In `build_daily_records`, replace:

```python
        memberships = list(memberships_by_code.get(code, []))
```

with:

```python
        memberships = list(cleaned_memberships_by_code.get(code, []))
        raw_memberships = list(memberships_by_code.get(code, []))
```

Before constructing `DailyRecord`, add:

```python
        record_type = _record_type(code, limit_up_codes, turnover_top_codes)
        limit_up_boards = _limit_up_board_label(record_type, stage, candidate_reasons)
```

Within the `DailyRecord(...)` call, replace each repeated `_record_type(...)` argument in that block with `record_type`, set `limit_up_boards=limit_up_boards`, and replace:

```python
                industries=_join_plates(memberships, "INDUSTRY"),
```

with:

```python
                industries=refine_industry_names(raw_memberships),
```

Add these helper functions above `_record_type`:

```python
def _limit_up_board_label(record_type: str, stage: StageTag, evidences: Sequence) -> str:
    if record_type not in {"涨停", "两者都是"}:
        return ""
    if stage.board_streak > 0:
        return "%d板" % stage.board_streak
    evidence_streak = _board_streak_from_evidences(evidences)
    if evidence_streak > 0:
        return "%d板" % evidence_streak
    return "1板"


def _board_streak_from_evidences(evidences: Sequence) -> int:
    streaks: List[int] = []
    for evidence in evidences:
        text = "%s %s" % (getattr(evidence, "summary", ""), getattr(evidence, "reason_type", ""))
        streaks.extend(int(match) for match in re.findall(r"(\d+)连板", text))
    return max(streaks) if streaks else 0
```

In `write_csv`, update the empty header list by inserting `"涨停板数"` after `"类型"` and replacing `"成交额"` with `"成交额(亿元)"`.

- [ ] **Step 4: Run the pipeline tests to verify pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_pipeline -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```bash
git add src/ghzw/pipeline.py tests/test_pipeline.py
git commit -m "feat: enrich daily pipeline output labels"
```

Expected: Commit succeeds.

### Task 4: Validation Reader Compatibility

**Files:**
- Modify: `src/ghzw/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Write the failing validation reader test**

Add these imports to `tests/test_validation.py`:

```python
from io import StringIO
from unittest.mock import mock_open, patch
from pathlib import Path
```

Update the validation import:

```python
from ghzw.validation import read_daily_records_csv, validate_next_day
```

Add this test to `ValidationTest`:

```python
    def test_read_daily_records_csv_converts_new_turnover_yi_header_to_yuan(self):
        csv_text = (
            "日期,代码,名称,类型,涨停板数,收盘价,昨收,涨幅,成交额(亿元),换手率,量比,所属行业,所属概念,"
            "核心题材,市场阶段,市场情绪,题材强度排名,题材层级,个股地位,角色分,角色依据,阶段,次日计划,"
            "资金流-净流入,资金流-主力净流入,上涨逻辑,驱动类型,上涨原因,原因来源,证据时间,一句话复盘\n"
            "2026-06-17,SH.600001,Alpha,涨停,2板,11,10,10,12.35,8,1.2,半导体-存储器,存储器,"
            "存储器,上升,涨停1/跌停0/上涨60%/连板高2/昨板无数据,1,主线,龙头,40,连板2,连板,观察验证,"
            "100,50,逻辑,题材发酵,原因,规则推断,2026-06-17,复盘\n"
        )

        with patch("pathlib.Path.open", mock_open(read_data=csv_text)):
            records = read_daily_records_csv(Path("daily.csv"))

        self.assertEqual(records[0].turnover, 1_235_000_000)
        self.assertEqual(records[0].limit_up_boards, "2板")
```

- [ ] **Step 2: Run validation tests to verify failure**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_validation -v
```

Expected: FAIL because `_row_to_record` does not read `成交额(亿元)` and does not pass `limit_up_boards`.

- [ ] **Step 3: Update validation row parsing**

In `src/ghzw/validation.py`, replace:

```python
        turnover=_float(row.get("成交额")),
```

with:

```python
        turnover=_daily_turnover_yuan(row),
```

Add this argument after `record_type=row.get("类型", ""),`:

```python
        limit_up_boards=row.get("涨停板数", ""),
```

Add this helper above `_float`:

```python
def _daily_turnover_yuan(row: Mapping[str, str]) -> float:
    if row.get("成交额(亿元)") not in (None, ""):
        return round(_float(row.get("成交额(亿元)")) * 100_000_000, 2)
    return _float(row.get("成交额"))
```

- [ ] **Step 4: Run validation tests to verify pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_validation -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add src/ghzw/validation.py tests/test_validation.py
git commit -m "feat: read daily reports with yi turnover"
```

Expected: Commit succeeds.

### Task 5: GUI And Documentation Alignment

**Files:**
- Modify: `src/ghzw/gui_assets/app.js`
- Modify: `tests/test_gui_assets.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing GUI asset test**

Add this test to `tests/test_gui_assets.py`:

```python
    def test_daily_output_headers_include_board_count_and_yi_turnover(self):
        app_js = Path("src/ghzw/gui_assets/app.js").read_text(encoding="utf-8")
        match = re.search(r"const priorityHeaders = \[(.*?)\];", app_js, flags=re.S)
        self.assertIsNotNone(match)

        block = match.group(1)
        type_index = block.index('"类型"')
        boards_index = block.index('"涨停板数"')
        turnover_index = block.index('"成交额(亿元)"')

        self.assertLess(type_index, boards_index)
        self.assertLess(boards_index, turnover_index)
        self.assertNotIn('"成交额"', block)
```

- [ ] **Step 2: Run GUI asset tests to verify failure**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_gui_assets -v
```

Expected: FAIL because `priorityHeaders` still contains `"成交额"` and does not contain `"涨停板数"`.

- [ ] **Step 3: Update GUI priority headers**

In `src/ghzw/gui_assets/app.js`, replace this block:

```javascript
  "类型",
  "收盘价",
  "涨幅",
  "成交额",
```

with:

```javascript
  "类型",
  "涨停板数",
  "收盘价",
  "涨幅",
  "成交额(亿元)",
```

- [ ] **Step 4: Update README output field documentation**

In `README.md`, replace the output field list around `类型` and `成交额` with:

```text
类型
涨停板数
收盘价
昨收
涨幅
成交额(亿元)
换手率
量比
所属行业
所属概念
```

Add this sentence below the output field list:

```markdown
`成交额(亿元)` 仅用于日报展示，内部计算仍使用原始元单位；`所属行业` 会优先展示行业-细分板块，例如 `半导体-存储器/MCU芯片`。
```

- [ ] **Step 5: Run GUI asset tests to verify pass**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_gui_assets -v
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```bash
git add src/ghzw/gui_assets/app.js tests/test_gui_assets.py README.md
git commit -m "docs: align daily output field names"
```

Expected: Commit succeeds.

### Task 6: Full Regression And Sample Output Check

**Files:**
- Verify only; no planned source edits in this task.

- [ ] **Step 1: Run the complete test suite**

Run:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: PASS for all tests.

- [ ] **Step 2: Generate a small in-memory CSV smoke check**

Run:

```bash
PYTHONPATH=src python3 - <<'PY'
from datetime import date
from pathlib import Path
from ghzw.models import CapitalFlow, DailyBar, PlateMembership, StockSnapshot
from ghzw.pipeline import build_daily_records, write_csv

records = build_daily_records(
    trade_date=date(2026, 6, 17),
    snapshots=[StockSnapshot(code="SH.600001", name="Alpha", last_price=11, prev_close_price=10, turnover=1_235_000_000)],
    memberships_by_code={
        "SH.600001": [
            PlateMembership(code="HY001", name="半导体", plate_type="INDUSTRY"),
            PlateMembership(code="GN001", name="存储器", plate_type="CONCEPT"),
            PlateMembership(code="GN002", name="MCU芯片", plate_type="CONCEPT"),
        ]
    },
    history_by_code={
        "SH.600001": [
            DailyBar(code="SH.600001", date="2026-06-16", close=10, change_pct=0),
            DailyBar(code="SH.600001", date="2026-06-17", close=11, change_pct=10),
        ]
    },
    capital_flow_by_code={"SH.600001": CapitalFlow(code="SH.600001")},
    turnover_limit=0,
)
path = write_csv(records, Path("/tmp/ghzw-output-smoke.csv"))
text = path.read_text(encoding="utf-8-sig")
assert "涨停板数" in text
assert "成交额(亿元)" in text
assert "半导体-存储器/MCU芯片" in text
assert ",1板," in text
assert ",12.35," in text
print("smoke ok")
PY
```

Expected: prints `smoke ok`.

- [ ] **Step 3: Check git diff for intended scope**

Run:

```bash
git diff --stat HEAD~5..HEAD
```

Expected: changed files are limited to `src/ghzw/themes.py`, `tests/test_themes.py`, `src/ghzw/models.py`, `tests/test_models.py`, `src/ghzw/pipeline.py`, `tests/test_pipeline.py`, `src/ghzw/validation.py`, `tests/test_validation.py`, `src/ghzw/gui_assets/app.js`, `tests/test_gui_assets.py`, and `README.md`.

## Self-Review

- Spec coverage: refined sector labels are covered in Tasks 1 and 3; limit-up board labels are covered in Tasks 2 and 3; turnover in 100 million yuan is covered in Tasks 2, 4, and 5.
- Placeholder scan: the plan contains concrete paths, exact tests, exact implementation snippets, exact commands, and expected results.
- Type consistency: `DailyRecord.limit_up_boards` is introduced in Task 2, passed by `pipeline.py` in Task 3, and read by `validation.py` in Task 4. `成交额(亿元)` is produced by `DailyRecord.as_dict()`, listed in empty CSV headers, read by validation compatibility code, and prioritized by the GUI.
