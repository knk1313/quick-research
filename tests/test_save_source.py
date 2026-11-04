"""save_source.py で保存した出典を、verify.py が照合できることを確かめる（保存モードの流れ）。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/quick-research/scripts"


def save(work: Path, url: str, text: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "save_source.py"), "--work", str(work), "--url", url, "--title", "架空", *extra],
        input=text,
        capture_output=True,
        text=True,
    )


class SaveSourceTest(unittest.TestCase):
    def test_ids_increase_and_metadata_is_written(self):
        work = Path(tempfile.mkdtemp())
        self.assertEqual(save(work, "https://example.com/a", "一つ目の段落", "--published", "2026-01-01").stdout.strip(), "1")
        self.assertEqual(save(work, "https://example.com/b", "二つ目\n参考文献").stdout.strip(), "2")
        sources = json.loads((work / "sources.json").read_text())
        self.assertEqual([s["id"] for s in sources], [1, 2])
        self.assertEqual(sources[0]["published"], "2026-01-01")
        self.assertFalse(sources[0]["has_references"])
        self.assertTrue(sources[1]["has_references"])
        self.assertEqual((work / "sources" / "2.txt").read_text(), "二つ目\n参考文献\n")

    def test_empty_text_is_rejected(self):
        work = Path(tempfile.mkdtemp())
        self.assertEqual(save(work, "https://example.com", "  \n").returncode, 1)
        self.assertFalse((work / "sources.json").exists())

    def test_verify_reads_saved_sources(self):
        work = Path(tempfile.mkdtemp())
        save(work, "https://example.com", "ミナトは2019年に公開され、42個のモジュールを持つ。")
        (work / "answer.md").write_text("**一言**：ミナトは2019年に公開され、42個のモジュールを持つ言語である。\n")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "verify.py"), "--answer", str(work / "answer.md"), "--work", str(work)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("OK\t年\t2019\t[1]", r.stdout)


if __name__ == "__main__":
    unittest.main()
