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
    "PCB": {"PCB概念", "印制电路板", "覆铜板", "电子布", "电子树脂"},
    "MLCC/被动元件": {"MLCC", "被动元件概念"},
    "油气": {"油气开采及服务", "页岩气", "天然气", "可燃冰", "石油行业"},
    "医药": {"创新药", "中药概念", "生物医药", "医疗器械概念", "健康中国"},
    "低空经济": {"低空经济", "飞行汽车(eVTOL)", "通用航空", "无人机"},
    "商业航天": {"商业航天", "卫星互联网", "航天系", "航天装备概念"},
    "军工": {"军工", "军工信息化", "军民融合", "军工央企", "军工集团", "大飞机"},
    "半导体": {"芯片概念", "半导体产业", "集成电路概念", "先进封装(Chiplet)"},
    "有色金属": {"黄金概念", "白银概念", "小金属概念", "有色金属概念", "铜概念", "钼概念"},
}

_ALIAS_BY_NAME = {
    alias: canonical
    for canonical, aliases in THEME_ALIASES.items()
    for alias in aliases
}

DETAIL_THEME_NAMES = {
    "PCB",
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
    "MLCC/被动元件",
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

GENERIC_THEME_NAMES = {
    "华为概念",
    "一带一路",
    "TMT",
}

THEME_KEYWORDS = {
    "人工智能": ("人工智能", "AI", "大模型", "算力", "服务器"),
    "PCB": ("PCB", "覆铜板", "印制电路板", "电子布", "电子树脂", "算力硬件", "服务器", "交换机"),
    "MLCC/被动元件": ("MLCC", "被动元件", "电容", "铝电解电容"),
    "油气": ("油气", "石油", "天然气", "油服", "原油", "WTI", "钻井"),
    "医药": ("创新药", "中药", "医药", "药品", "基药", "医疗器械"),
    "机器人": ("机器人", "人形", "康复辅具", "脑机接口", "优必选", "关节模组", "机械臂"),
    "华为概念": ("华为", "鸿蒙", "海思", "昇腾"),
    "一带一路": ("一带一路", "海外工程", "基建出海", "中欧班列"),
    "半导体": ("半导体", "芯片", "存储器", "封装", "晶圆", "HBM"),
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


def select_core_theme(
    memberships: Sequence[PlateMembership],
    theme_rank_by_plate: Mapping[str, int],
    industry_text: str = "",
    reason_hint: str = "",
) -> str:
    concepts = [item for item in memberships if item.plate_type.upper() == "CONCEPT"]
    if not concepts:
        return "未匹配"
    context = "/".join(
        item
        for item in [industry_text, "、".join(member.name for member in memberships), reason_hint]
        if item
    )
    ranked = [
        (
            -_theme_fit_score(item.name, item.code, theme_rank_by_plate, context, industry_text),
            theme_rank_by_plate.get(item.code, 10_000),
            item.name,
        )
        for item in concepts
    ]
    return sorted(ranked, key=lambda item: (item[0], item[1], item[2]))[0][2]


def normalize_theme_name(name: str) -> str:
    return str(name or "").strip()


def is_noise_theme(name: str) -> bool:
    normalized = normalize_theme_name(name)
    return normalized in NOISE_THEME_NAMES


def _theme_fit_score(
    name: str,
    code: str,
    theme_rank_by_plate: Mapping[str, int],
    context: str,
    industry_text: str,
) -> float:
    rank = theme_rank_by_plate.get(code, 10_000)
    score = max(0.0, 50.0 - min(rank, 50))
    if name in DETAIL_THEME_NAMES:
        score += 8
    score += _business_fit_bonus(name, context)
    score += _keyword_fit_bonus(name, context)
    score -= _generic_theme_penalty(name, context)
    if name == "半导体" and not _has_semiconductor_business_fit(industry_text) and not _has_semiconductor_detail_fit(context):
        score -= 45
    if name == "半导体" and _has_specific_semiconductor_detail(context):
        score -= 16
    if name in {"商业航天", "军工"} and _has_space_defense_business_fit(context):
        score += 35
    if name == "商业航天" and "卫星" in context:
        score += 15
    return score


def _business_fit_bonus(name: str, context: str) -> float:
    if not name or not context:
        return 0.0
    if name in context:
        return 12.0
    return 0.0


def _keyword_fit_bonus(name: str, context: str) -> float:
    if not name or not context:
        return 0.0
    keywords = THEME_KEYWORDS.get(name, ())
    hits = sum(1 for keyword in keywords if keyword in context)
    if hits == 0:
        return 0.0
    return min(24.0, 8.0 + 4.0 * (hits - 1))


def _generic_theme_penalty(name: str, context: str) -> float:
    if name not in GENERIC_THEME_NAMES:
        return 0.0
    keywords = THEME_KEYWORDS.get(name, ())
    if any(keyword in context for keyword in keywords):
        return 0.0
    return 24.0


def _has_semiconductor_business_fit(context: str) -> bool:
    keywords = (
        "半导体",
        "芯片",
        "集成电路",
        "存储器",
        "封装",
        "光刻",
        "硅片",
        "电子特气",
        "引线框架",
        "晶圆",
        "氮化镓",
        "碳基半导体",
        "中芯国际",
    )
    return any(keyword in context for keyword in keywords)


def _has_semiconductor_detail_fit(context: str) -> bool:
    keywords = (
        "芯片",
        "集成电路",
        "存储器",
        "封装",
        "光刻",
        "硅片",
        "电子特气",
        "引线框架",
        "晶圆",
        "氮化镓",
        "碳基半导体",
        "中芯国际",
        "半导体设备",
        "半导体材料",
    )
    return any(keyword in context for keyword in keywords)


def _has_space_defense_business_fit(context: str) -> bool:
    keywords = (
        "军工",
        "航天",
        "卫星",
        "航空装备",
        "军工电子",
        "商业航天",
        "大飞机",
        "毫米波",
        "T/R",
    )
    return any(keyword in context for keyword in keywords)


def _has_specific_semiconductor_detail(context: str) -> bool:
    keywords = (
        "半导体设备概念",
        "半导体材料概念",
        "存储器",
        "MCU芯片",
        "先进封装",
        "高带宽存储器HBM",
    )
    return any(keyword in context for keyword in keywords)
