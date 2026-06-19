from __future__ import annotations

from typing import Iterable, List, Mapping, Sequence

from .models import PlateMembership


NOISE_THEME_NAMES = {
    "融资融券",
    "转融券标的",
    "深股通",
    "沪股通",
    "MSCI概念",
    "标普道琼斯中国",
    "纳入富时罗素",
    "昨日首板",
    "昨日触板",
    "昨日高振幅",
    "昨日高换手",
    "小盘股",
    "中盘股",
    "大盘股",
    "高价股",
    "低价股",
    "微利股",
    "破净股",
    "高股息100",
    "筹码集中100",
    "龙头股",
    "行业龙头",
    "政府控股",
    "央企央资",
    "国企改革",
    "并购重组",
    "股权转让",
}

THEME_ALIASES = {
    "机器人": {"机器人概念", "人形机器人", "机器视觉"},
    "人工智能": {"人工智能", "ChatGPT", "DeepSeek概念股", "AI语料"},
    "低空经济": {"低空经济", "飞行汽车(eVTOL)", "通用航空", "无人机"},
    "半导体": {"芯片概念", "半导体产业", "集成电路概念", "先进封装(Chiplet)"},
    "有色金属": {"黄金概念", "白银概念", "小金属概念", "有色金属概念", "铜概念", "钼概念"},
}

_ALIAS_BY_NAME = {
    alias: canonical
    for canonical, aliases in THEME_ALIASES.items()
    for alias in aliases
}

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


def clean_theme_names(names: Iterable[str]) -> List[str]:
    result: List[str] = []
    for raw_name in names:
        name = normalize_theme_name(raw_name)
        if not name or is_noise_theme(name):
            continue
        canonical = _ALIAS_BY_NAME.get(name, name)
        if canonical not in result:
            result.append(canonical)
    return result


def clean_plate_memberships(memberships: Sequence[PlateMembership]) -> List[PlateMembership]:
    result: List[PlateMembership] = []
    seen = set()
    for item in memberships:
        if item.plate_type.upper() != "CONCEPT":
            key = (item.plate_type.upper(), item.code, item.name)
            if key not in seen:
                result.append(item)
                seen.add(key)
            continue

        for theme_name in clean_theme_names([item.name]):
            cleaned = PlateMembership(
                code="THEME:%s" % theme_name,
                name=theme_name,
                plate_type="CONCEPT",
            )
            key = (cleaned.plate_type, cleaned.code, cleaned.name)
            if key not in seen:
                result.append(cleaned)
                seen.add(key)
    return result


def refine_industry_names(memberships: Sequence[PlateMembership], max_details: int = 3) -> str:
    industries: List[str] = []
    details: List[str] = []
    fallback_detail_names: List[str] = []
    for item in memberships:
        name = normalize_theme_name(item.name)
        if not name:
            continue
        plate_type = item.plate_type.upper()
        if plate_type == "INDUSTRY" and name not in industries:
            industries.append(name)
        elif plate_type == "CONCEPT" and name in DETAIL_THEME_NAMES and name not in details:
            details.append(name)
        elif plate_type == "CONCEPT":
            for theme_name in clean_theme_names([name]):
                if theme_name not in fallback_detail_names:
                    fallback_detail_names.append(theme_name)

    if not details:
        details = [name for name in fallback_detail_names if name not in industries]
    if not industries:
        return "、".join(details[:max_details])
    if not details:
        return "、".join(industries)
    detail_text = "/".join(details[:max_details])
    return "、".join("%s-%s" % (industry, detail_text) for industry in industries)


def select_core_theme(memberships: Sequence[PlateMembership], theme_rank_by_plate: Mapping[str, int]) -> str:
    concepts = [item for item in memberships if item.plate_type.upper() == "CONCEPT"]
    if not concepts:
        return "未匹配"
    ranked = [(theme_rank_by_plate.get(item.code, 10_000), item.name) for item in concepts]
    return sorted(ranked, key=lambda item: (item[0], item[1]))[0][1]


def normalize_theme_name(name: str) -> str:
    return str(name or "").strip()


def is_noise_theme(name: str) -> bool:
    normalized = normalize_theme_name(name)
    return normalized in NOISE_THEME_NAMES
