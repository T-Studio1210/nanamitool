# 石川七夢講師専用学習アプリ - 設定

import os

class Config:
    """アプリケーション設定"""
    
    # アプリ名
    APP_NAME = "石川七夢講師専用学習アプリ"
    
    # セキュリティ
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'nanami-learning-app-secret-key-2024'
    
    # データベース設定（ローカル開発用SQLite / 本番PostgreSQL）
    # RenderのPostgreSQL URLは'postgres://'で始まるが、SQLAlchemyは'postgresql://'が必要
    _database_url = os.environ.get('DATABASE_URL', '')
    if _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _database_url or 'sqlite:///nanami_learning.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # セッション設定
    PERMANENT_SESSION_LIFETIME = 86400  # 24時間
