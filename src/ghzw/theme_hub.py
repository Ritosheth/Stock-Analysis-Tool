"""Read the locally maintained A-share theme library without changing it."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List


DEFAULT_DATABASE_PATH = Path.home() / "Documents" / "A股主题研究中枢" / "data" / "theme_hub.sqlite3"


def load_formal_themes(codes: Iterable[str], database_path: str | Path | None = None) -> Dict[str, List[str]]:
    """Return formal library themes for each stock, ordered by confidence."""

    normalized_codes = sorted({str(code).strip().upper() for code in codes if str(code).strip()})
    path = Path(database_path or os.environ.get("GHZW_THEME_HUB_DB", DEFAULT_DATABASE_PATH))
    if not normalized_codes or not path.is_file():
        return {}
    placeholders = ",".join("?" for _ in normalized_codes)
    query = f"""
        SELECT m.code, t.name
        FROM theme_member AS m JOIN theme AS t ON t.theme_id = m.theme_id
        WHERE m.code IN ({placeholders})
          AND m.publication_status IN ('published_high', 'published_limited')
        ORDER BY m.code, m.evidence_confidence DESC, m.effective_weight DESC, t.level DESC, t.name
    """
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            rows = connection.execute(query, normalized_codes).fetchall()
    except sqlite3.Error:
        return {}
    themes_by_code: Dict[str, List[str]] = {}
    for code, name in rows:
        if name and name not in themes_by_code.setdefault(code, []):
            themes_by_code[code].append(name)
    return themes_by_code
