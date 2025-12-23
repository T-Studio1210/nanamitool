# Render用ビルドスクリプト
# データベースのマイグレーションと漢字データの初期化

#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# データベースマイグレーション
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 漢字データの初期化（必要な場合）
python -c "from app import app; from seed_kanji import seed_kanji_data; app.app_context().push(); seed_kanji_data()" || true
