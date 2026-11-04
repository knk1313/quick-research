#!/usr/bin/env bash
# Claude アプリにアップロードする zip を dist/ に作る。
# zip の一番上に quick-research/ のフォルダーが来るようにする（アプリがその形を求めるため）。
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/quick-research.zip
(cd skills && zip -qr ../dist/quick-research.zip quick-research -x '*/__pycache__/*' '*.DS_Store')
unzip -l dist/quick-research.zip
