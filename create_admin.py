# 本番環境用：初期ユーザー作成スクリプト
# 実行方法: python create_admin.py

import os
from app import app, db
from models import User

def create_admin():
    with app.app_context():
        # テーブルがない場合は作成
        db.create_all()
        
        # nanamiユーザーがいるか確認
        target_user = User.query.filter_by(username='nanami').first()
        if target_user:
            print(f"✅ 既にnanamiユーザーが存在します")
            # パスワードを念の為リセットする場合はコメントアウトを外す
            # target_user.set_password('nanami2005')
            # db.session.commit()
            return

        # 新規作成
        teacher = User(
            username='nanami',
            display_name='石川七夢先生',
            role='teacher'
        )
        teacher.set_password('nanami2005')
        
        db.session.add(teacher)
        db.session.commit()
        print("✅ ユーザー(nanami)を作成しました。パスワードは nanami2005 です。")

if __name__ == '__main__':
    create_admin()
