#!/usr/bin/env python3
"""Offline tests for shape_layer.py (no API calls).

Run:
    python tests/test_shape_layer.py
"""

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import shape_layer as S

CARD = """# Borrowing an organization's capability

## 問題形狀
Someone without scale tries to get what only organizations had.

## 核心張力
Wants the capability, cannot afford the structure.

## 證據
Should not reach the judge.

## 最像但不同的線（判別欄）
Plain tool adoption is not this.

## 化身清單

| Year | Note | Object | Means |
|---|---|---|---|
| 2011 | [[a/one]] | students | groups |
| 2013 | [[two|Two]] | farmers | crowd |
"""


def make_index(d, units, raw):
    S.jsave(d / "units.json", units)
    ids = sorted(units)
    np.savez_compressed(d / "vectors.npz", ids=np.array(ids), raw=np.array([raw[u] for u in ids], dtype=np.float32))
    (d / "cache").mkdir(exist_ok=True)
    return S.Index(d)


class TestUnits(unittest.TestCase):
    def test_note_and_chunks(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "a").mkdir()
            (root / "a/plain.md").write_text("---\ntitle: x\n---\nhello ![img](x.png) https://e.com", encoding="utf-8")
            (root / "a/split.md").write_text(
                '%% chunk-start id="w:one" %%\nfirst\n%% chunk-end %%\n%% chunk-start id="w:two" %%\nsecond\n%% chunk-end %%',
                encoding="utf-8")
            (root / "private").mkdir()
            (root / "private/secret.md").write_text("pii", encoding="utf-8")
            (root / "a/footer.md").write_text("body\n<!-- auto v2 -->\nrelated links", encoding="utf-8")
            u = S.read_units(root, exclude=["private/*"], cut_at=["<!-- auto"])
            self.assertEqual(u["a/footer"], "# footer\n\nbody")
            self.assertEqual(S.body_chars(u["a/plain"]), 5)
            self.assertEqual(u["a/plain"], "# plain\n\nhello  (link)")
            self.assertEqual(u["a/split#w:one"], "# split\n\nfirst")
            self.assertEqual(u["a/split#w:two"], "# split\n\nsecond")
            self.assertNotIn("private/secret", u)


class TestCard(unittest.TestCase):
    def test_sections_and_rows(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "borrow.md"
            p.write_text(CARD, encoding="utf-8")
            c = S.parse_card(p)
            self.assertEqual(c["id"], "borrow")
            self.assertIn("問題形狀", c["text"])
            self.assertIn("最像但不同的線", c["text"])
            self.assertNotIn("Should not reach", c["text"])
            self.assertEqual([l for l, _ in c["rows"]], ["a/one", "two"])
            self.assertIn("| 2013 | Two |", c["rows"][1][1])


class TestProbe(unittest.TestCase):
    def test_rocchio_moves_away_from_rejected(self):
        units = {u: {"text": u} for u in ("p1", "p2", "n1", "x")}
        raw = {"p1": [1.0, 0.0], "p2": [0.8, 0.6], "n1": [0.6, 0.8], "x": [0.0, 1.0]}
        with tempfile.TemporaryDirectory() as t:
            ix = make_index(Path(t), units, raw)
            v = S.probe(ix, ["p1", "p2"], [])
            self.assertTrue(np.allclose(v, [0.9, 0.3]))
            v = S.probe(ix, ["p1", "p2"], ["n1"])
            self.assertTrue(np.allclose(v, [0.6, -0.1]))

    def test_auc(self):
        self.assertEqual(S.auc([2, 2], [0, 0]), 1.0)
        self.assertEqual(S.auc([1], [1]), 0.5)


class TestReview(unittest.TestCase):
    def test_marks_go_into_card(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "cards").mkdir()
            (d / "cards/borrow.md").write_text(CARD, encoding="utf-8")
            (d / "review.md").write_text(
                "# Shape links\n\n## Borrowing\n<!-- card: borrow -->\n\n"
                "- [x] accept [[c/three]] — 對不上：—\n"
                "- [-] borderline [[c/four]] — 對不上：x\n"
                "- [ ] accept [[c/five]]\n"
                "- [x] probe 0.512 [[two]]\n", encoding="utf-8")
            S.cmd_review(argparse.Namespace(index=str(d), cards=str(d / "cards")))
            c = S.parse_card(d / "cards/borrow.md")
            self.assertEqual([l for l, _ in c["rows"]], ["a/one", "two", "c/three"])   # "two" not duplicated
            self.assertEqual(c["rejected"], ["c/four"])
            self.assertIn("|  | [[c/three]] |  |  |", (d / "cards/borrow.md").read_text(encoding="utf-8"))
            # applying again changes nothing
            S.cmd_review(argparse.Namespace(index=str(d), cards=str(d / "cards")))
            self.assertEqual(S.parse_card(d / "cards/borrow.md")["rejected"], ["c/four"])


class TestJudgeLeaveOut(unittest.TestCase):
    def test_batch_never_sees_own_row(self):
        units = {u: {"text": f"text of {u}"} for u in ("a/one", "two", "three")}
        e = [1.0, 0.0]
        prompts = []

        def fake_chat(prompt):
            prompts.append(prompt)
            n = prompt.count("--- ")
            return "\n".join(json.dumps({"i": i, "對不上": [], "判定": "收"}) for i in range(1, n + 1))

        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            ix = make_index(d, units, {u: e for u in units})
            (d / "card.md").write_text(CARD, encoding="utf-8")
            card = S.parse_card(d / "card.md")
            with patch.object(S, "chat", fake_chat), patch.object(S, "BATCH", 1):
                res = S.judge(ix, card, ["a/one", "three"], "t")
        self.assertEqual(set(res), {"a/one", "three"})
        p_one = next(p for p in prompts if "text of a/one" in p)
        p_three = next(p for p in prompts if "text of three" in p)
        self.assertNotIn("| 2011 | one |", p_one)
        self.assertIn("| 2013 | Two |", p_one)
        self.assertIn("| 2011 | one |", p_three)


if __name__ == "__main__":
    unittest.main()
