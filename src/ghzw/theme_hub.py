"""Read the locally maintained A-share theme library without changing it."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_DATABASE_PATH = Path.home() / "Documents" / "A股主题研究中枢" / "data" / "theme_hub.sqlite3"
FORMAL_THEME_SOURCE = "A股主题库"
FUTU_FALLBACK_THEME_SOURCE = "Futu分类（A股主题库无相应分类）"


@dataclass(frozen=True)
class FormalThemeClassification:
    """The four classification fields supplied by the local theme hub."""

    industries: List[str]
    concepts: List[str]

    @property
    def raw_theme(self) -> str:
        return self.concepts[0] if self.concepts else "未匹配"

    @property
    def core_theme(self) -> str:
        return self.raw_theme


def load_formal_theme_classifications(
    codes: Iterable[str], database_path: str | Path | None = None
) -> Dict[str, FormalThemeClassification]:
    """Return local A-share theme classifications, including parent industries."""

    normalized_codes = sorted({str(code).strip().upper() for code in codes if str(code).strip()})
    path = Path(database_path or os.environ.get("GHZW_THEME_HUB_DB", DEFAULT_DATABASE_PATH))
    if not normalized_codes or not path.is_file():
        return {}
    placeholders = ",".join("?" for _ in normalized_codes)
    query = f"""
        SELECT m.code, t.name, parent.name
        FROM theme_member AS m
        JOIN theme AS t ON t.theme_id = m.theme_id
        LEFT JOIN theme AS parent ON parent.theme_id = t.parent_id
        WHERE m.code IN ({placeholders})
          AND m.publication_status IN ('published_high', 'published_limited')
        ORDER BY m.code, m.evidence_confidence DESC, m.effective_weight DESC,
                 t.level DESC, t.name
    """
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            rows = connection.execute(query, normalized_codes).fetchall()
    except sqlite3.Error:
        return {}

    industries_by_code: Dict[str, List[str]] = {}
    concepts_by_code: Dict[str, List[str]] = {}
    for code, concept_name, industry_name in rows:
        if concept_name:
            concepts = concepts_by_code.setdefault(code, [])
            if concept_name not in concepts:
                concepts.append(concept_name)
        if industry_name:
            industries = industries_by_code.setdefault(code, [])
            if industry_name not in industries:
                industries.append(industry_name)

    result: Dict[str, FormalThemeClassification] = {}
    for code in set(industries_by_code) | set(concepts_by_code):
        result[code] = FormalThemeClassification(
            industries=industries_by_code.get(code, []),
            concepts=concepts_by_code.get(code, []),
        )
    return result


def load_formal_themes(codes: Iterable[str], database_path: str | Path | None = None) -> Dict[str, List[str]]:
    """Return only the local theme names for backward-compatible callers."""

    return {
        code: classification.concepts
        for code, classification in load_formal_theme_classifications(codes, database_path).items()
    }
