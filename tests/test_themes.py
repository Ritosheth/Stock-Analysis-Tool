import unittest

from ghzw.models import PlateMembership
from ghzw.themes import clean_plate_memberships, clean_theme_names, refine_industry_names, select_core_theme


class ThemeCleaningTest(unittest.TestCase):
    def test_clean_theme_names_filters_noise_and_merges_aliases(self):
        names = [
            "融资融券",
            "昨日首板",
            "机器人概念",
            "人形机器人",
            "DeepSeek概念股",
            "芯片概念",
            "沪股通",
        ]

        result = clean_theme_names(names)

        self.assertEqual(result, ["机器人", "人工智能", "半导体"])

    def test_clean_plate_memberships_preserves_industries_and_canonicalizes_concepts(self):
        memberships = [
            PlateMembership(code="HY001", name="软件开发", plate_type="INDUSTRY"),
            PlateMembership(code="GN001", name="融资融券", plate_type="CONCEPT"),
            PlateMembership(code="GN002", name="机器人概念", plate_type="CONCEPT"),
            PlateMembership(code="GN003", name="机器视觉", plate_type="CONCEPT"),
        ]

        result = clean_plate_memberships(memberships)

        self.assertEqual([item.name for item in result], ["软件开发", "机器人"])
        self.assertEqual(result[0].code, "HY001")
        self.assertEqual(result[1].code, "THEME:机器人")

    def test_select_core_theme_prefers_best_ranked_clean_theme(self):
        memberships = [
            PlateMembership(code="THEME:机器人", name="机器人", plate_type="CONCEPT"),
            PlateMembership(code="THEME:人工智能", name="人工智能", plate_type="CONCEPT"),
        ]
        ranks = {"THEME:人工智能": 1, "THEME:机器人": 3}

        result = select_core_theme(memberships, ranks)

        self.assertEqual(result, "人工智能")

    def test_select_core_theme_returns_unmatched_when_no_clean_concept(self):
        result = select_core_theme([PlateMembership(code="HY001", name="银行", plate_type="INDUSTRY")], {})

        self.assertEqual(result, "未匹配")

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

    def test_refine_industry_names_uses_clean_concepts_when_detail_whitelist_misses(self):
        memberships = [
            PlateMembership(code="HY003", name="软件开发", plate_type="INDUSTRY"),
            PlateMembership(code="GN001", name="DeepSeek概念股", plate_type="CONCEPT"),
            PlateMembership(code="GN002", name="沪股通", plate_type="CONCEPT"),
        ]

        result = refine_industry_names(memberships)

        self.assertEqual(result, "软件开发-人工智能")


if __name__ == "__main__":
    unittest.main()
