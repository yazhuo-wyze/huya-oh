import unittest

from huya_automation.lucky_event import (
    ACTIVITY_FRAME_PATH,
    AD_COMPLETE_SELECTOR,
    AD_FRAME_PATH,
    AD_FRAME_SELECTOR,
    AD_MODAL_CLOSE_SELECTOR,
    AD_START_SETTLE_SECONDS,
    AD_UNAVAILABLE_TEXT,
    BASE_COIN_BUTTON_SELECTOR,
    BONUS_COIN_BUTTON_SELECTOR,
    COIN_CONFIRM_BUTTON_SELECTOR,
    COIN_REWARD_VALUE_SELECTOR,
    FREE_DRAW_CARD_SELECTOR,
    LUCKY_VALUE_SELECTOR,
    PARTICIPATE_BUTTON_SELECTOR,
    is_active_round_text,
    is_ad_unavailable_text,
    is_free_participate_button,
    is_safe_free_draw_card,
    LuckyEventConfig,
    next_poll_delay,
    parse_base_coin_amount,
    parse_bonus_coin_amount,
    parse_countdown_seconds,
    parse_lucky_value,
)


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

    def test_parses_countdown_seconds(self) -> None:
        self.assertEqual(parse_countdown_seconds("01:00"), 60)
        self.assertEqual(parse_countdown_seconds("00:59"), 59)

    def test_rejects_invalid_countdown(self) -> None:
        self.assertIsNone(parse_countdown_seconds("已结束"))
        self.assertIsNone(parse_countdown_seconds("00:60"))

    def test_activity_poll_delay_is_between_five_and_ten_seconds(self) -> None:
        delay = next_poll_delay(LuckyEventConfig())
        self.assertGreaterEqual(delay, 5.0)
        self.assertLessEqual(delay, 10.0)


class LuckyEventSelectorTest(unittest.TestCase):
    def test_real_activity_selectors_are_stable(self) -> None:
        self.assertEqual(
            ACTIVITY_FRAME_PATH,
            "/hyfe/super_lucky_time/index.html",
        )
        self.assertEqual(LUCKY_VALUE_SELECTOR, ".luck-value")
        self.assertEqual(FREE_DRAW_CARD_SELECTOR, ".list-item")
        self.assertEqual(PARTICIPATE_BUTTON_SELECTOR, ".btn")
        self.assertEqual(AD_COMPLETE_SELECTOR, "#ext-ab-time")
        self.assertEqual(AD_FRAME_PATH, "/hyfe/task-ext/index.html")
        self.assertEqual(
            AD_FRAME_SELECTOR,
            "iframe[src*='/hyfe/task-ext/index.html']",
        )
        self.assertEqual(AD_MODAL_CLOSE_SELECTOR, "#close-modalh5")
        self.assertEqual(AD_START_SETTLE_SECONDS, 1.0)
        self.assertEqual(BASE_COIN_BUTTON_SELECTOR, "button.return-gold")
        self.assertEqual(BONUS_COIN_BUTTON_SELECTOR, "button.not-enough")
        self.assertEqual(
            COIN_CONFIRM_BUTTON_SELECTOR,
            ".reward-container button.btn",
        )
        self.assertEqual(
            COIN_REWARD_VALUE_SELECTOR,
            ".reward-container .value",
        )


class LuckyEventSafetyTest(unittest.TestCase):
    def test_accepts_real_free_draw_card(self) -> None:
        self.assertTrue(is_safe_free_draw_card("+10\n免费抽", "免费抽"))

    def test_rejects_coin_card(self) -> None:
        self.assertFalse(
            is_safe_free_draw_card("+10 免费抽 500金币", "免费抽")
        )

    def test_only_accepts_exact_free_participation_button(self) -> None:
        self.assertTrue(is_free_participate_button("看视频免费参与 "))
        self.assertFalse(is_free_participate_button("立即参与 (500金币)"))

    def test_recognizes_exact_ad_unavailable_message(self) -> None:
        self.assertEqual(AD_UNAVAILABLE_TEXT, "没有获取到广告信息")
        self.assertTrue(is_ad_unavailable_text(" 没有获取到广告信息 "))
        self.assertFalse(is_ad_unavailable_text("恭喜完成任务"))

    def test_only_accepts_base_coin_claim_button(self) -> None:
        self.assertEqual(parse_base_coin_amount("只领800金币"), 800)
        self.assertIsNone(parse_base_coin_amount("不够！再领288金币"))

    def test_only_accepts_bonus_coin_button(self) -> None:
        self.assertEqual(parse_bonus_coin_amount("不够！再领288金币"), 288)
        self.assertIsNone(parse_bonus_coin_amount("只领800金币"))


if __name__ == "__main__":
    unittest.main()
