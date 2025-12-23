from app import app
from models import User

with app.app_context():
    users = User.query.all()
    print("=== FCMトークン確認 ===")
    for u in users:
        token = u.fcm_token[:40] + "..." if u.fcm_token else "なし"
        print(f"{u.role}: {u.display_name} -> {token}")
