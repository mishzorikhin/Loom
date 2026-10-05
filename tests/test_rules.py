import unittest

import random

from app.rules import (
    advance_minutes, apply_changes, arrival_gap, choose_arrival, clean_verdict, come_day_for, day_curve, echo_ratio,
    fallback_verdict, format_clock, new_share, popularity, rating_for, return_weight, stay_minutes, style_problem,
    MOODS, active_hints, after_visit_mood, arrival_mood, clean_critic, effective_patience, mood_value, pick_mood,
    shift_mood,
    calendar, clean_district, clean_event, clean_newcomers, clean_review, cut_text, effect_label, part_curve,
)


class RulesTest(unittest.TestCase):
    def test_rating(self):
        self.assertEqual(rating_for("served", 0), 5)
        self.assertEqual(rating_for("served", 1), 4)
        self.assertEqual(rating_for("served", 1, 2), 3)
        self.assertEqual(rating_for("served", 0, 1), 5)
        self.assertEqual(rating_for("refused", 0), 2)
        self.assertIsNone(rating_for("failed", 0))

    def test_stay_minutes(self):
        self.assertEqual(stay_minutes(5, "refused"), 0)
        self.assertEqual(stay_minutes(5, "failed"), 0)
        self.assertEqual(stay_minutes(8, "served"), 0)
        self.assertEqual(stay_minutes(5, "served"), stay_minutes(5, "served"))
        for visit_id in range(1, 200):
            if visit_id % 4:
                self.assertTrue(12 <= stay_minutes(visit_id, "served") <= 40)

    def test_echo_and_style(self):
        said = "Артём, что выберешь: булочку или эспрессо?"
        self.assertGreaterEqual(echo_ratio("Нам булочку или эспрессо? Я как раз сомневался, что лучше.", said), 0.55)
        self.assertLess(echo_ratio("Булочку, пожалуйста.", said), 0.55)
        self.assertEqual(echo_ratio("что угодно", ""), 0.0)
        self.assertTrue(style_problem("client", {"say": "Нам булочку или эспрессо? Что лучше?"}, said))
        self.assertEqual(style_problem("client", {"say": "Булочку, пожалуйста."}, said), "")
        self.assertEqual(style_problem("client", {"say": "Нам булочку или эспрессо?"}, ""), "")
        self.assertTrue(style_problem("staff", {"say": "Берёшь булочку?", "action": "serve"}))
        self.assertEqual(style_problem("staff", {"say": "Что выберешь?", "action": "ask"}), "")
        self.assertEqual(style_problem("staff", {"say": "Держи булочку.", "action": "serve"}), "")
        first = "Привет, я впервые здесь. Подскажи, что у вас попроще взять, чтобы не разориться?"
        self.assertTrue(style_problem("verdict", {"say": first}, first))
        self.assertEqual(style_problem("verdict", {"say": "Быстро и недорого, мне это подошло."}, first), "")

    def test_popularity_grows_with_likes(self):
        self.assertEqual(popularity([]), 1.0)
        self.assertGreater(popularity([5] * 10), popularity([4] * 10))
        self.assertLess(popularity([2] * 10), 1.0)
        self.assertGreater(popularity([4] * 10, referral_pool=3), popularity([4] * 10))
        self.assertLessEqual(popularity([5] * 10, referral_pool=99), 2.2)
        self.assertGreaterEqual(popularity([1] * 10), 0.5)

    def test_arrival_gap_follows_popularity_and_daypart(self):
        quiet = arrival_gap(600, 0.6, 0.5)
        busy = arrival_gap(600, 1.8, 0.5)
        self.assertGreater(quiet, busy)
        self.assertGreater(arrival_gap(11 * 60, 1.0, 0.5), arrival_gap(12 * 60 + 30, 1.0, 0.5))
        self.assertGreaterEqual(arrival_gap(600, 2.2, 0.0), 2.0)
        self.assertGreater(day_curve(12.5 * 60), day_curve(15 * 60))

    def test_arrival_stream_has_no_fixed_count(self):
        counts = []
        for seed in range(30):
            rng = random.Random(seed)
            minute, count = 480.0, 0
            while True:
                minute += arrival_gap(minute, 1.0, rng.random())
                if minute > 1190:
                    break
                count += 1
            counts.append(count)
        self.assertGreater(len(set(counts)), 5)
        self.assertTrue(6 <= sum(counts) / len(counts) <= 17)

    def test_return_weight_comes_from_verdict(self):
        yes = {"id": 1, "intent": "yes", "liked": 5}
        maybe = {"id": 2, "intent": "maybe", "liked": 3}
        never = {"id": 3, "intent": "no", "liked": 1}
        self.assertGreater(return_weight(yes, 10), return_weight(maybe, 10))
        self.assertGreater(return_weight(maybe, 10), return_weight(never, 10))
        self.assertEqual(return_weight({**yes, "come_day": 12}, 10), 0.0)
        self.assertGreater(return_weight({**yes, "come_day": 12}, 12), 0.0)
        self.assertGreater(return_weight({"id": 4}, 3), 0.0)

    def test_choose_arrival(self):
        yes = {"id": 1, "intent": "yes", "liked": 5}
        maybe = {"id": 2, "intent": "maybe", "liked": 2}
        self.assertIsNone(choose_arrival([yes], 5, set(), 1.0, 0.0, 0.0))
        self.assertIsNone(choose_arrival([], 5, set(), 1.0, 0.99, 0.0))
        self.assertEqual(choose_arrival([yes, maybe], 5, set(), 1.0, 0.99, 0.0)["id"], 1)
        self.assertEqual(choose_arrival([yes, maybe], 5, set(), 1.0, 0.99, 0.999)["id"], 2)
        self.assertEqual(choose_arrival([yes, maybe], 5, {1}, 1.0, 0.99, 0.0)["id"], 2)
        self.assertIsNone(choose_arrival([{**yes, "come_day": 9}], 5, set(), 1.0, 0.99, 0.0))
        self.assertGreater(new_share(2.0), new_share(0.6))

    def test_moods_have_sign_and_ladder(self):
        self.assertEqual(mood_value("радость"), 2)
        self.assertEqual(mood_value("раздражение"), -2)
        self.assertEqual(mood_value("что-то"), 0)
        self.assertEqual(shift_mood("спокойствие", 1), "бодрость")
        self.assertEqual(shift_mood("спокойствие", -9), "раздражение")
        self.assertEqual(shift_mood("радость", 3), "радость")
        self.assertEqual(shift_mood("грусть", 1), "спокойствие")
        self.assertEqual(shift_mood("тревога", 0), "тревога")
        self.assertEqual(shift_mood(None, 0), "спокойствие")
        seen = {pick_mood(i / 200) for i in range(200)}
        self.assertEqual(seen, set(MOODS))

    def test_arrival_mood_follows_history_and_wait(self):
        self.assertEqual(arrival_mood(0.5, 0.9, None, None, 0), pick_mood(0.5))
        self.assertEqual(arrival_mood(0.5, 0.1, "радость", None, 0), "радость")
        calm = pick_mood(0.5)
        self.assertLess(mood_value(arrival_mood(0.5, 0.9, None, None, 20)), mood_value(calm) + 1)
        self.assertEqual(arrival_mood(0.5, 0.9, None, None, 40), "раздражение")
        self.assertEqual(arrival_mood(0.5, 0.9, None, 5, 0), shift_mood(calm, 1))
        self.assertEqual(arrival_mood(0.5, 0.9, None, 1, 0), shift_mood(calm, -1))

    def test_staff_mood_after_visit(self):
        self.assertEqual(after_visit_mood("спокойствие", "refused", 2, 600, 0.9), "раздражение")
        self.assertEqual(after_visit_mood("спокойствие", "served", 5, 600, 0.9), "бодрость")
        self.assertEqual(after_visit_mood("спокойствие", "served", 3, 600, 0.0), "спокойствие")
        self.assertEqual(after_visit_mood("спокойствие", "served", 3, 18 * 60, 0.1), "усталость")
        self.assertEqual(after_visit_mood("спокойствие", "served", 3, 18 * 60, 0.9), "спокойствие")

    def test_mood_changes_patience_and_stay(self):
        self.assertEqual(effective_patience(3, "раздражение"), 2)
        self.assertEqual(effective_patience(3, "радость"), 4)
        self.assertEqual(effective_patience(1, "раздражение"), 1)
        self.assertEqual(effective_patience(5, "радость"), 5)
        self.assertEqual(stay_minutes(5, "served", -2), 0)
        self.assertEqual(stay_minutes(5, "served", 2), stay_minutes(5, "served", 0) + 8)
        self.assertLessEqual(stay_minutes(5, "served", 2), 45)

    def test_clean_critic_clamps(self):
        texts = ["Привет, хочу эспрессо", "Эспрессо сейчас будет, 150 рублей", "Спасибо"]
        good = {"code": "price_named", "line": 2, "quote": "150 рублей", "severity": "high", "note": " a  b "}
        out = clean_critic({"score": 9, "issues": [
            good,
            {**good, "code": "?"},
            {**good, "quote": "двести рублей"},
            {**good, "line": 1},
            {**good, "quote": "«150   Рублей»"},
            {**good, "line": 77, "quote": ""},
        ]}, texts)
        self.assertEqual(out["score"], 5)
        self.assertEqual([(row["line"], row["note"]) for row in out["issues"]], [(2, "a b"), (2, "a b"), (0, "a b")])
        self.assertEqual(clean_critic({"score": "x", "issues": None}, ["a", "b"]), {"score": 3, "issues": []})

    def test_hints_need_three_sightings(self):
        def row(code, severity="high"):
            return {"code": code, "severity": severity}

        seen = [[row("price_named")], [row("price_named"), row("echo")], [row("echo")]]
        self.assertEqual(active_hints(seen, "staff"), [])
        seen.append([row("price_named")])
        self.assertEqual(len(active_hints(seen, "staff")), 1)
        self.assertEqual(active_hints(seen, "client"), [])
        seen.append([row("echo")])
        self.assertEqual(len(active_hints(seen, "client")), 1)
        weak = [[row("second_item", "low")]] * 6
        self.assertEqual(active_hints(weak, "staff"), [])

    def test_event_is_clamped_to_the_catalog(self):
        items = {"latte": {"id": "latte", "name": "Латте"}, "bun": {"id": "bun", "name": "Булочка"}}
        crew = ["anya", "mark"]
        event = clean_event({
            "headline": "  Сломалась   кофемашина " + "я" * 100, "story": "Мастер приедет завтра.",
            "effects": [
                {"type": "slower_prep", "target": "", "amount": 9, "days": 7},
                {"type": "item_out", "target": "булочка", "amount": 0, "days": 5},
                {"type": "demand", "target": "", "amount": 0.1, "days": 1},
            ],
        }, items, crew)
        self.assertLessEqual(len(event["headline"]), 60)
        self.assertEqual(len(event["effects"]), 2)
        self.assertEqual(event["effects"][0], {"type": "slower_prep", "target": "", "amount": 2.0, "days": 2})
        self.assertEqual(event["effects"][1]["target"], "bun")
        self.assertEqual(event["effects"][1]["days"], 2)
        rest = clean_event({"headline": "Жара", "story": "", "effects": [
            {"type": "demand", "target": "", "amount": 0.1, "days": 9},
            {"type": "staff_mood", "target": "кто-то", "amount": 7, "days": 1},
            {"type": "item_out", "target": "нет такого", "amount": 0, "days": 1},
            {"type": "магия", "target": "", "amount": 1, "days": 1},
        ]}, items, crew)
        self.assertEqual(rest["effects"][0], {"type": "demand", "target": "", "amount": 0.6, "days": 3})
        self.assertEqual(rest["effects"][1], {"type": "staff_mood", "target": "all", "amount": 2.0, "days": 1})
        self.assertEqual(len(rest["effects"]), 2)
        bad = clean_event({"headline": "Ерунда", "story": "", "effects": [
            {"type": "item_out", "target": "нет такого", "amount": 0, "days": 1},
            {"type": "магия", "target": "", "amount": 1, "days": 1},
        ]}, items, crew)
        self.assertEqual(bad["effects"], [])
        self.assertIsNone(clean_event({"headline": "", "story": "x", "effects": []}, items, crew))
        zero = clean_event({"headline": "Тихо", "story": "", "effects": [{"type": "guest_mood", "target": "", "amount": 0.2, "days": 1}]}, items, crew)
        self.assertEqual(zero["effects"], [])

    def test_district_is_clamped_and_curve_normalised(self):
        out = clean_district({"traffic": 9, "newcomers": -1, "curve": [2, 2, 2, 0, 0, 5, 9], "why": " так  вышло ", "buzz": "x" * 300},
                             previous=1.7)
        self.assertEqual(out["traffic"], 1.8)
        self.assertEqual(out["newcomers"], 0.1)
        self.assertEqual(len(out["curve"]), 6)
        hours = [2, 2, 2, 3, 2, 1]
        self.assertAlmostEqual(sum(w * h for w, h in zip(out["curve"], hours)) / 12, 1.0, delta=0.05)
        self.assertEqual(out["why"], "так вышло")
        self.assertLessEqual(len(out["buzz"]), 140)
        calm = clean_district({"traffic": 0.5}, previous=1.0)
        self.assertEqual(calm["traffic"], 0.65)
        self.assertEqual(clean_district({"traffic": 1.8}, previous=1.0)["traffic"], 1.35)
        self.assertEqual(clean_district({"traffic": 1.8}, previous=1.7)["traffic"], 1.8)
        empty = clean_district({})
        self.assertEqual((empty["traffic"], empty["newcomers"], empty["curve"]), (1.0, 0.3, [1.0] * 6))

    def test_district_curve_shapes_the_stream(self):
        curve = [0.3, 0.3, 2.0, 0.3, 0.3, 0.3]
        self.assertEqual(part_curve(8.5 * 60, curve), 0.3)
        self.assertEqual(part_curve(13 * 60, curve), 2.0)
        self.assertEqual(part_curve(19.5 * 60, curve), 0.3)
        self.assertLess(arrival_gap(13 * 60, 1.0, 0.5, curve), arrival_gap(9 * 60, 1.0, 0.5, curve))
        self.assertEqual(arrival_gap(13 * 60, 1.0, 0.5), arrival_gap(13 * 60, 1.0, 0.5, None))

    def test_newcomers_are_cleaned(self):
        data = {"guests": [
            {"name": "Ася", "trait": "спешит куда-то", "patience": 9, "budget": 300, "story": "Ты шёл мимо."},
            {"name": "Тимур", "trait": "приходит за одним и тем же", "patience": 0, "budget": 100, "story": ""},
            {"name": "тимур", "trait": "спокоен и не торопит", "patience": "x", "budget": "много", "story": "x" * 300},
            {"name": "Ф", "trait": "спокоен и не торопит", "patience": 3, "budget": 250, "story": ""},
            {"name": "Bot<>", "trait": "спокоен и не торопит", "patience": 3, "budget": 250, "story": ""},
            "мусор",
        ]}
        out = clean_newcomers(data, {"Тимур"})
        self.assertEqual([g["name"] for g in out], ["Ася", "Тимур 2", "тимур 3"])
        self.assertEqual(out[0]["patience"], 5)
        self.assertEqual(out[0]["budget"], 320)
        self.assertEqual(out[1]["patience"], 1)
        self.assertEqual(out[1]["budget"], 180)
        self.assertIn(out[0]["trait"], __import__("app.rules", fromlist=["TRAITS"]).TRAITS)
        self.assertEqual(out[2]["patience"], 3)
        self.assertLessEqual(len(out[2]["story"]), 160)
        self.assertEqual(clean_review("  Быстро   и вкусно " + "я" * 200)[:15], "Быстро и вкусно")
        self.assertEqual(len(clean_review("я" * 400)), 140)

    def test_director_events_last_one_day_and_text_is_cut_at_a_word(self):
        items = {"bun": {"id": "bun", "name": "Булочка"}}
        fx = [{"type": "demand", "target": "", "amount": 1.5, "days": 3}, {"type": "item_out", "target": "bun", "amount": 0, "days": 2}]
        event = clean_event({"headline": "Праздник", "story": "", "effects": fx}, items, [], max_days=1)
        self.assertEqual([row["days"] for row in event["effects"]], [1, 1])
        event = clean_event({"headline": "Праздник", "story": "", "effects": fx}, items, [])
        self.assertEqual([row["days"] for row in event["effects"]], [3, 2])
        self.assertEqual(cut_text("Кофейня в эпицентре скандала: страх, ажиотаж и любопытство", 30), "Кофейня в эпицентре скандала…")
        self.assertEqual(cut_text("коротко", 30), "коротко")
        self.assertEqual(clean_district({"buzz": "слово " * 60})["buzz"][-1], "…")

    def test_calendar_and_labels(self):
        self.assertEqual(calendar(1), ("понедельник", "осень"))
        self.assertEqual(calendar(8)[0], "понедельник")
        self.assertEqual(calendar(31)[1], "зима")
        items = {"bun": {"name": "Булочка"}}
        self.assertEqual(effect_label({"type": "item_out", "target": "bun", "amount": 0, "days": 1}, items, {}), "нет: Булочка")
        self.assertEqual(effect_label({"type": "demand", "target": "", "amount": 0.8, "days": 1}, items, {}), "спрос ×0.8")
        self.assertEqual(effect_label({"type": "staff_mood", "target": "anya", "amount": -2.0, "days": 1}, items, {"anya": "Аня"}), "настроение: Аня -2")

    def test_verdict_is_clamped_and_dated(self):
        v = clean_verdict({"say": "  Мило  ", "liked": 9, "return": "навсегда", "return_in_days": -3, "recommend": 1})
        self.assertEqual((v["say"], v["liked"], v["return"], v["return_in_days"], v["recommend"]), ("Мило", 5, "maybe", 0, True))
        self.assertEqual(come_day_for("yes", 0, 7), 8)
        self.assertEqual(come_day_for("maybe", 99, 7), 21)
        self.assertEqual(come_day_for("no", 3, 7), 37)
        self.assertEqual(fallback_verdict("served", 5)["return"], "yes")
        self.assertEqual(fallback_verdict("refused", 2)["liked"], 2)

    def test_price_bounds_and_limit(self):
        items = {
            "latte": {"id": "latte", "name": "Латте", "price": 240, "available": 1},
            "bun": {"id": "bun", "name": "Булочка", "price": 120, "available": 1},
        }
        changes = [
            {"op": "set_price", "item_id": "latte", "price": 260, "available": True},
            {"op": "set_available", "item_id": "bun", "price": 120, "available": False},
            {"op": "set_price", "item_id": "latte", "price": 10, "available": True},
            {"op": "set_price", "item_id": "bun", "price": 130, "available": True},
        ]
        applied, notes = apply_changes(items, changes)
        self.assertEqual(len(applied), 2)
        self.assertEqual(items["latte"]["price"], 260)
        self.assertEqual(items["bun"]["available"], 0)
        self.assertTrue(any("отброшены" in note for note in notes))

    def test_clock_scale(self):
        self.assertEqual(format_clock(8 * 60 + 5), "08:05")
        self.assertEqual(advance_minutes(480, 1000, 1060, 1, True), 540)
        self.assertEqual(advance_minutes(480, 1000, 1060, 1, False), 480)
        self.assertEqual(advance_minutes(480, 1000, 1015, 4, True), 540)
        self.assertEqual(advance_minutes(480, 1000, 1015, 8, True, thinking=True), 495)
        self.assertEqual(advance_minutes(480, 1000, 1030, 1, True, thinking=True), 510)
        self.assertEqual(advance_minutes(480, 1000, 1015, 8, False, thinking=True), 480)

    def _menu(self, count=2):
        items = {
            "latte": {"id": "latte", "name": "Латте", "price": 240, "minutes": 4, "available": 1},
            "bun": {"id": "bun", "name": "Булочка", "price": 120, "minutes": 1, "available": 1},
        }
        for i in range(count - 2):
            items[f"x{i}"] = {"id": f"x{i}", "name": f"Позиция {i}", "price": 100, "minutes": 2, "available": 1}
        return items

    def _add(self, **fields):
        change = {"op": "add_item", "item_id": "", "name": "Раф", "price": 260, "minutes": 5, "available": True}
        change.update(fields)
        return change

    def test_add_item(self):
        items = self._menu()
        applied, notes = apply_changes(items, [self._add(name="  Раф   ванильный ")])
        self.assertEqual(notes, [])
        self.assertEqual(applied[0]["name"], "Раф ванильный")
        self.assertEqual(applied[0]["item_id"], "new1")
        self.assertEqual(items["new1"]["available"], 1)
        self.assertEqual(items["new1"]["minutes"], 5)

    def test_add_item_gets_free_id(self):
        items = self._menu()
        items["new1"] = {"id": "new1", "name": "Чай", "price": 90, "minutes": 2, "available": 1}
        applied, _ = apply_changes(items, [self._add()])
        self.assertEqual(applied[0]["item_id"], "new2")

    def test_add_item_rejects_bad_input(self):
        for bad in (
            self._add(name=""), self._add(name="Р"), self._add(name="Очень длинное название позиции меню"),
            self._add(name="Раф<script>"), self._add(name="латте"), self._add(price=10), self._add(price=5000),
            self._add(minutes=0), self._add(minutes=30), self._add(price="много"),
        ):
            items = self._menu()
            applied, notes = apply_changes(items, [bad])
            self.assertEqual(applied, [], bad)
            self.assertEqual(len(items), 2, bad)
            self.assertTrue(notes, bad)

    def test_add_item_one_per_week_and_menu_cap(self):
        items = self._menu()
        applied, notes = apply_changes(items, [self._add(), self._add(name="Мокко")])
        self.assertEqual(len(applied), 1)
        self.assertTrue(any("одна новая" in note for note in notes))
        full = self._menu(10)
        applied, notes = apply_changes(full, [self._add()])
        self.assertEqual(applied, [])
        self.assertTrue(any("10 позиций" in note for note in notes))

    def test_unknown_item(self):
        applied, notes = apply_changes({}, [{"op": "set_price", "item_id": "nope", "price": 100, "available": True}])
        self.assertEqual(applied, [])
        self.assertTrue(notes)


if __name__ == "__main__":
    unittest.main()
