# 本番環境用：初期ユーザー作成スクリプト
# 実行方法: python create_admin.py

import os
from app import app, db
from models import User

def create_admin():
    with app.app_context():
        # テーブルがない場合は作成
        db.create_all()
        
        # 先生ユーザーがいるか確認
        admin = User.query.filter_by(role='teacher').first()
        if admin:
            print(f"既に先生ユーザーが存在します: {admin.username}")
            return

        # 新規作成
        teacher = User(
            username='nanami',  # ユーザー名
            display_name='石川七夢先生',
            role='teacher'
        )
        teacher.set_password('nanami2005')  # パスワード
        
        db.session.add(teacher)
        db.session.commit()
        print("✅ 先生ユーザー(admin)を作成しました。パスワードは admin1234 です。")

if __name__ == '__main__':
    create_admin()
