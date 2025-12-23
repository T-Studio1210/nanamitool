# Firebase通知モジュール

import firebase_admin
from firebase_admin import credentials, messaging
import os

# Firebase Admin SDKの初期化
cred_path = os.path.join(os.path.dirname(__file__), 'firebase-service-account.json')
if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    FIREBASE_INITIALIZED = True
else:
    FIREBASE_INITIALIZED = False
    print("⚠️ Firebase設定ファイルが見つかりません")


def strip_html_tags(html_content):
    """HTMLタグを除去してプレーンテキストを取得"""
    from bs4 import BeautifulSoup
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text(separator=' ', strip=True)


def send_push_notification(token, title, body, data=None):
    """単一のデバイスにプッシュ通知を送信"""
    if not FIREBASE_INITIALIZED or not token:
        return False
    
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        print(f"通知送信成功: {response}")
        return True
    except Exception as e:
        print(f"通知送信エラー: {e}")
        return False


def send_push_to_users(users, title, body, data=None):
    """複数のユーザーにプッシュ通知を送信（重複トークンは除外）"""
    if not FIREBASE_INITIALIZED:
        return 0
    
    # 重複トークンを除外
    sent_tokens = set()
    success_count = 0
    
    for user in users:
        if user.fcm_token and user.fcm_token not in sent_tokens:
            if send_push_notification(user.fcm_token, title, body, data):
                success_count += 1
                sent_tokens.add(user.fcm_token)
    
    return success_count


def send_announcement_notification(announcement, recipients):
    """連絡事項の通知を送信"""
    title = f"📢 {announcement.title}"
    # HTMLタグを除去してプレーンテキストにする
    plain_content = strip_html_tags(announcement.content)
    body = plain_content[:100] + ("..." if len(plain_content) > 100 else "")
    data = {
        "type": "announcement",
        "url": "/dashboard"
    }
    
    return send_push_to_users(recipients, title, body, data)


def send_problem_notification(problem, recipients):
    """新問題配信の通知を送信"""
    title = "📝 新しい問題が届きました"
    body = problem.title
    data = {
        "type": "problem",
        "url": f"/problem/{problem.id}"
    }
    
    return send_push_to_users(recipients, title, body, data)


def send_answer_notification(answer, teacher):
    """回答提出の通知を先生に送信"""
    if not teacher or not teacher.fcm_token:
        return False
    
    student_name = answer.student.display_name if answer.student else "生徒"
    problem_title = answer.problem.title if answer.problem else "問題"
    
    title = f"✏️ {student_name}さんが回答しました"
    body = problem_title
    data = {
        "type": "answer",
        "url": f"/answer/{answer.id}"
    }
    
    return send_push_notification(teacher.fcm_token, title, body, data)


def send_reaction_notification(student, announcement, teacher):
    """リアクションの通知を先生に送信"""
    if not teacher or not teacher.fcm_token:
        return False
    
    student_name = student.display_name if student else "生徒"
    
    title = f"💬 {student_name}さんがリアクションしました"
    body = announcement.title if announcement else "連絡事項"
    data = {
        "type": "reaction",
        "url": "/manage_announcements"
    }
    
    return send_push_notification(teacher.fcm_token, title, body, data)


def send_feedback_notification(feedback, student):
    """フィードバックの通知を生徒に送信"""
    if not student or not student.fcm_token:
        return False
    
    problem_title = feedback.answer.problem.title if feedback.answer and feedback.answer.problem else "問題"
    
    title = "📬 先生からフィードバックが届きました"
    body = problem_title
    data = {
        "type": "feedback",
        "url": f"/problem/{feedback.answer.problem_id}"
    }
    
    return send_push_notification(student.fcm_token, title, body, data)


def send_view_notification(student, problem, teacher):
    """生徒が問題を閲覧したときの通知を先生に送信"""
    if not teacher or not teacher.fcm_token:
        return False
    
    student_name = student.display_name if student else "生徒"
    
    title = f"👀 {student_name}さんが問題を開きました"
    body = problem.title if problem else "問題"
    data = {
        "type": "view",
        "url": f"/problem/{problem.id}"
    }
    
    return send_push_notification(teacher.fcm_token, title, body, data)
