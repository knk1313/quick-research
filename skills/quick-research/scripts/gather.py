# /// script
# requires-python = ">=3.10"
# dependencies = ["trafilatura>=2.0", "htmldate>=1.9", "rank-bm25>=0.2"]
# ///
"""ページを取ってきて本文を抜き出し、質問に関係する段落だけを返す。

使い方:
  uv run gather.py --query "検索語1" --query "検索語2" --out <作業フォルダー> URL [URL ...]

- 本文の全文は <作業フォルダー>/sources/<番号>.txt に保存する（verify.py が照合に使う）
- 出典の情報と抜粋は <作業フォルダー>/sources.json に保存する
- 標準出力には、Claude が読む分だけ（出典ごとの情報と、関連の高い段落）を出す
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import trafilatura
from htmldate import find_date
from rank_bm25 import BM25Okapi

REF_MARKERS = re.compile(r"(参考文献|参考資料|出典|脚注|References|Bibliography|Further reading|Citations?)", re.I)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).lower()


def tokens(text: str) -> list[str]:
    """日本語は文字の2-gram、英数字は単語で区切る（形態素解析なしで軽く動かすため）。"""
    text = normalize(text)
    out: list[str] = []
    for word in re.findall(r"[a-z0-9][a-z0-9+#._-]*", text):
        out.append(word)
    ja = re.sub(r"[a-z0-9+#._-]+|\s+|[^\w]", " ", text)
    for chunk in ja.split():
        if len(chunk) == 1:
            out.append(chunk)
        out.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return out


def split_passages(text: str, size: int = 400) -> list[str]:
    """段落をまとめて、およそ size 文字の塊にする。"""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if buf and len(buf) + len(p) > size:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def fetch(url: str) -> dict:
    html = trafilatura.fetch_url(url)
    if not html:
        return {"url": url, "error": "取得できなかった"}
    raw = trafilatura.extract(
        html,
        url=url,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not raw:
        return {"url": url, "error": "本文を抜き出せなかった"}
    meta = json.loads(raw)
    # Wikipedia などの「[編集]」の行は本文ではないので外す
    text = re.sub(r"(?m)^\s*\[(編集|edit|ソースを編集)\]\s*$\n?", "", meta.get("text") or "")
    author = meta.get("author")
    # 典拠データなどを書き手と取り違えることがあるので、長すぎるものは捨てる
    if author and (len(author) > 60 or author.count(" ") > 5):
        author = None
    published = meta.get("date") or find_date(html, original_date=True)
    modified = find_date(html, original_date=False)
    return {
        "url": url,
        "domain": urlparse(url).netloc,
        "title": meta.get("title"),
        "site": meta.get("sitename") or meta.get("hostname"),
        "author": author,
        "published": published,
        "modified": modified if modified != published else None,
        "has_references": bool(REF_MARKERS.search(text)),
        "chars": len(text),
        "text": text,
    }


def age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--query", action="append", required=True, help="検索語（複数可）")
    ap.add_argument("--out", required=True, help="作業フォルダー")
    ap.add_argument("--top", type=int, default=4, help="出典ごとに返す段落の数")
    ap.add_argument("--max-chars", type=int, default=1800, help="出典ごとに標準出力へ出す文字数の上限")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "sources").mkdir(parents=True, exist_ok=True)
    query = tokens(" ".join(args.query))

    existing = []
    sj = out / "sources.json"
    if sj.exists():
        existing = json.loads(sj.read_text())
    next_id = max((s["id"] for s in existing), default=0) + 1

    results = []
    for url in args.urls:
        src = fetch(url)
        src["id"] = next_id
        next_id += 1
        if "error" not in src:
            (out / "sources" / f"{src['id']}.txt").write_text(src["text"])
            passages = split_passages(src["text"])
            if passages:
                bm25 = BM25Okapi([tokens(p) for p in passages])
                scores = bm25.get_scores(query)
                ranked = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)[: args.top]
                # 本文での順番に並べ直す（読みやすさのため）
                src["passages"] = [passages[i] for i in sorted(ranked)]
            else:
                src["passages"] = []
        src.pop("text", None)
        results.append(src)

    sj.write_text(json.dumps(existing + results, ensure_ascii=False, indent=2))

    for s in results:
        print(f"## [{s['id']}] {s.get('title') or s['url']}")
        print(f"url: {s['url']}")
        if "error" in s:
            print(f"error: {s['error']}\n")
            continue
        age = age_days(s.get("published"))
        print(
            f"site: {s.get('site')} / author: {s.get('author') or '不明'} / "
            f"published: {s.get('published') or '不明'}"
            + (f"（{age}日前）" if age is not None else "")
            + (f" / modified: {s['modified']}" if s.get("modified") else "")
            + f" / 参考文献: {'あり' if s['has_references'] else 'なし'} / 本文: {s['chars']}字"
        )
        budget = args.max_chars
        for p in s["passages"]:
            if budget <= 0:
                break
            print("> " + p[:budget].replace("\n", "\n> "))
            budget -= len(p)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
