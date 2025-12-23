import sys
import os

# プロジェクトのディレクトリパス
# ⚠️ ユーザー名が "nanamitool" の場合の設定です
path = '/home/nanamitool/nanamitool'
if path not in sys.path:
    sys.path.append(path)

# データベースの絶対パス設定（重要）
os.environ['DATABASE_URL'] = 'sqlite:////home/nanamitool/nanamitool/nanami_learning.db'

# 環境変数の読み込み（必要であれば）
# from dotenv import load_dotenv
# project_folder = os.path.expanduser('~/nanamitool')
# load_dotenv(os.path.join(project_folder, '.env'))

# アプリケーションのインポート
from app import app as application
