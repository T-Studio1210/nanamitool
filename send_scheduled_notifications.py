# 予約通知送信スクリプト
# PythonAnywhereのスケジュールタスクで定期実行するか、cronで実行してください

from datetime import datetime
import os
import sys

# プロジェクトのパスを追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, ScheduledNotification, Announcement, Problem, Feedback, User


def send_scheduled_notifications():
    """予約された通知を送信"""
    with app.app_context():
        now = datetime.utcnow()
        
        # 未送信かつ送信予定時刻を過ぎた通知を取得
        pending = ScheduledNotification.query.filter(
            ScheduledNotification.is_sent == False,
            ScheduledNotification.scheduled_at <= now
        ).all()
        
        print(f"[{now}] 送信待ち通知: {len(pending)}件")
        
        for scheduled in pending:
            try:
                if scheduled.notification_type == 'announcement':
                    send_announcement_notification(scheduled)
                elif scheduled.notification_type == 'problem':
                    send_problem_notification(scheduled)
                elif scheduled.notification_type == 'feedback':
                    send_feedback_notification(scheduled)
                
                # 送信済みに更新
                scheduled.is_sent = True
                scheduled.sent_at = datetime.utcnow()
                db.session.commit()
                print(f"  ✓ 通知送信完了: {scheduled.notification_type} ID={scheduled.target_id}")
            
            except Exception as e:
                print(f"  ✗ 通知送信エラー: {e}")
                import traceback
                traceback.print_exc()


def send_announcement_notification(scheduled):
    """予約された連絡事項の通知を送信"""
    from firebase_notifications import send_announcement_notification as send_push
    
    announcement = Announcement.query.get(scheduled.target_id)
    if not announcement:
        print(f"    連絡事項が見つかりません: ID={scheduled.target_id}")
        return
    
    if announcement.is_global:
        recipients = User.query.filter_by(role='student').all()
    else:
        recipients = list(announcement.recipients)
    
    sent_count = send_push(announcement, recipients)
    print(f"    連絡事項「{announcement.title}」を{sent_count}人に送信")


def send_problem_notification(scheduled):
    """予約された問題の通知を送信"""
    from firebase_notifications import send_problem_notification as send_push
    
    problem = Problem.query.get(scheduled.target_id)
    if not problem:
        print(f"    問題が見つかりません: ID={scheduled.target_id}")
        return
    
    recipients = list(problem.assigned_students)
    sent_count = send_push(problem, recipients)
    print(f"    問題「{problem.title}」を{sent_count}人に送信")


def send_feedback_notification(scheduled):
    """予約されたフィードバックの通知を送信"""
    from firebase_notifications import send_feedback_notification as send_push
    
    feedback = Feedback.query.get(scheduled.target_id)
    if not feedback:
        print(f"    フィードバックが見つかりません: ID={scheduled.target_id}")
        return
    
    student = feedback.answer.student if feedback.answer else None
    send_push(feedback, student)
    print(f"    フィードバックを{student.display_name if student else '不明'}に送信")


if __name__ == '__main__':
    send_scheduled_notifications()
