"""読んだ出典の本文を、verify.py が照合に使う形で作業フォルダーに保存する。

gather.py が使えない環境（Claude アプリのように、実行環境から一般のサイトに通信できない環境）で使う。
Web 検索や Web fetch で読んだ本文のうち、答えの根拠にする段落を、原文のまま標準入力で渡す。
標準ライブラリーだけで動く。

使い方:
  python3 save_source.py --work <作業フォルダー> --url <URL> --title "<タイトル>" \
    [--site "<発行者>"] [--published 2026-01-01] [--author "<書き手>"] < 本文.txt

保存した出典の番号を標準出力に出す。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

REF_MARKERS = re.compile(r"(参考文献|参考資料|出典|脚注|References|Bibliography|Further reading|Citations?)", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--title")
    ap.add_argument("--site")
    ap.add_argument("--published", help="公開日か最終更新日（YYYY-MM-DD）")
    ap.add_argument("--author")
    ap.add_argument("--has-references", action="store_true", help="ページに参考文献の節がある")
    args = ap.parse_args()

    text = sys.stdin.read().strip()
    if not text:
        print("本文が空なので保存しなかった", file=sys.stderr)
        return 1

    work = Path(args.work)
    (work / "sources").mkdir(parents=True, exist_ok=True)
    sj = work / "sources.json"
    sources = json.loads(sj.read_text()) if sj.exists() else []
    sid = max((s["id"] for s in sources), default=0) + 1

    (work / "sources" / f"{sid}.txt").write_text(text + "\n")
    sources.append(
        {
            "id": sid,
            "url": args.url,
            "domain": urlparse(args.url).netloc,
            "title": args.title,
            "site": args.site or urlparse(args.url).netloc,
            "author": args.author,
            "published": args.published,
            "has_references": args.has_references or bool(REF_MARKERS.search(text)),
            "chars": len(text),
            "excerpt_only": True,
        }
    )
    sj.write_text(json.dumps(sources, ensure_ascii=False, indent=2))
    print(sid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
