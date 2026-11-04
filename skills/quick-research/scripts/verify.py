# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""答えの原稿を、gather.py が保存した出典の本文と照合する。

使い方:
  python3 verify.py --answer <作業フォルダー>/answer.md --work <作業フォルダー>

調べること:
1. 確かめられる語（年、数値、『』の書名、英字の固有名詞、「・」でつないだカタカナの人名）が、
   どの出典の本文にあるか。どの出典にもない語は「未確認」として出す
2. 「一言」と「要点」の各行が、いくつの出典に支えられているか（文字の2-gramの重なりによる目安）
3. 出典ごとの信憑性の手がかり（日付、書き手、参考文献、支えた行の数）

未確認の語があれば終了コード 1 を返す。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

# 照合から外す節（出典の一覧や、次の質問の候補は事実の主張ではない）
SKIP_SECTIONS = re.compile(r"^\s*(\*\*)?(出典|次に聞けること)")
SECTION = re.compile(r"^\s*(\*\*[^*]+\*\*|#+\s)")

YEAR = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")
NUMBER = re.compile(r"(?<![\d.])(\d+(?:[.,]\d+)+|\d{2,})(?![\d])")
BOOK = re.compile(r"『([^』]+)』")
LATIN = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9+#.-]*(?:\s+(?:of|the|and|de|von|van|[A-Z][A-Za-z0-9+#.-]*))*)")
KATAKANA_NAME = re.compile(r"([ァ-ヴー]+(?:・[ァ-ヴー]+)+)")
URL = re.compile(r"https?://\S+")
JA_ONLY_KANA = re.compile(r"^[ぁ-ゖー、。・]+$")

# 一般的すぎて照合の意味がない英字
COMMON_LATIN = {"I", "A", "The", "OK", "NG", "AI", "Web", "OS"}


def norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).lower())


def bigrams(text: str) -> set[str]:
    t = norm(re.sub(r"[*`>#\-|]", "", text))
    grams = {t[i : i + 2] for i in range(len(t) - 1)}
    # ひらがなだけの2-gram（「ので」「ます」など）は内容を表さないので外す
    return {g for g in grams if not JA_ONLY_KANA.match(g)}


def claim_lines(answer: str) -> tuple[list[str], list[str]]:
    """照合の対象になる本文の行と、支えを数える行（一言と要点）を返す。"""
    body, support = [], []
    skipping = False
    section = ""
    for line in answer.splitlines():
        if SECTION.match(line):
            skipping = bool(SKIP_SECTIONS.match(line))
            section = line
        if skipping or not line.strip():
            continue
        body.append(line)
        is_point = line.lstrip().startswith(("-", "*", "・")) and "要点" in section
        if "一言" in line or is_point:
            text = re.sub(r"^\s*(\*\*一言\*\*[:：]?|[-*・])\s*", "", line)
            if len(text) >= 8:
                support.append(text)
    return body, support


def checkable_terms(lines: list[str]) -> list[tuple[str, str]]:
    text = URL.sub("", "\n".join(lines))
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(kind: str, term: str) -> None:
        key = norm(term)
        if key and key not in seen:
            seen.add(key)
            found.append((kind, term))

    for m in YEAR.finditer(text):
        add("年", m.group(1))
    for m in NUMBER.finditer(text):
        if not YEAR.fullmatch(m.group(1)):
            add("数値", m.group(1))
    for m in BOOK.finditer(text):
        add("書名", m.group(1))
    for m in LATIN.finditer(text):
        term = m.group(1).strip(" .-")
        if len(term) >= 2 and term not in COMMON_LATIN:
            add("固有名詞", term)
    for m in KATAKANA_NAME.finditer(text):
        add("人名", m.group(1))
    return found


def number_variants(term: str) -> list[str]:
    n = norm(term)
    return list({n, n.replace(",", "")})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answer", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--support", type=float, default=0.45, help="行を支えたとみなす2-gramの重なりの割合")
    args = ap.parse_args()

    work = Path(args.work)
    sources = [s for s in json.loads((work / "sources.json").read_text()) if "error" not in s]
    texts = {}
    for s in sources:
        p = work / "sources" / f"{s['id']}.txt"
        if p.exists():
            texts[s["id"]] = p.read_text()
    normed = {sid: norm(t) for sid, t in texts.items()}
    grams = {sid: bigrams(t) for sid, t in texts.items()}

    answer = Path(args.answer).read_text()
    body, support_lines = claim_lines(answer)

    # 1. 確かめられる語の照合
    unconfirmed = []
    print("## 確かめられる語")
    for kind, term in checkable_terms(body):
        variants = number_variants(term) if kind in ("年", "数値") else [norm(term)]
        hits = [sid for sid, t in normed.items() if any(v in t for v in variants)]
        mark = "OK" if hits else "未確認"
        if not hits:
            unconfirmed.append(term)
        where = ",".join(f"[{h}]" for h in hits) if hits else "-"
        print(f"- {mark}\t{kind}\t{term}\t{where}")

    # 2. 一言・要点の行の支え
    print("\n## 一言・要点の支え（目安）")
    supported_by: dict[int, int] = {sid: 0 for sid in texts}
    for line in support_lines:
        g = bigrams(line)
        if not g:
            continue
        backers = [sid for sid in texts if len(g & grams[sid]) / len(g) >= args.support]
        for sid in backers:
            supported_by[sid] += 1
        mark = "○" if len(backers) >= 2 else "△" if backers else "×"
        short = line if len(line) <= 40 else line[:40] + "…"
        print(f"- {mark}\t{','.join(f'[{b}]' for b in backers) or '-'}\t{short}")

    # 3. 出典ごとの手がかり
    print("\n## 出典の手がかり")
    print("| 番号 | サイト | 日付 | 書き手 | 参考文献 | 支えた行 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for s in sources:
        d = s.get("published")
        age = ""
        if d:
            try:
                age = f"（{(date.today() - date.fromisoformat(d[:10])).days}日前）"
            except ValueError:
                pass
        print(
            f"| [{s['id']}] | {s.get('site') or s['domain']} | {d or '不明'}{age} | "
            f"{s.get('author') or '不明'} | {'あり' if s.get('has_references') else 'なし'} | "
            f"{supported_by.get(s['id'], 0)} |"
        )

    if unconfirmed:
        print(f"\n未確認の語が {len(unconfirmed)} 件ある: " + "、".join(unconfirmed))
        return 1
    print("\n未確認の語はない")
    return 0


if __name__ == "__main__":
    sys.exit(main())
