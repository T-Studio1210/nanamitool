# Render用ビルドスクリプト
# データベースのマイグレーションと漢字データの初期化

#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# データベースの初期設定、漢字データの投入、管理者ユーザーの作成を順次実行
python -c "from app import app, db; app.app_context().push(); db.create_all()"
python -c "from app import app; from seed_kanji import seed_kanji; app.app_context().push(); seed_kanji()" || true
python create_admin.py || true
