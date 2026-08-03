import sqlite3
import tempfile
import unittest
from pathlib import Path

from ghzw.theme_hub import load_formal_theme_classifications, load_formal_themes


class ThemeHubTest(unittest.TestCase):
    def test_load_formal_classifications_includes_parent_industry_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "theme_hub.sqlite3"
            with sqlite3.connect(database_path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE theme (
                        theme_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        parent_id TEXT,
                        level INTEGER NOT NULL,
                        publication_status TEXT NOT NULL DEFAULT 'published_high'
                    );
                    CREATE TABLE theme_member (
                        theme_id TEXT NOT NULL,
                        code TEXT NOT NULL,
                        evidence_confidence REAL NOT NULL DEFAULT 0,
                        effective_weight REAL NOT NULL DEFAULT 0,
                        publication_status TEXT NOT NULL DEFAULT 'published_high'
                    );
                    INSERT INTO theme VALUES
                        ('industry', '主题库行业', NULL, 2, 'watch'),
                        ('theme-a', '主题库核心', 'industry', 3, 'published_high'),
                        ('theme-b', '主题库次级', 'industry', 3, 'published_high');
                    INSERT INTO theme_member VALUES
                        ('theme-b', 'SH.600103', 0.7, 0.8, 'published_high'),
                        ('theme-a', 'SH.600103', 0.9, 0.9, 'published_high');
                    """
                )

            result = load_formal_theme_classifications(["SH.600103"], database_path)

            self.assertEqual(result["SH.600103"].industries, ["主题库行业"])
            self.assertEqual(result["SH.600103"].concepts, ["主题库核心", "主题库次级"])
            self.assertEqual(result["SH.600103"].raw_theme, "主题库核心")
            self.assertEqual(load_formal_themes(["SH.600103"], database_path), {
                "SH.600103": ["主题库核心", "主题库次级"]
            })

    def test_load_formal_classifications_returns_empty_for_missing_database(self):
        result = load_formal_theme_classifications(["SH.600103"], "/tmp/not-a-theme-hub.sqlite3")

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
