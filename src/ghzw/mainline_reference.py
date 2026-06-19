from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

from .models import DailyRecord


@dataclass(frozen=True)
class MainlineMatch:
    code: str
    name: str
    mainline: str
    subsector: str
    role: str = ""
    note: str = ""

    @property
    def display_theme(self) -> str:
        return self.mainline

    @property
    def display_sector(self) -> str:
        return self.subsector


@dataclass(frozen=True)
class DisplayTheme:
    display_theme: str
    display_sector: str
    role: str = ""
    note: str = ""


def load_mainline_matches(path: Path | None = None) -> Dict[str, MainlineMatch]:
    source = path or default_mainline_config_path()
    if source is None or not source.exists():
        return {}
    return _parse_mainline_yaml(source.read_text(encoding="utf-8"))


def default_mainline_config_path() -> Path | None:
    candidates = [
        Path.cwd().parent / "A股主线研究学习" / "config" / "mainline_stock_pool.yaml",
        Path(__file__).resolve().parents[3] / "A股主线研究学习" / "config" / "mainline_stock_pool.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def match_record_mainline(record: DailyRecord, matches: Mapping[str, MainlineMatch]) -> DisplayTheme:
    match = matches.get(record.code)
    if match is None:
        match = next((item for item in matches.values() if item.name == record.name), None)
    if match is not None:
        return DisplayTheme(
            display_theme=match.display_theme,
            display_sector=match.display_sector,
            role=match.role,
            note=match.note,
        )
    keyword_match = _match_keyword_rule(record)
    if keyword_match is not None:
        return keyword_match
    return DisplayTheme(
        display_theme=record.core_theme or "未匹配",
        display_sector=_fallback_sector(record),
    )


def _parse_mainline_yaml(text: str) -> Dict[str, MainlineMatch]:
    matches: Dict[str, MainlineMatch] = {}
    mainline = ""
    subsector = ""
    stock: Dict[str, str] = {}

    def flush_stock():
        if stock.get("code") and stock.get("name") and mainline and subsector:
            matches[stock["code"]] = MainlineMatch(
                code=stock["code"],
                name=stock["name"],
                mainline=mainline,
                subsector=subsector,
                role=stock.get("role", ""),
                note=stock.get("note", ""),
            )

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if indent == 2 and stripped.startswith("- name:"):
            flush_stock()
            stock = {}
            mainline = _value_after_colon(stripped)
            subsector = ""
        elif indent == 6 and stripped.startswith("- name:"):
            flush_stock()
            stock = {}
            subsector = _value_after_colon(stripped)
        elif indent == 10 and stripped.startswith("- code:"):
            flush_stock()
            stock = {"code": _value_after_colon(stripped)}
        elif indent >= 12 and ":" in stripped and stock:
            key, value = stripped.split(":", 1)
            stock[key.strip()] = value.strip().strip('"').strip("'")

    flush_stock()
    return matches


def _value_after_colon(text: str) -> str:
    return text.split(":", 1)[1].strip().strip('"').strip("'")


def _match_keyword_rule(record: DailyRecord) -> DisplayTheme | None:
    text = "/".join(
        item
        for item in [
            record.industries,
            record.concepts,
            record.core_theme,
            record.reason_type,
            record.reason_logic,
        ]
        if item
    )
    if not text:
        return None
    normalized = text.lower()
    for mainline, subsector, keywords in _KEYWORD_RULES:
        if any(keyword.lower() in normalized for keyword in keywords):
            return DisplayTheme(
                display_theme=mainline,
                display_sector=subsector,
                role="keyword",
                note="按行业/概念关键词匹配",
            )
    return None


def _fallback_sector(record: DailyRecord) -> str:
    return _compact_industry(record.industries) or record.core_theme or "未匹配"


def _compact_industry(text: str) -> str:
    if not text:
        return ""
    chunks: list[str] = []
    for part in _split_labels(text):
        if not part or part in chunks:
            continue
        chunks.append(part)
        if len(chunks) >= 3:
            break
    return "/".join(chunks)


def _split_labels(text: str) -> Iterable[str]:
    for segment in text.replace("、", "/").replace(",", "/").replace("，", "/").split("/"):
        segment = segment.strip()
        if not segment:
            continue
        yield segment


_KEYWORD_RULES: Sequence[tuple[str, str, Sequence[str]]] = (
    ("AI算力与国产半导体", "PCB与覆铜板", ("PCB", "覆铜板", "封装基板")),
    ("AI算力与国产半导体", "光模块", ("光模块", "光通信", "光器件", "CPO", "硅光")),
    ("AI算力与国产半导体", "先进封装", ("先进封装", "Chiplet", "封测")),
    ("AI算力与国产半导体", "存储", ("高带宽存储器", "HBM", "存储器", "存储模组", "NOR Flash", "DRAM", "NAND", "SSD", "MCU芯片")),
    ("AI算力与国产半导体", "国产AI芯片", ("AI芯片", "GPU", "高性能处理器", "国产芯片", "算力芯片")),
    ("AI算力与国产半导体", "半导体设备", ("半导体设备", "刻蚀设备", "薄膜沉积", "CMP设备", "光刻机")),
    ("AI算力与国产半导体", "半导体材料", ("半导体材料", "电子材料", "靶材", "硅片", "光刻胶", "CMP材料")),
    ("AI算力与国产半导体", "AI服务器", ("AI服务器", "服务器", "算力租赁", "国产算力")),
    ("AI算力与国产半导体", "液冷", ("液冷", "温控")),
    ("AI算力与国产半导体", "电力与数据中心配套", ("数据中心", "UPS", "智能电网", "特高压", "电网自动化", "电力信息化")),
    ("人形机器人", "减速器", ("减速器", "谐波减速器")),
    ("人形机器人", "电机与运动控制", ("电机", "运动控制")),
    ("人形机器人", "传感器", ("传感器", "力传感器", "视觉传感器")),
    ("人形机器人", "执行器", ("执行器",)),
    ("人形机器人", "整机与集成", ("机器人", "工业机器人", "人形机器人")),
    ("创新药", "ADC与双抗", ("ADC", "双抗")),
    ("创新药", "CXO", ("CXO", "CRO", "临床CRO")),
    ("创新药", "医疗器械", ("医疗器械", "高端影像设备")),
    ("创新药", "创新药", ("创新药",)),
    ("低空经济、商业航天与军工", "eVTOL与通航", ("eVTOL", "通航", "低空经济")),
    ("低空经济、商业航天与军工", "空管与通信", ("空管", "通信导航")),
    ("低空经济、商业航天与军工", "卫星与商业航天", ("卫星", "商业航天")),
    ("低空经济、商业航天与军工", "军工装备", ("军工", "航空主机厂", "航空动力")),
    ("防守主线", "红利资产", ("高股息", "红利", "煤炭")),
    ("防守主线", "电力公用事业", ("核电", "公用事业")),
    ("防守主线", "资源品", ("铜", "钴", "金", "资源品")),
)
