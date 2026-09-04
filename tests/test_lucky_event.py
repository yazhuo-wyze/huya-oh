import unittest

from huya_automation.lucky_event import is_active_round_text, parse_lucky_value


class LuckyValueTest(unittest.TestCase):
    def test_parses_lucky_value(self) -> None:
        self.assertEqual(parse_lucky_value("累计幸运值 🍀 10"), 10)

    def test_parses_target_lucky_value(self) -> None:
        self.assertEqual(parse_lucky_value("累计幸运值 200"), 200)

    def test_returns_none_when_value_is_absent(self) -> None:
        self.assertIsNone(parse_lucky_value("本轮活动已结束"))


class LuckyRoundStateTest(unittest.TestCase):
    def test_countdown_means_round_is_active(self) -> None:
        self.assertTrue(is_active_round_text("08:55"))

    def test_ended_label_is_not_active(self) -> None:
        self.assertFalse(is_active_round_text("已结束"))

    def test_activity_name_alone_is_not_active(self) -> None:
        self.assertFalse(is_active_round_text("欧皇时刻"))


if __name__ == "__main__":
    unittest.main()
