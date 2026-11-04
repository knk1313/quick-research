"""verify.py を、架空の出典と答えで確かめる（ネットワークを使わない）。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/quick-research/scripts/verify.py"

SOURCE = """架空言語ミナトは、2019年に港北大学の研究室が公開したプログラミング言語である。
標準ライブラリーには42個のモジュールがあり、設計者はアオイ・サトウである。
"""

ANSWER = """**一言**：ミナトは、2019年に港北大学の研究室が公開したプログラミング言語である。

**要点**
- 標準ライブラリーには42個のモジュールがある
- 設計者はアオイ・サトウである
- 2021年に版2が出た

**出典**
1. ○ 架空の出典 — 例（2026-01-01）https://example.com/1999
"""


def run(answer: str, source: str) -> subprocess.CompletedProcess:
    work = Path(tempfile.mkdtemp())
    (work / "sources").mkdir()
    (work / "sources" / "1.txt").write_text(source)
    (work / "sources.json").write_text(
        json.dumps([{"id": 1, "url": "https://example.com", "domain": "example.com", "site": "example.com", "published": "2026-01-01", "has_references": False}])
    )
    (work / "answer.md").write_text(answer)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--answer", str(work / "answer.md"), "--work", str(work)],
        capture_output=True,
        text=True,
    )


class VerifyTest(unittest.TestCase):
    def test_unconfirmed_year_fails(self):
        r = run(ANSWER, SOURCE)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("未確認\t年\t2021", r.stdout)
        self.assertIn("OK\t年\t2019\t[1]", r.stdout)
        self.assertIn("OK\t数値\t42\t[1]", r.stdout)
        self.assertIn("OK\t人名\tアオイ・サトウ\t[1]", r.stdout)

    def test_sources_section_is_skipped(self):
        # 出典の節の URL や日付は照合しない
        r = run(ANSWER, SOURCE)
        self.assertNotIn("1999", r.stdout)

    def test_all_confirmed_passes(self):
        answer = ANSWER.replace("- 2021年に版2が出た\n", "")
        r = run(answer, SOURCE)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
