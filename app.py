# 石川七夢講師専用学習アプリ - メインアプリケーション

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from config import Config
from models import db, User, Problem, Answer, Feedback, Announcement, AnnouncementReaction, ProblemComponent, JapaneseQuiz, JapaneseAnswer, JapaneseAssignment, JapaneseFlashcard, JapaneseWriting, GradeKanji, JapaneseFlashcardAssignment, JapaneseWritingAssignment
from functools import wraps
import hashlib
import json
import os
import random
from bs4 import BeautifulSoup
from groq import Groq

# Groq API設定
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
groq_client = Groq(api_key=GROQ_API_KEY)

# アプリケーション初期化
app = Flask(__name__)
app.config.from_object(Config)

# データベース初期化
# データベース初期化
db.init_app(app)
migrate = Migrate(app, db)

# フィルター定義
@app.template_filter('from_json_safe')
def from_json_safe_filter(s):
    try:
        import json
        return json.loads(s)
    except:
        return None


@app.template_filter('jst')
def to_jst_filter(utc_dt, fmt='%Y/%m/%d %H:%M'):
    """UTCをJST（日本標準時、UTC+9）に変換してフォーマット"""
    if utc_dt is None:
        return ''
    from datetime import timedelta
    jst_dt = utc_dt + timedelta(hours=9)
    return jst_dt.strftime(fmt)


@app.template_filter('format_mixed_answer')
def format_mixed_answer_filter(content, problem_type='text'):
    """mixed問題の回答をJSON形式から人が読める形式に変換"""
    if problem_type != 'mixed':
        # mixed以外はそのまま返す（HTMLタグを除去）
        from bs4 import BeautifulSoup
        return BeautifulSoup(content, 'html.parser').get_text()[:100]
    
    try:
        import json
        answers = json.loads(content)
        parts = []
        for key, answer in answers.items():
            if answer.get('type') == 'text':
                val = answer.get('value', '')
                if val:
                    parts.append(val[:50])
            elif answer.get('type') == 'choice':
                parts.append(f"選択: {answer.get('choice_text', '')}")
            elif answer.get('type') == 'checkbox':
                texts = answer.get('choice_text', [])
                if texts:
                    parts.append(f"選択: {', '.join(texts[:3])}")
        return ' / '.join(parts)[:100] if parts else '(回答あり)'
    except:
        # JSONパースに失敗した場合はそのまま（truncate）
        return content[:100] if len(content) > 100 else content

# ログイン管理
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'ログインが必要です。'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# 先生専用デコレーター
def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_teacher():
            flash('この機能は先生専用です。', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ============ ルート ============

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/firebase-messaging-sw.js')
def firebase_sw():
    """Firebase Service Workerをルートから提供"""
    from flask import send_from_directory
    return send_from_directory('static', 'firebase-messaging-sw.js', mimetype='application/javascript')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'ようこそ、{user.display_name}さん！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('ユーザー名またはパスワードが正しくありません。', 'error')
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('ログアウトしました。', 'success')
    return redirect(url_for('login'))


@app.route('/api/check-new')
@login_required
def check_new():
    """新着をチェックするAPI"""
    import json
    from datetime import datetime, timedelta
    from flask import session
    
    # 最後のチェック時刻を取得（なければ1時間前）
    last_check = session.get('last_notification_check')
    if last_check:
        last_check = datetime.fromisoformat(last_check)
    else:
        last_check = datetime.utcnow() - timedelta(hours=1)
    
    # 現在時刻を保存
    session['last_notification_check'] = datetime.utcnow().isoformat()
    
    result = {
        'new_problems': 0,
        'new_announcements': 0,
        'new_feedback': 0
    }
    
    if current_user.is_teacher():
        # 先生: 新しい回答をチェック
        result['new_feedback'] = Answer.query.filter(
            Answer.submitted_at > last_check
        ).count()
    else:
        # 生徒: 新しい問題と連絡事項をチェック
        from sqlalchemy import or_
        
        # 新しい問題
        new_problems = current_user.assigned_problems.filter(
            Problem.created_at > last_check
        ).count()
        result['new_problems'] = new_problems
        
        # 新しい連絡事項
        new_announcements = Announcement.query.filter(
            Announcement.is_active == True,
            Announcement.created_at > last_check
        ).filter(
            or_(
                Announcement.is_global == True,
                Announcement.recipients.any(id=current_user.id)
            )
        ).count()
        result['new_announcements'] = new_announcements
        
        # 新しいフィードバック
        new_feedback = db.session.query(Feedback).join(Answer).filter(
            Answer.student_id == current_user.id,
            Feedback.created_at > last_check
        ).count()
        result['new_feedback'] = new_feedback
    
    return json.dumps(result), 200, {'Content-Type': 'application/json'}


@app.route('/api/save-fcm-token', methods=['POST'])
@login_required
def save_fcm_token():
    """FCMトークンを保存"""
    import json
    data = request.get_json()
    token = data.get('token')
    
    if token:
        current_user.fcm_token = token
        db.session.commit()
        return json.dumps({'success': True}), 200, {'Content-Type': 'application/json'}
    
    return json.dumps({'success': False}), 400, {'Content-Type': 'application/json'}


@app.route('/api/announcement/<int:announcement_id>/react', methods=['POST'])
@login_required
def react_to_announcement(announcement_id):
    """連絡事項にリアクション"""
    import json
    data = request.get_json()
    reaction_type = data.get('reaction')
    
    if not reaction_type:
        return json.dumps({'success': False, 'error': 'リアクションを選択してください'}), 400, {'Content-Type': 'application/json'}
    
    announcement = Announcement.query.get_or_404(announcement_id)
    
    # 既存のリアクションを確認
    existing = AnnouncementReaction.query.filter_by(
        announcement_id=announcement_id,
        student_id=current_user.id,
        reaction_type=reaction_type
    ).first()
    
    if existing:
        # 同じリアクションがあれば削除（トグル）
        db.session.delete(existing)
        db.session.commit()
        return json.dumps({'success': True, 'action': 'removed'}), 200, {'Content-Type': 'application/json'}
    else:
        # 新しいリアクションを追加
        reaction = AnnouncementReaction(
            announcement_id=announcement_id,
            student_id=current_user.id,
            reaction_type=reaction_type
        )
        db.session.add(reaction)
        db.session.commit()
        
        # 先生にプッシュ通知を送信
        try:
            from firebase_notifications import send_reaction_notification
            teacher = User.query.filter_by(role='teacher').first()
            send_reaction_notification(current_user, announcement, teacher)
        except Exception as e:
            print(f"通知送信エラー: {e}")
        
        return json.dumps({'success': True, 'action': 'added'}), 200, {'Content-Type': 'application/json'}


@app.route('/api/announcement/<int:announcement_id>/reactions', methods=['GET'])
@login_required
def get_announcement_reactions(announcement_id):
    """連絡事項のリアクション詳細を取得"""
    if not current_user.is_teacher():
        return json.dumps({'error': 'Unauthorized'}), 403, {'Content-Type': 'application/json'}
        
    import json
    reactions = AnnouncementReaction.query.filter_by(announcement_id=announcement_id).order_by(AnnouncementReaction.created_at.desc()).all()
    
    result = []
    for r in reactions:
        user = User.query.get(r.student_id)
        result.append({
            'user_name': user.display_name if user else 'Unknown',
            'type': r.reaction_type,
            'created_at': r.created_at.strftime('%m/%d %H:%M')
        })
    
    return json.dumps(result, ensure_ascii=False), 200, {'Content-Type': 'application/json'}


@app.route('/api/problem/<int:problem_id>/viewed', methods=['POST'])
@login_required
def notify_problem_viewed(problem_id):
    """生徒が問題を表示したとき先生に通知"""
    if current_user.is_teacher():
        return json.dumps({'success': False, 'error': 'Teacher cannot notify'}), 400, {'Content-Type': 'application/json'}
    
    problem = Problem.query.get_or_404(problem_id)
    
    try:
        from firebase_notifications import send_view_notification
        teacher = problem.author
        send_view_notification(current_user, problem, teacher)
    except Exception as e:
        print(f"閲覧通知送信エラー: {e}")
    
    return json.dumps({'success': True}), 200, {'Content-Type': 'application/json'}

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_teacher():
        # 先生用：すべての連絡事項と問題を表示
        announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).limit(5).all()
        # 最新の問題5件のみ表示
        problems = Problem.query.order_by(Problem.created_at.desc()).limit(5).all()
        
        # ディスク使用量取得
        import shutil
        total, used, free = shutil.disk_usage("/")
        
        stats = {
            'problems': Problem.query.count(),
            'students': User.query.filter_by(role='student').count(),
            'pending_answers': Answer.query.filter(Answer.feedback == None).count(),
            'disk_used_percent': int((used / total) * 100),
            'disk_free_gb': round(free / (1024**3), 2)
        }
        from datetime import datetime
        return render_template('dashboard.html', problems=problems, stats=stats, announcements=announcements, now=datetime.utcnow())
    else:
        # 生徒用：自分に配信された連絡事項と問題のみ表示
        from sqlalchemy import or_
        announcements = Announcement.query.filter(
            Announcement.is_active == True
        ).filter(
            or_(
                Announcement.is_global == True,
                Announcement.recipients.any(id=current_user.id)
            )
        ).order_by(Announcement.created_at.desc()).limit(5).all()
        
        # 通常の問題を取得
        problems = Problem.query.order_by(Problem.created_at.desc()).all()
        
        # 日本語課題の取得と統合
        japanese_tasks = []
        
        # クイズ（全てグループ化）
        quiz_assignments_all = current_user.japanese_assignments.order_by(
            JapaneseAssignment.assigned_at.desc(),
            JapaneseAssignment.id
        ).all()
        
        from itertools import groupby
        # 分単位でグルーピングするためのキー関数
        def get_quiz_group_key(q):
            return q.assigned_at.strftime('%Y-%m-%d %H:%M')
        
        for key, group in groupby(quiz_assignments_all, key=get_quiz_group_key):
            items = list(group)
            if not items:
                continue
                
            # グループ内の最新の日時を使用
            group_date = items[0].assigned_at
            count = len(items)
            
            # ソート順を古い順（解く順番）にするためにIDでソートし直す
            items.sort(key=lambda x: x.id)
            first_item = items[0]
            
            # グループ内の完了状況を計算
            completed_count = sum(1 for item in items if item.completed)
            all_completed = (completed_count == count)
            
            # フィードバックがあるかチェック
            has_feedback = any(item.teacher_feedback for item in items)
            has_unseen_feedback = any(item.teacher_feedback and not item.feedback_seen for item in items)
            
            # 未完了のものがあれば最初の未完了を、なければ最初の完了を表示
            next_item = next((item for item in items if not item.completed), first_item)
            
            japanese_tasks.append({
                'type': 'quiz_group',
                'title': f"熟語クイズ ({completed_count}/{count}問完了)" if all_completed else f"熟語クイズ ({count}問)",
                'id': next_item.quiz.id,
                'assignment_id': next_item.id,
                'created_at': group_date,
                'completed': all_completed,
                'feedback': has_feedback,
                'unseen_feedback': has_unseen_feedback,
                'count': count,
                'items': items
            })
            
        # フラッシュカード（全てグループ化）
        flashcard_assignments = current_user.japanese_flashcard_assignments.order_by(
            JapaneseFlashcardAssignment.assigned_at.desc(), 
            JapaneseFlashcardAssignment.id
        ).all()
        
        def get_flashcard_group_key(fa):
            return fa.assigned_at.strftime('%Y-%m-%d %H:%M')
        
        for key, group in groupby(flashcard_assignments, key=get_flashcard_group_key):
            items = list(group)
            if not items:
                continue
            group_date = items[0].assigned_at
            count = len(items)
            items.sort(key=lambda x: x.id)
            first_item = items[0]
            
            # グループ内の完了状況を計算
            completed_count = sum(1 for item in items if item.completed)
            all_completed = (completed_count == count)
            
            # フィードバックがあるかチェック
            has_feedback = any(item.teacher_feedback for item in items)
            has_unseen_feedback = any(item.teacher_feedback and not item.feedback_seen for item in items)
            
            # 未完了のものがあれば最初の未完了を、なければ最初の完了を表示
            next_item = next((item for item in items if not item.completed), first_item)
            
            japanese_tasks.append({
                'type': 'flashcard_group',
                'title': f"フラッシュカード ({completed_count}/{count}枚完了)" if all_completed else f"フラッシュカード ({count}枚)",
                'id': next_item.flashcard.id,
                'assignment_id': next_item.id,
                'created_at': group_date,
                'completed': all_completed,
                'feedback': has_feedback,
                'unseen_feedback': has_unseen_feedback,
                'count': count,
                'items': items
            })
            
        # 書き取り（全てグループ化）
        writing_assignments = current_user.japanese_writing_assignments.order_by(
            JapaneseWritingAssignment.assigned_at.desc(),
            JapaneseWritingAssignment.id
        ).all()
        
        def get_writing_group_key(wa):
            return wa.assigned_at.strftime('%Y-%m-%d %H:%M')
        
        for key, group in groupby(writing_assignments, key=get_writing_group_key):
            items = list(group)
            if not items:
                continue
            group_date = items[0].assigned_at
            count = len(items)
            items.sort(key=lambda x: x.id)
            first_item = items[0]
            
            # グループ内の完了状況を計算
            completed_count = sum(1 for item in items if item.completed)
            all_completed = (completed_count == count)
            
            # フィードバックがあるかチェック
            has_feedback = any(item.teacher_feedback for item in items)
            has_unseen_feedback = any(item.teacher_feedback and not item.feedback_seen for item in items)
            
            # 未完了のものがあれば最初の未完了を、なければ最初の完了を表示
            next_item = next((item for item in items if not item.completed), first_item)
            
            japanese_tasks.append({
                'type': 'writing_group',
                'title': f"書き取り練習 ({completed_count}/{count}問完了)" if all_completed else f"書き取り練習 ({count}問)",
                'id': next_item.writing.id,
                'assignment_id': next_item.id,
                'created_at': group_date,
                'completed': all_completed,
                'feedback': has_feedback,
                'unseen_feedback': has_unseen_feedback,
                'count': count,
                'items': items
            })
            
        # 日付順にソート（新しい順）
        japanese_tasks.sort(key=lambda x: x['created_at'], reverse=True)
        
        # 生徒の学習統計を計算
        total_assigned = len(problems) + len(japanese_tasks)
        
        # answerテーブル経由の回答数
        answered_problem_count = current_user.answers.count()
        # 日本語課題の完了数
        completed_japanese_count = len([t for t in japanese_tasks if t['completed']])
        
        answered_count = answered_problem_count + completed_japanese_count
        
        # フィードバック数
        feedback_problem_count = sum(1 for a in current_user.answers if a.feedback)
        feedback_japanese_count = len([t for t in japanese_tasks if t['feedback']])
        feedback_count = feedback_problem_count + feedback_japanese_count
        
        completion_rate = int((answered_count / total_assigned * 100)) if total_assigned > 0 else 0
        
        student_stats = {
            'total_assigned': total_assigned,
            'answered': answered_count,
            'feedback_received': feedback_count,
            'pending_feedback': answered_count - feedback_count,
            'unanswered': total_assigned - answered_count,
            'completion_rate': completion_rate
        }
        
        from datetime import datetime
        return render_template('dashboard.html', problems=problems, japanese_tasks=japanese_tasks, announcements=announcements, student_stats=student_stats, now=datetime.utcnow())


def save_components_from_html(html_content):
    """HTMLコンテンツからコンポーネントを抽出して保存"""
    if not html_content:
        return

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # テキストブロックとウィジェットブロックを抽出
        # block-text または question-widget を探す
        # 保存されるHTML構造に依存する
        
        # テキストブロック
        text_blocks = soup.find_all(class_='block-text')
        for block in text_blocks:
            content = str(block.decode_contents()).strip() # innerHTML
            if not content: continue
            
            # ハッシュ計算 (type + content)
            raw_data = f"text:{content}"
            content_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
            
            # 重複チェック
            if not ProblemComponent.query.filter_by(content_hash=content_hash).first():
                comp = ProblemComponent(
                    content=content,
                    component_type='text',
                    content_hash=content_hash,
                    description=None,
                    choices_json=None
                )
                db.session.add(comp)

        # ウィジェット
        widgets = soup.find_all(class_='question-widget')
        for widget in widgets:
            w_type = widget.get('data-widget-type', 'unknown')
            w_choices = widget.get('data-choices', '[]')
            
            # 説明文抽出
            description = ''
            desc_div = widget.find(class_='widget-description')
            if desc_div:
                description = desc_div.get_text("\n", strip=True) # 改行を維持してテキスト化
            
            # ハッシュ計算 (type + choices + description)
            # コンテンツ自体はHTML全体として保存するが、同一性の判定はメタデータで行う
            raw_data = f"widget:{w_type}:{w_choices}:{description}"
            content_hash = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
            
            if not ProblemComponent.query.filter_by(content_hash=content_hash).first():
                # ウィジェット全体をHTMLとして保存（再利用時にそのまま埋め込めるように）
                # ただし、外側のdivは再生成されることが多いので、widgetの中身だけあるいはwidgetタグそのものを利用
                comp = ProblemComponent(
                    content=str(widget), # widgetタグそのもの
                    component_type=f"widget-{w_type}",
                    content_hash=content_hash,
                    description=description,
                    choices_json=w_choices
                )
                db.session.add(comp)
        
        db.session.commit()
            
    except Exception as e:
        print(f"Error saving components: {e}")



# ============ 問題管理 ============

@app.route('/teacher/problems')
@login_required
@teacher_required
def manage_problems():
    problems = Problem.query.order_by(Problem.created_at.desc()).all()
    return render_template('manage_problems.html', problems=problems)

@app.route('/problem/create', methods=['GET', 'POST'])
@login_required
@teacher_required
def create_problem():
    students = User.query.filter_by(role='student').order_by(User.display_name).all()
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        deadline_str = request.form.get('deadline')
        selected_students = request.form.getlist('students')
        problem_type = request.form.get('problem_type', 'text')
        
        if not title:
            flash('タイトルを入力してください。', 'error')
            return redirect(url_for('create_problem'))
        
        # 記述式の場合はcontentが必須（複合もここに含まれるが、JSでcontentにHTMLが入るのでOK）
        if not content:
            flash('問題内容を入力してください。', 'error')
            return redirect(url_for('create_problem'))
        
        if not selected_students:
            flash('配信先の生徒を選択してください。', 'error')
            return redirect(url_for('create_problem'))
        
        # 期限の処理
        deadline = None
        if deadline_str:
            from datetime import datetime
            try:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass
        
        # 選択肢の処理 (古いchoiceタイプのための互換性コード、基本はmixedになるので使われない可能性が高いが残す)
        choices_json = None
        correct_choice = None
        if problem_type == 'choice':
            import json
            choices = request.form.getlist('choices[]')
            choices = [c for c in choices if c.strip()]
            if choices:
                choices_json = json.dumps(choices, ensure_ascii=False)
                correct_choice = int(request.form.get('correct_choice', 0))
        
        problem = Problem(
            title=title,
            content=content,
            problem_type=problem_type,
            choices_json=choices_json,
            correct_choice=correct_choice,
            teacher_id=current_user.id,
            deadline=deadline
        )
        
        # 選択された生徒を問題に割り当て
        for student_id in selected_students:
            student = User.query.get(int(student_id))
            if student:
                problem.assigned_students.append(student)
        
        
        db.session.add(problem)
        db.session.commit()
        
        # コンポーネント保存
        save_components_from_html(content)
        
        # 配信タイミング処理
        schedule_type = request.form.get('schedule_type', 'immediate')
        scheduled_at_str = request.form.get('scheduled_at')
        
        if schedule_type == 'scheduled' and scheduled_at_str:
            # 予約配信
            from datetime import datetime, timedelta
            from models import ScheduledNotification
            try:
                scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
                # JSTからUTCへ変換 (JST = UTC+9)
                scheduled_at_utc = scheduled_at - timedelta(hours=9)
                
                scheduled_notification = ScheduledNotification(
                    notification_type='problem',
                    target_id=problem.id,
                    scheduled_at=scheduled_at_utc
                )
                db.session.add(scheduled_notification)
                db.session.commit()
                
                flash(f'問題を{len(selected_students)}人の生徒に予約配信（{scheduled_at_str}）しました。', 'success')
            except ValueError as e:
                print(f"予約時刻パースエラー: {e}")
                flash(f'問題を{len(selected_students)}人の生徒に配信しました。（予約設定エラー）', 'warning')
        else:
            # 即時配信：配信対象の生徒にプッシュ通知を送信
            try:
                from firebase_notifications import send_problem_notification
                send_problem_notification(problem, problem.assigned_students)
            except Exception as e:
                print(f"通知送信エラー: {e}")
            
            flash(f'問題を{len(selected_students)}人の生徒に配信しました。', 'success')
        return redirect(url_for('dashboard'))
    
    past_problems = Problem.query.order_by(Problem.created_at.desc()).limit(20).all()
    return render_template('create_problem.html', students=students, past_problems=past_problems)


@app.route('/problem/<int:problem_id>')
@login_required
def view_problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    
    if current_user.is_teacher():
        answers = problem.answers.order_by(Answer.submitted_at.desc()).all()
        # 回答済みの生徒IDリスト
        answered_student_ids = [a.student_id for a in answers]
        # 配信先の生徒のうち未回答の生徒
        unanswered_students = [s for s in problem.assigned_students if s.id not in answered_student_ids]
        return render_template('view_problem.html', problem=problem, answers=answers, unanswered_students=unanswered_students)
    else:
        existing_answer = Answer.query.filter_by(
            problem_id=problem_id,
            student_id=current_user.id
        ).first()
        return render_template('view_problem.html', problem=problem, existing_answer=existing_answer)


@app.route('/problem/<int:problem_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    db.session.delete(problem)
    db.session.commit()
    flash('問題を削除しました。', 'success')
    
    redirect_to = request.form.get('redirect_to')
    if redirect_to == 'manage_problems':
        return redirect(url_for('manage_problems'))
        
    return redirect(url_for('dashboard'))


@app.route('/problems/bulk_delete', methods=['POST'])
@login_required
@teacher_required
def bulk_delete_problems():
    problem_ids = request.form.getlist('problem_ids')
    if not problem_ids:
        flash('削除する問題が選択されていません。', 'warning')
        return redirect(url_for('manage_problems'))
    
    count = 0
    for pid in problem_ids:
        problem = Problem.query.get(int(pid))
        if problem:
            db.session.delete(problem)
            count += 1
    
    db.session.commit()
    flash(f'{count}件の問題を削除しました。', 'success')
    return redirect(url_for('manage_problems'))


@app.route('/problem/<int:problem_id>/edit', methods=['GET', 'POST'])
@login_required
@teacher_required
def edit_problem(problem_id):
    problem = Problem.query.get_or_404(problem_id)
    
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if not title or not content:
            flash('タイトルと内容を入力してください。', 'error')
            return redirect(url_for('edit_problem', problem_id=problem_id))
        
        problem.title = title
        problem.content = content
        db.session.commit()
        
        # コンポーネント保存
        save_components_from_html(content)
        
        flash('問題を更新しました。', 'success')
        return redirect(url_for('view_problem', problem_id=problem_id))
    
    return render_template('edit_problem.html', problem=problem)


# ============ 回答管理 ============

@app.route('/problem/<int:problem_id>/answer', methods=['POST'])
@login_required
def submit_answer(problem_id):
    if current_user.is_teacher():
        flash('先生は回答を提出できません。', 'error')
        return redirect(url_for('view_problem', problem_id=problem_id))
    
    problem = Problem.query.get_or_404(problem_id)
    
    # 選択問題の場合
    if problem.problem_type == 'choice':
        selected_choice = request.form.get('selected_choice')
        if selected_choice is None:
            flash('選択肢を選んでください。', 'error')
            return redirect(url_for('view_problem', problem_id=problem_id))
        
        choices = problem.get_choices()
        choice_idx = int(selected_choice)
        content = f"選択: {choices[choice_idx]}"
        
        # 正解かどうか判定
        is_correct = (choice_idx == problem.correct_choice)
        
    elif problem.problem_type == 'mixed':
        mixed_json = request.form.get('mixed_answers_json')
        if not mixed_json:
            flash('回答データが送信されませんでした。', 'error')
            return redirect(url_for('view_problem', problem_id=problem_id))
            
        # JSONのまま保存する（編集・表示時にそれぞれ加工する）
        content = mixed_json
        
        is_correct = None # 複合問題は自動採点しない（先生が確認）
        
    else:
        content = request.form.get('content')
        if not content:
            flash('回答を入力してください。', 'error')
            return redirect(url_for('view_problem', problem_id=problem_id))
        is_correct = None
    
    # 既存の回答があるかチェック
    existing = Answer.query.filter_by(problem_id=problem_id, student_id=current_user.id).first()
    if existing:
        flash('すでに回答を提出しています。', 'error')
        return redirect(url_for('view_problem', problem_id=problem_id))
    
    answer = Answer(
        problem_id=problem_id,
        student_id=current_user.id,
        content=content
    )
    db.session.add(answer)
    db.session.commit()
    
    # 先生にプッシュ通知を送信
    try:
        from firebase_notifications import send_answer_notification
        teacher = problem.author
        print(f"📤 回答通知送信: 先生={teacher.display_name if teacher else 'None'}, FCMトークン={'あり' if teacher and teacher.fcm_token else 'なし'}")
        result = send_answer_notification(answer, teacher)
        print(f"📤 通知送信結果: {result}")
    except Exception as e:
        import traceback
        print(f"通知送信エラー: {e}")
        traceback.print_exc()
    
    # 選択問題は自動採点表示
    if problem.problem_type == 'choice':
        if is_correct:
            flash('🎉 正解です！回答を提出しました。', 'success')
        else:
            flash('😢 不正解です。回答を提出しました。', 'warning')
    else:
        flash('回答を提出しました。先生の確認をお待ちください。', 'success')
        
    return redirect(url_for('view_problem', problem_id=problem_id))



@app.route('/answer/<int:answer_id>')
@login_required
@teacher_required
def view_answer(answer_id):
    answer = Answer.query.get_or_404(answer_id)
    return render_template('view_answer.html', answer=answer)


@app.route('/answer/<int:answer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_answer(answer_id):
    answer = Answer.query.get_or_404(answer_id)
    
    # 自分の回答のみ編集可能、かつフィードバックがまだない場合のみ
    if answer.student_id != current_user.id:
        flash('他の人の回答は編集できません。', 'error')
        return redirect(url_for('dashboard'))
    
    if answer.feedback:
        flash('フィードバック済みの回答は編集できません。', 'error')
        return redirect(url_for('view_problem', problem_id=answer.problem_id))
    
    if request.method == 'POST':
        content = request.form.get('content')
        if not content:
            flash('回答を入力してください。', 'error')
            return redirect(url_for('edit_answer', answer_id=answer_id))
        
        answer.content = content
        db.session.commit()
        flash('回答を更新しました。', 'success')
        return redirect(url_for('view_problem', problem_id=answer.problem_id))
    
    return render_template('edit_answer.html', answer=answer)


# ============ フィードバック ============

@app.route('/answer/<int:answer_id>/feedback', methods=['POST'])
@login_required
@teacher_required
def send_feedback(answer_id):
    answer = Answer.query.get_or_404(answer_id)
    content = request.form.get('content')
    score = request.form.get('score')
    
    if not content:
        flash('フィードバック内容を入力してください。', 'error')
        return redirect(url_for('view_answer', answer_id=answer_id))
    
    # 既存のフィードバックがあれば削除
    if answer.feedback:
        db.session.delete(answer.feedback)
    
    feedback = Feedback(
        answer_id=answer_id,
        content=content,
        score=int(score) if score else None
    )
    db.session.add(feedback)
    db.session.commit()
    
    # 生徒にプッシュ通知を送信
    try:
        from firebase_notifications import send_feedback_notification
        student = answer.student
        send_feedback_notification(feedback, student)
    except Exception as e:
        print(f"通知送信エラー: {e}")
    
    flash('フィードバックを送信しました。', 'success')
    return redirect(url_for('view_answer', answer_id=answer_id))


@app.route('/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_feedback(feedback_id):
    feedback = Feedback.query.get_or_404(feedback_id)
    answer_id = feedback.answer_id
    db.session.delete(feedback)
    db.session.commit()
    flash('フィードバックを削除しました。', 'success')
    return redirect(url_for('view_answer', answer_id=answer_id))


# ============ 生徒管理 ============

@app.route('/announcements/bulk_delete', methods=['POST'])
@login_required
@teacher_required
def bulk_delete_announcements():
    announcement_ids = request.form.getlist('announcement_ids')
    if not announcement_ids:
        flash('削除する連絡事項が選択されていません。', 'warning')
        return redirect(url_for('manage_announcements'))
    
    count = 0
    for aid in announcement_ids:
        announcement = Announcement.query.get(int(aid))
        if announcement:
            db.session.delete(announcement)
            count += 1
    
    db.session.commit()
    flash(f'{count}件の連絡事項を削除しました。', 'success')
    return redirect(url_for('manage_announcements'))


@app.route('/students')
@login_required
@teacher_required
def manage_students():
    students = User.query.filter_by(role='student').order_by(User.created_at.desc()).all()
    return render_template('manage_students.html', students=students)


@app.route('/students/add', methods=['POST'])
@login_required
@teacher_required
def add_student():
    username = request.form.get('username')
    display_name = request.form.get('display_name')
    password = request.form.get('password')
    is_chinese_student = request.form.get('is_chinese_student') == '1'
    
    if not username or not display_name or not password:
        flash('すべての項目を入力してください。', 'error')
        return redirect(url_for('manage_students'))
    
    # ユーザー名の重複チェック
    if User.query.filter_by(username=username).first():
        flash('このユーザー名は既に使用されています。', 'error')
        return redirect(url_for('manage_students'))
    
    student = User(
        username=username,
        display_name=display_name,
        role='student',
        is_chinese_student=is_chinese_student
    )
    student.set_password(password)
    db.session.add(student)
    db.session.commit()
    
    flash(f'{display_name}さんを追加しました。', 'success')
    return redirect(url_for('manage_students'))


@app.route('/students/<int:student_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_student(student_id):
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('先生は削除できません。', 'error')
        return redirect(url_for('manage_students'))
    
    db.session.delete(student)
    db.session.commit()
    flash('生徒を削除しました。', 'success')
    return redirect(url_for('manage_students'))


@app.route('/students/<int:student_id>/toggle-chinese', methods=['POST'])
@login_required
@teacher_required
def toggle_chinese_student(student_id):
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('この操作は生徒にのみ可能です。', 'error')
        return redirect(url_for('manage_students'))
    
    student.is_chinese_student = not student.is_chinese_student
    db.session.commit()
    
    if student.is_chinese_student:
        flash(f'{student.display_name}さんの日本語学習を有効にしました。', 'success')
    else:
        flash(f'{student.display_name}さんの日本語学習を無効にしました。', 'success')
    return redirect(url_for('manage_students'))


@app.route('/students/<int:student_id>/progress')
@login_required
@teacher_required
def student_progress(student_id):
    """生徒の詳細な学習状況を表示"""
    student = User.query.get_or_404(student_id)
    if student.role != 'student':
        flash('この機能は生徒専用です。', 'error')
        return redirect(url_for('manage_students'))
    
    # 割り当てられた問題を取得
    assigned_problems = student.assigned_problems.all()
    
    # 各問題の回答状況を取得
    problem_stats = []
    for problem in assigned_problems:
        answer = Answer.query.filter_by(problem_id=problem.id, student_id=student.id).first()
        status = 'unanswered'
        feedback_status = None
        if answer:
            status = 'answered'
            if answer.feedback:
                status = 'feedback_received'
                feedback_status = {
                    'score': answer.feedback.score,
                    'created_at': answer.feedback.created_at
                }
        
        problem_stats.append({
            'problem': problem,
            'answer': answer,
            'status': status,
            'feedback_status': feedback_status
        })
    
    # 統計計算
    total = len(problem_stats)
    answered = sum(1 for p in problem_stats if p['status'] != 'unanswered')
    with_feedback = sum(1 for p in problem_stats if p['status'] == 'feedback_received')
    completion_rate = int((answered / total * 100)) if total > 0 else 0
    
    stats = {
        'total': total,
        'answered': answered,
        'unanswered': total - answered,
        'with_feedback': with_feedback,
        'pending_feedback': answered - with_feedback,
        'completion_rate': completion_rate
    }
    
    return render_template('student_progress.html', 
                           student=student, 
                           problem_stats=problem_stats, 
                           stats=stats)


# ============ プロフィール・設定 ============

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not current_user.check_password(current_password):
                flash('現在のパスワードが正しくありません。', 'error')
            elif new_password != confirm_password:
                flash('新しいパスワードが一致しません。', 'error')
            elif len(new_password) < 4:
                flash('パスワードは4文字以上で入力してください。', 'error')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('パスワードを変更しました。', 'success')
        
        elif action == 'change_display_name':
            new_name = request.form.get('display_name')
            if new_name and len(new_name) >= 1:
                current_user.display_name = new_name
                db.session.commit()
                flash('表示名を変更しました。', 'success')
            else:
                flash('表示名を入力してください。', 'error')
        
        return redirect(url_for('settings'))
    
    return render_template('settings.html')


# ============ 連絡事項 ============

@app.route('/announcements')
@login_required
@teacher_required
def manage_announcements():
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    students = User.query.filter_by(role='student').order_by(User.display_name).all()
    return render_template('manage_announcements.html', announcements=announcements, students=students)


@app.route('/announcements/create', methods=['POST'])
@login_required
@teacher_required
def create_announcement():
    title = request.form.get('title')
    content = request.form.get('content')
    is_global = request.form.get('is_global') == 'on'
    selected_students = request.form.getlist('students')
    schedule_type = request.form.get('schedule_type', 'immediate')
    scheduled_at_str = request.form.get('scheduled_at')
    
    if not title or not content:
        flash('タイトルと内容を入力してください。', 'error')
        return redirect(url_for('manage_announcements'))
    
    if not is_global and not selected_students:
        flash('配信先を選択するか、全員に配信にチェックを入れてください。', 'error')
        return redirect(url_for('manage_announcements'))
    
    # 予約配信の場合、日時を確認
    scheduled_at = None
    if schedule_type == 'scheduled':
        if not scheduled_at_str:
            flash('予約配信の場合は日時を指定してください。', 'error')
            return redirect(url_for('manage_announcements'))
        try:
            from datetime import datetime
            scheduled_at = datetime.strptime(scheduled_at_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('日時の形式が正しくありません。', 'error')
            return redirect(url_for('manage_announcements'))
    
    announcement = Announcement(
        title=title,
        content=content,
        teacher_id=current_user.id,
        is_global=is_global
    )
    
    # 選択された生徒を配信先に追加（全員向けでない場合）
    if not is_global:
        for student_id in selected_students:
            student = User.query.get(int(student_id))
            if student:
                announcement.recipients.append(student)
    
    db.session.add(announcement)
    db.session.commit()
    
    # 予約配信の場合
    if schedule_type == 'scheduled' and scheduled_at:
        from models import ScheduledNotification
        scheduled = ScheduledNotification(
            notification_type='announcement',
            target_id=announcement.id,
            scheduled_at=scheduled_at
        )
        db.session.add(scheduled)
        db.session.commit()
        flash(f'連絡事項を予約しました。配信予定: {scheduled_at.strftime("%Y年%m月%d日 %H:%M")}', 'success')
        return redirect(url_for('manage_announcements'))
    
    # 即時配信: プッシュ通知を送信
    try:
        from firebase_notifications import send_announcement_notification
        if is_global:
            # 全員に送信
            recipients = User.query.filter_by(role='student').all()
            print(f"[通知] 全員配信: {len(recipients)}人")
        else:
            recipients = list(announcement.recipients)  # リストに変換
            print(f"[通知] 個別配信: {[r.display_name for r in recipients]}")
        
        for r in recipients:
            print(f"  - {r.display_name}: token={r.fcm_token[:20] if r.fcm_token else 'なし'}...")
        
        sent_count = send_announcement_notification(announcement, recipients)
        if sent_count > 0:
            flash(f'連絡事項を投稿し、{sent_count}人に通知を送信しました。', 'success')
        else:
            if is_global:
                flash('連絡事項を全員に投稿しました。', 'success')
            else:
                flash(f'連絡事項を{len(selected_students)}人の生徒に投稿しました。', 'success')
    except Exception as e:
        print(f"通知送信エラー: {e}")
        import traceback
        traceback.print_exc()
        if is_global:
            flash('連絡事項を全員に投稿しました。', 'success')
        else:
            flash(f'連絡事項を{len(selected_students)}人の生徒に投稿しました。', 'success')
    
    return redirect(url_for('manage_announcements'))


@app.route('/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    db.session.delete(announcement)
    db.session.commit()
    flash('連絡事項を削除しました。', 'success')
    return redirect(url_for('manage_announcements'))


@app.route('/announcements/<int:announcement_id>/toggle', methods=['POST'])
@login_required
@teacher_required
def toggle_announcement(announcement_id):
    announcement = Announcement.query.get_or_404(announcement_id)
    announcement.is_active = not announcement.is_active
    db.session.commit()
    status = '表示' if announcement.is_active else '非表示'
    flash(f'連絡事項を{status}にしました。', 'success')
    return redirect(url_for('manage_announcements'))


# ============ 初期化 ============

def init_db():
    """データベース初期化と先生アカウント作成"""
    with app.app_context():
        db.create_all()
        
        # 先生アカウントがなければ作成、あれば更新
        teacher = User.query.filter_by(role='teacher').first()
        if not teacher:
            teacher = User(
                username='nanami',
                display_name='石川七夢',
                role='teacher'
            )
            db.session.add(teacher)
        
        # パスワードを設定/更新
        teacher.set_password('nanami2005')
        db.session.commit()
        print('先生アカウント:')
        print('  ユーザー名: nanami')
        print('  パスワード: nanami2005')


# ============================================
# 日本語学習 - デフォルト問題データ
# ============================================
DEFAULT_QUIZ_DATA = [
    {"word": "勉強", "correct_reading": "べんきょう", "wrong_readings": ["べんきよう", "べんきゅう", "べんこう"], "meaning_chinese": "学习 xuéxí", "example": "毎日日本語を勉強します。"},
    {"word": "学校", "correct_reading": "がっこう", "wrong_readings": ["がくこう", "がこう", "がっこ"], "meaning_chinese": "学校 xuéxiào", "example": "学校は楽しいです。"},
    {"word": "友達", "correct_reading": "ともだち", "wrong_readings": ["ゆうたち", "ともたち", "ゆうだち"], "meaning_chinese": "朋友 péngyou", "example": "友達と遊びます。"},
    {"word": "先生", "correct_reading": "せんせい", "wrong_readings": ["せんしょう", "さきせい", "せいせん"], "meaning_chinese": "老师 lǎoshī", "example": "先生に質問します。"},
    {"word": "家族", "correct_reading": "かぞく", "wrong_readings": ["いえぞく", "かそく", "けぞく"], "meaning_chinese": "家人 jiārén", "example": "家族は5人です。"},
    {"word": "天気", "correct_reading": "てんき", "wrong_readings": ["てんけ", "あめき", "てんぎ"], "meaning_chinese": "天气 tiānqì", "example": "今日の天気はいいです。"},
    {"word": "食事", "correct_reading": "しょくじ", "wrong_readings": ["たべじ", "しょくし", "しょくに"], "meaning_chinese": "饭/用餐 fàn", "example": "食事の時間です。"},
    {"word": "音楽", "correct_reading": "おんがく", "wrong_readings": ["おとがく", "いんがく", "おんらく"], "meaning_chinese": "音乐 yīnyuè", "example": "音楽を聴きます。"},
    {"word": "運動", "correct_reading": "うんどう", "wrong_readings": ["うんとう", "はこどう", "うどう"], "meaning_chinese": "运动 yùndòng", "example": "運動が好きです。"},
    {"word": "宿題", "correct_reading": "しゅくだい", "wrong_readings": ["やどだい", "しゅくたい", "しゅだい"], "meaning_chinese": "作业 zuòyè", "example": "宿題を忘れました。"},
]

FLASHCARD_DATA = [
    {"word": "学校", "reading": "がっこう", "meaning": "学校 xuéxiào", "example": "学校に行きます。"},
    {"word": "友達", "reading": "ともだち", "meaning": "朋友 péngyou", "example": "友達と遊びます。"},
    {"word": "先生", "reading": "せんせい", "meaning": "老师 lǎoshī", "example": "先生に質問します。"},
    {"word": "勉強", "reading": "べんきょう", "meaning": "学习 xuéxí", "example": "日本語を勉強します。"},
    {"word": "家族", "reading": "かぞく", "meaning": "家人 jiārén", "example": "家族は5人です。"},
    {"word": "天気", "reading": "てんき", "meaning": "天气 tiānqì", "example": "今日の天気はいいです。"},
    {"word": "食事", "reading": "しょくじ", "meaning": "饭/用餐 fàn", "example": "食事の時間です。"},
    {"word": "音楽", "reading": "おんがく", "meaning": "音乐 yīnyuè", "example": "音楽を聴きます。"},
]


# 中国人生徒専用デコレーター
def chinese_student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not current_user.is_teacher() and not current_user.is_chinese_student:
            flash('この機能にアクセスする権限がありません。', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_japanese_stats(user_id):
    """日本語学習の統計を取得"""
    total = JapaneseAnswer.query.filter_by(user_id=user_id).count()
    correct = JapaneseAnswer.query.filter_by(user_id=user_id, is_correct=True).count()
    return {
        'total': total,
        'correct': correct,
        'accuracy': int(correct / total * 100) if total > 0 else 0
    }


# ============================================
# 日本語学習ルート
# ============================================

@app.route('/japanese')
@login_required
@chinese_student_required
def japanese_dashboard():
    stats = get_japanese_stats(current_user.id)
    recent_answers = JapaneseAnswer.query.filter_by(user_id=current_user.id).order_by(JapaneseAnswer.answered_at.desc()).limit(10).all()
    
    # グループ化された日本語課題を取得（ダッシュボードと同じロジック）
    from itertools import groupby
    japanese_tasks = []
    
    # クイズ（全てグループ化）
    quiz_assignments_all = current_user.japanese_assignments.order_by(
        JapaneseAssignment.assigned_at.desc(),
        JapaneseAssignment.id
    ).all()
    
    def get_quiz_group_key(q):
        return q.assigned_at.strftime('%Y-%m-%d %H:%M')
    
    for key, group in groupby(quiz_assignments_all, key=get_quiz_group_key):
        items = list(group)
        if not items:
            continue
        group_date = items[0].assigned_at
        count = len(items)
        items.sort(key=lambda x: x.id)
        first_item = items[0]
        completed_count = sum(1 for item in items if item.completed)
        all_completed = (completed_count == count)
        next_item = next((item for item in items if not item.completed), first_item)
        
        japanese_tasks.append({
            'type': 'quiz_group',
            'title': f"熟語クイズ ({completed_count}/{count}問完了)" if all_completed else f"熟語クイズ ({count}問)",
            'assignment_id': next_item.id,
            'created_at': group_date,
            'completed': all_completed,
        })
    
    # フラッシュカード（全てグループ化）
    flashcard_assignments = current_user.japanese_flashcard_assignments.order_by(
        JapaneseFlashcardAssignment.assigned_at.desc(), 
        JapaneseFlashcardAssignment.id
    ).all()
    
    def get_flashcard_group_key(fa):
        return fa.assigned_at.strftime('%Y-%m-%d %H:%M')
    
    for key, group in groupby(flashcard_assignments, key=get_flashcard_group_key):
        items = list(group)
        if not items:
            continue
        group_date = items[0].assigned_at
        count = len(items)
        items.sort(key=lambda x: x.id)
        first_item = items[0]
        completed_count = sum(1 for item in items if item.completed)
        all_completed = (completed_count == count)
        next_item = next((item for item in items if not item.completed), first_item)
        
        japanese_tasks.append({
            'type': 'flashcard_group',
            'title': f"フラッシュカード ({completed_count}/{count}枚完了)" if all_completed else f"フラッシュカード ({count}枚)",
            'assignment_id': next_item.id,
            'created_at': group_date,
            'completed': all_completed,
        })
    
    # 書き取り（全てグループ化）
    writing_assignments = current_user.japanese_writing_assignments.order_by(
        JapaneseWritingAssignment.assigned_at.desc(),
        JapaneseWritingAssignment.id
    ).all()
    
    def get_writing_group_key(wa):
        return wa.assigned_at.strftime('%Y-%m-%d %H:%M')
    
    for key, group in groupby(writing_assignments, key=get_writing_group_key):
        items = list(group)
        if not items:
            continue
        group_date = items[0].assigned_at
        count = len(items)
        items.sort(key=lambda x: x.id)
        first_item = items[0]
        completed_count = sum(1 for item in items if item.completed)
        all_completed = (completed_count == count)
        next_item = next((item for item in items if not item.completed), first_item)
        
        japanese_tasks.append({
            'type': 'writing_group',
            'title': f"書き取り練習 ({completed_count}/{count}問完了)" if all_completed else f"書き取り練習 ({count}問)",
            'assignment_id': next_item.id,
            'created_at': group_date,
            'completed': all_completed,
        })
    
    # 日付順にソート（新しい順）
    japanese_tasks.sort(key=lambda x: x['created_at'], reverse=True)
    
    return render_template('japanese_dashboard.html', 
                           stats=stats, 
                           recent_answers=recent_answers,
                           japanese_tasks=japanese_tasks)


@app.route('/japanese/quiz')
@login_required
@chinese_student_required
def japanese_quiz():
    # DBから問題を取得、なければデフォルト
    db_quizzes = JapaneseQuiz.query.all()
    if db_quizzes:
        quiz_data = random.choice(db_quizzes)
        quiz = {
            'id': quiz_data.id,
            'word': quiz_data.word,
            'correct_reading': quiz_data.correct_reading,
            'meaning_chinese': quiz_data.meaning_chinese or '',
            'example': quiz_data.example or ''
        }
        options = [quiz_data.correct_reading] + quiz_data.get_wrong_readings()
    else:
        quiz_item = random.choice(DEFAULT_QUIZ_DATA)
        quiz = {
            'id': None,
            'word': quiz_item['word'],
            'correct_reading': quiz_item['correct_reading'],
            'meaning_chinese': quiz_item['meaning_chinese'],
            'example': quiz_item['example']
        }
        options = [quiz_item['correct_reading']] + quiz_item['wrong_readings']
    
    random.shuffle(options)
    return render_template('japanese_quiz.html', quiz=quiz, options=options)


@app.route('/japanese/answer', methods=['POST'])
@login_required
@chinese_student_required
def japanese_answer():
    data = request.get_json()
    answer = JapaneseAnswer(
        user_id=current_user.id,
        quiz_id=data.get('quiz_id'),
        quiz_word=data.get('quiz_word'),
        is_correct=data.get('is_correct', False)
    )
    db.session.add(answer)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/japanese/assigned/<int:assignment_id>')
@login_required
@chinese_student_required
def japanese_assigned_quiz(assignment_id):
    """配信された問題に回答"""
    from datetime import datetime
    assignment = JapaneseAssignment.query.get_or_404(assignment_id)
    
    # 自分宛ての問題か確認
    if assignment.student_id != current_user.id:
        flash('アクセス権限がありません。', 'error')
        return redirect(url_for('japanese_dashboard'))
    
    quiz = assignment.quiz
    quiz_data = {
        'word': quiz.word,
        'correct_reading': quiz.correct_reading,
        'meaning_chinese': quiz.meaning_chinese or '',
        'example': quiz.example or ''
    }
    options = [quiz.correct_reading] + quiz.get_wrong_readings()
    random.shuffle(options)
    
    return render_template('japanese_assigned_quiz.html',
                           quiz=quiz_data,
                           options=options,
                           assignment=assignment)


@app.route('/japanese/assigned/answer', methods=['POST'])
@login_required
@chinese_student_required
def answer_assigned_quiz():
    """配信された問題の回答を記録"""
    from datetime import datetime
    data = request.get_json()
    assignment_id = data.get('assignment_id')
    is_correct = data.get('is_correct', False)
    
    assignment = JapaneseAssignment.query.get(assignment_id)
    if assignment and assignment.student_id == current_user.id:
        assignment.completed = True
        assignment.completed_at = datetime.utcnow()
        assignment.is_correct = is_correct
        
        # 回答履歴も記録
        answer = JapaneseAnswer(
            user_id=current_user.id,
            quiz_id=assignment.quiz_id,
            quiz_word=assignment.quiz.word,
            is_correct=is_correct
        )
        db.session.add(answer)
        db.session.commit()
    
    return jsonify({'success': True})


@app.route('/japanese/flashcard')
@login_required
@chinese_student_required
def japanese_flashcard():
    index = request.args.get('index', 0, type=int)
    
    # DBから取得、なければデフォルトデータ
    db_cards = JapaneseFlashcard.query.all()
    if db_cards:
        cards = [{'word': c.word, 'reading': c.reading, 'meaning': c.meaning, 'example': c.example or ''} for c in db_cards]
    else:
        cards = FLASHCARD_DATA
    
    total = len(cards)
    index = index % total
    card = cards[index]
    
    prev_index = (index - 1) % total
    next_index = (index + 1) % total
    
    return render_template('japanese_flashcard.html', 
                           card=card, 
                           current_index=index, 
                           total=total,
                           prev_index=prev_index,
                           next_index=next_index)


# 書き取り練習用データ（デフォルト）
WRITING_DATA = [
    {"word": "学", "reading": "がく / まなぶ", "meaning": "学 xué - 学ぶ", "example": "学校で勉強します。"},
    {"word": "校", "reading": "こう", "meaning": "校 xiào - 学校", "example": "学校は楽しいです。"},
    {"word": "先", "reading": "せん / さき", "meaning": "先 xiān - 先、前", "example": "先生に聞きます。"},
    {"word": "生", "reading": "せい / い(きる)", "meaning": "生 shēng - 生きる", "example": "先生は優しいです。"},
    {"word": "友", "reading": "ゆう / とも", "meaning": "友 yǒu - 友達", "example": "友達と遊びます。"},
    {"word": "読", "reading": "どく / よ(む)", "meaning": "读 dú - 読む", "example": "本を読みます。"},
    {"word": "書", "reading": "しょ / か(く)", "meaning": "书 shū - 書く", "example": "手紙を書きます。"},
    {"word": "食", "reading": "しょく / た(べる)", "meaning": "食 shí - 食べる", "example": "ご飯を食べます。"},
    {"word": "見", "reading": "けん / み(る)", "meaning": "见 jiàn - 見る", "example": "テレビを見ます。"},
    {"word": "聞", "reading": "ぶん / き(く)", "meaning": "闻 wén - 聞く", "example": "音楽を聞きます。"},
]


@app.route('/japanese/writing')
@login_required
@chinese_student_required
def japanese_writing():
    """漢字書き取り練習"""
    index = request.args.get('index', 0, type=int)
    
    # DBから取得、なければデフォルトデータ
    db_kanjis = JapaneseWriting.query.all()
    if db_kanjis:
        kanjis = [{'word': k.word, 'reading': k.reading, 'meaning': k.meaning, 'example': k.example or ''} for k in db_kanjis]
    else:
        kanjis = WRITING_DATA
    
    total = len(kanjis)
    index = index % total
    kanji = kanjis[index]
    
    prev_index = (index - 1) % total
    next_index = (index + 1) % total
    
    return render_template('japanese_writing.html',
                           kanji=kanji,
                           current_index=index,
                           total=total,
                           prev_index=prev_index,
                           next_index=next_index)


@app.route('/japanese/ai-tutor', methods=['GET', 'POST'])
@login_required
@chinese_student_required
def japanese_ai_tutor():
    response = None
    error = None
    query = None
    
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        if query:
            try:
                prompt = f"""あなたは中国の小学生に日本語を教える優しい先生です。
以下の漢字または熟語について、中国の小学生にも分かりやすく説明してください。

【質問】{query}

回答には以下を含めてください：
1. 読み方（ひらがな）
2. 中国語の意味（ピンイン付き）
3. 簡単な例文
4. 覚え方のコツ（あれば）

できるだけ簡単な言葉を使って説明してください。"""
                
                completion = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.7
                )
                response = completion.choices[0].message.content
            except Exception as e:
                error = f"AIへの接続でエラーが発生しました: {str(e)}"
    
    return render_template('japanese_ai_tutor.html', response=response, error=error, query=query)


@app.route('/japanese/ai-quiz', methods=['GET', 'POST'])
@login_required
@chinese_student_required
def japanese_ai_quiz():
    quiz = None
    error = None
    
    if request.method == 'POST':
        difficulty = request.form.get('difficulty', 'medium')
        
        difficulty_map = {
            'easy': 'N5レベル（最も簡単）',
            'medium': 'N4レベル（普通）',
            'hard': 'N3レベル（難しい）'
        }
        
        prompt = f"""日本語学習者のために、{difficulty_map.get(difficulty, 'N4レベル')}の熟語クイズを1問作ってください。

以下のJSON形式で回答してください（他のテキストは含めないでください）：
{{
    "word": "熟語（漢字）",
    "correct_reading": "正しい読み方",
    "wrong_readings": ["間違い1", "間違い2", "間違い3"],
    "meaning_chinese": "中国語の意味（ピンイン付き）",
    "example": "例文"
}}"""
        
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.8
            )
            response_text = completion.choices[0].message.content
            
            # JSON抽出
            import re
            json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
                options = [quiz_data['correct_reading']] + quiz_data.get('wrong_readings', [])[:3]
                random.shuffle(options)
                quiz = {
                    'word': quiz_data.get('word', ''),
                    'correct_reading': quiz_data.get('correct_reading', ''),
                    'meaning_chinese': quiz_data.get('meaning_chinese', ''),
                    'example': quiz_data.get('example', ''),
                    'options': options
                }
        except Exception as e:
            error = f"問題の生成に失敗しました: {str(e)}"
    
    return render_template('japanese_ai_quiz.html', quiz=quiz, error=error)


# ============================================
# 先生用：日本語問題管理
# ============================================

@app.route('/teacher/japanese')
@login_required
@teacher_required
@teacher_required
def teacher_japanese_problems():
    """先生用：日本語問題一覧（評価画面統合）"""
    problems = JapaneseQuiz.query.order_by(JapaneseQuiz.created_at.desc()).all()
    chinese_students = User.query.filter_by(role='student', is_chinese_student=True).all()
    
    # 完了済み課題（フィードバック用）を取得
    quizzes = db.session.query(JapaneseAssignment, User).join(User).filter(JapaneseAssignment.completed == True).all()
    flashcards = db.session.query(JapaneseFlashcardAssignment, User).join(User).filter(JapaneseFlashcardAssignment.completed == True).all()
    writings = db.session.query(JapaneseWritingAssignment, User).join(User).filter(JapaneseWritingAssignment.completed == True).all()
    
    tasks = []
    
    for q, s in quizzes:
        tasks.append({
            'type': 'quiz',
            'id': q.id,
            'student_name': s.display_name,
            'title': f"クイズ: {q.quiz.word}",
            'assigned_at': q.assigned_at,
            'completed_at': q.completed_at,
            'feedback': q.teacher_feedback,
            'status': '正解' if q.is_correct else '完了',
            'result_image': None
        })
        
    for f, s in flashcards:
        tasks.append({
            'type': 'flashcard',
            'id': f.id,
            'student_name': s.display_name,
            'title': f"カード: {f.flashcard.word}",
            'assigned_at': f.assigned_at,
            'completed_at': f.completed_at,
            'feedback': f.teacher_feedback,
            'status': '覚えた',
            'result_image': None
        })
        
    for w, s in writings:
        tasks.append({
            'type': 'writing',
            'id': w.id,
            'student_name': s.display_name,
            'title': f"書き取り: {w.writing.word}",
            'assigned_at': w.assigned_at,
            'completed_at': w.completed_at,
            'feedback': w.teacher_feedback,
            'status': '練習済',
            'result_image': w.result_image  # 画像データ
        })
    
    # グルーピング処理
    grouped_tasks = {}
    for task in tasks:
        # キー: 生徒名 + 課題配信日時(分まで)
        key = (task['student_name'], task['assigned_at'].strftime('%Y-%m-%d %H:%M'))
        if key not in grouped_tasks:
            grouped_tasks[key] = {
                'student_name': task['student_name'],
                'date': task['assigned_at'],
                'tasks': []
            }
        grouped_tasks[key]['tasks'].append(task)
    
    # リスト化してソート（新しい順）
    grouped_list = sorted(grouped_tasks.values(), key=lambda x: x['date'], reverse=True)
    
    return render_template('teacher_japanese_problems.html', problems=problems, chinese_students=chinese_students, grouped_tasks=grouped_list)


@app.route('/teacher/japanese/generate', methods=['GET', 'POST'])
@login_required
@teacher_required
def teacher_japanese_generate():
    """先生用：AIで問題一括生成"""
    generated_problems = []
    error = None
    total_problems = JapaneseQuiz.query.count()
    
    if request.method == 'POST':
        difficulty = request.form.get('difficulty', 'medium')
        count = int(request.form.get('count', 5))
        theme = request.form.get('theme', '').strip()
        
        difficulty_map = {
            'easy': 'N5レベル（最も簡単、小学校低学年向け）',
            'medium': 'N4レベル（普通、小学校高学年向け）',
            'hard': 'N3レベル（難しい、中学生向け）'
        }
        
        theme_text = f"テーマは「{theme}」に関連する熟語で" if theme else ""
        
        prompt = f"""日本語学習者のために、{difficulty_map.get(difficulty, 'N4レベル')}の熟語クイズを{count}問作ってください。
{theme_text}

以下のJSON配列形式で回答してください（他のテキストは含めないでください）：
[
  {{
    "word": "熟語（漢字）",
    "correct_reading": "正しい読み方（ひらがな）",
    "wrong_readings": ["間違い1", "間違い2", "間違い3"],
    "meaning_chinese": "中国語の意味（ピンイン付き）",
    "example": "例文"
  }}
]

各問題は異なる熟語にしてください。間違い選択肢は、正解と似ているが間違っているものにしてください。"""
        
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8
            )
            response_text = completion.choices[0].message.content
            
            # JSON抽出
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                problems_data = json.loads(json_match.group())
                
                for prob in problems_data:
                    # DBに保存
                    new_quiz = JapaneseQuiz(
                        word=prob.get('word', ''),
                        correct_reading=prob.get('correct_reading', ''),
                        wrong_readings=json.dumps(prob.get('wrong_readings', []), ensure_ascii=False),
                        meaning_chinese=prob.get('meaning_chinese', ''),
                        example=prob.get('example', ''),
                        category=difficulty,
                        created_by=current_user.id
                    )
                    db.session.add(new_quiz)
                    generated_problems.append(prob)
                
                db.session.commit()
                total_problems = JapaneseQuiz.query.count()
                flash(f'{len(generated_problems)}問の問題を生成・保存しました！', 'success')
            else:
                error = "AIからの応答にJSONが見つかりませんでした"
        except Exception as e:
            error = f"問題の生成に失敗しました: {str(e)}"
    
    return render_template('teacher_japanese_generate.html', 
                           generated_problems=generated_problems, 
                           error=error,
                           total_problems=total_problems)


@app.route('/teacher/japanese/add', methods=['POST'])
@login_required
@teacher_required
def add_japanese_problem():
    """先生用：問題を手動追加"""
    word = request.form.get('word')
    correct_reading = request.form.get('correct_reading')
    wrong1 = request.form.get('wrong1')
    wrong2 = request.form.get('wrong2')
    wrong3 = request.form.get('wrong3')
    meaning_chinese = request.form.get('meaning_chinese', '')
    example = request.form.get('example', '')
    
    if not all([word, correct_reading, wrong1, wrong2, wrong3]):
        flash('必須項目を入力してください', 'error')
        return redirect(url_for('teacher_japanese_problems'))
    
    new_quiz = JapaneseQuiz(
        word=word,
        correct_reading=correct_reading,
        wrong_readings=json.dumps([wrong1, wrong2, wrong3], ensure_ascii=False),
        meaning_chinese=meaning_chinese,
        example=example,
        category='manual',
        created_by=current_user.id
    )
    db.session.add(new_quiz)
    db.session.commit()
    
    flash(f'問題「{word}」を追加しました！', 'success')
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/japanese/<int:problem_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_japanese_problem(problem_id):
    """先生用：問題を削除"""
    problem = JapaneseQuiz.query.get_or_404(problem_id)
    word = problem.word
    db.session.delete(problem)
    db.session.commit()
    flash(f'問題「{word}」を削除しました。', 'success')
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/japanese/edit', methods=['POST'])
@login_required
@teacher_required
def edit_japanese_problem():
    """先生用：問題を編集"""
    problem_id = request.form.get('problem_id')
    word = request.form.get('word')
    correct_reading = request.form.get('correct_reading')
    meaning_chinese = request.form.get('meaning_chinese', '')
    example = request.form.get('example', '')
    
    problem = JapaneseQuiz.query.get_or_404(problem_id)
    problem.word = word
    problem.correct_reading = correct_reading
    problem.meaning_chinese = meaning_chinese
    problem.example = example
    
    db.session.commit()
    flash(f'問題「{word}」を更新しました！', 'success')
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/japanese/bulk-delete', methods=['POST'])
@login_required
@teacher_required
def bulk_delete_japanese_problems():
    """先生用：問題を一括削除"""
    problem_ids = request.form.get('problem_ids', '')
    
    if not problem_ids:
        flash('問題を選択してください。', 'error')
        return redirect(url_for('teacher_japanese_problems'))
    
    ids = [int(id) for id in problem_ids.split(',') if id]
    count = 0
    for problem_id in ids:
        problem = JapaneseQuiz.query.get(problem_id)
        if problem:
            db.session.delete(problem)
            count += 1
    
    db.session.commit()
    flash(f'{count}問の問題を削除しました。', 'success')
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/japanese/bulk-send', methods=['POST'])
@login_required
@teacher_required
def bulk_send_japanese_quiz():
    """先生用：問題を一括配信"""
    quiz_ids = request.form.get('quiz_ids', '')
    student_ids = request.form.getlist('student_ids')
    
    if not quiz_ids or not student_ids:
        flash('問題と生徒を選択してください。', 'error')
        return redirect(url_for('teacher_japanese_problems'))
    
    quiz_id_list = [int(id) for id in quiz_ids.split(',') if id]
    
    count = 0
    for quiz_id in quiz_id_list:
        for student_id in student_ids:
            existing = JapaneseAssignment.query.filter_by(
                quiz_id=quiz_id,
                student_id=int(student_id)
            ).first()
            
            if not existing:
                assignment = JapaneseAssignment(
                    quiz_id=quiz_id,
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
    
    db.session.commit()
    flash(f'{len(quiz_id_list)}問を{len(student_ids)}人の生徒に配信しました！（計{count}件）', 'success')
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/japanese/send')
@login_required
@teacher_required
def teacher_japanese_send():
    """先生用：問題を生徒に配信する画面（全タイプ対応）"""
    # クイズ
    quizzes = JapaneseQuiz.query.order_by(JapaneseQuiz.created_at.desc()).all()
    # フラッシュカード
    flashcards = JapaneseFlashcard.query.order_by(JapaneseFlashcard.created_at.desc()).all()
    # 書き取り
    writings = JapaneseWriting.query.order_by(JapaneseWriting.created_at.desc()).all()
    # 配信対象の生徒
    chinese_students = User.query.filter_by(role='student', is_chinese_student=True).all()
    # 最近の配信履歴（クイズのみ表示）
    recent_assignments = JapaneseAssignment.query.order_by(JapaneseAssignment.assigned_at.desc()).limit(20).all()
    
    return render_template('teacher_japanese_send.html',
                           quizzes=quizzes,
                           flashcards=flashcards,
                           writings=writings,
                           chinese_students=chinese_students,
                           recent_assignments=recent_assignments)


@app.route('/teacher/japanese/send', methods=['POST'])
@login_required
@teacher_required
def send_japanese_quiz():
    """先生用：問題を一括配信（クイズ・フラッシュカード・書き取り対応）"""
    quiz_ids = request.form.getlist('quiz_ids')
    flashcard_ids = request.form.getlist('flashcard_ids')
    writing_ids = request.form.getlist('writing_ids')
    student_ids = request.form.getlist('student_ids')
    
    if not student_ids:
        flash('配信先の生徒を選択してください。', 'error')
        return redirect(url_for('teacher_japanese_send'))
    
    if not quiz_ids and not flashcard_ids and not writing_ids:
        flash('配信する問題を選択してください。', 'error')
        return redirect(url_for('teacher_japanese_send'))
    
    count = 0
    
    # クイズの配信
    for quiz_id in quiz_ids:
        for student_id in student_ids:
            existing = JapaneseAssignment.query.filter_by(
                quiz_id=int(quiz_id),
                student_id=int(student_id)
            ).first()
            if not existing:
                assignment = JapaneseAssignment(
                    quiz_id=int(quiz_id),
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
    
    # フラッシュカードの配信
    for flashcard_id in flashcard_ids:
        for student_id in student_ids:
            existing = JapaneseFlashcardAssignment.query.filter_by(
                flashcard_id=int(flashcard_id),
                student_id=int(student_id)
            ).first()
            if not existing:
                assignment = JapaneseFlashcardAssignment(
                    flashcard_id=int(flashcard_id),
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
    
    # 書き取りの配信
    for writing_id in writing_ids:
        for student_id in student_ids:
            existing = JapaneseWritingAssignment.query.filter_by(
                writing_id=int(writing_id),
                student_id=int(student_id)
            ).first()
            if not existing:
                assignment = JapaneseWritingAssignment(
                    writing_id=int(writing_id),
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
    
    db.session.commit()
    
    # 詳細メッセージ
    msg_parts = []
    if quiz_ids:
        msg_parts.append(f'クイズ{len(quiz_ids)}問')
    if flashcard_ids:
        msg_parts.append(f'フラッシュカード{len(flashcard_ids)}枚')
    if writing_ids:
        msg_parts.append(f'書き取り{len(writing_ids)}問')
    
    flash(f'{" + ".join(msg_parts)}を{len(student_ids)}人の生徒に配信しました！（計{count}件）', 'success')
    return redirect(url_for('teacher_japanese_send'))


# ============================================
# 先生用：フラッシュカード管理
# ============================================

@app.route('/teacher/flashcard')
@login_required
@teacher_required
def teacher_flashcard_manage():
    """フラッシュカード管理画面"""
    cards = JapaneseFlashcard.query.order_by(JapaneseFlashcard.created_at.desc()).all()
    chinese_students = User.query.filter_by(role='student', is_chinese_student=True).all()
    return render_template('teacher_flashcard_manage.html', cards=cards, chinese_students=chinese_students)


@app.route('/teacher/flashcard/edit', methods=['POST'])
@login_required
@teacher_required
def edit_flashcard():
    """フラッシュカード編集"""
    card_id = request.form.get('card_id')
    card = JapaneseFlashcard.query.get_or_404(card_id)
    
    card.word = request.form.get('word')
    card.reading = request.form.get('reading')
    card.meaning = request.form.get('meaning')
    card.example = request.form.get('example', '')
    
    db.session.commit()
    flash(f'カード「{card.word}」を更新しました！', 'success')
    return redirect(url_for('teacher_flashcard_manage'))


@app.route('/teacher/flashcard/add', methods=['POST'])
@login_required
@teacher_required
def add_flashcard():
    """フラッシュカード追加"""
    card = JapaneseFlashcard(
        word=request.form.get('word'),
        reading=request.form.get('reading'),
        meaning=request.form.get('meaning'),
        example=request.form.get('example', ''),
        created_by=current_user.id
    )
    db.session.add(card)
    db.session.commit()
    flash(f'カード「{card.word}」を追加しました！', 'success')
    return redirect(url_for('teacher_flashcard_manage'))


@app.route('/teacher/flashcard/<int:card_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_flashcard(card_id):
    """フラッシュカード削除"""
    card = JapaneseFlashcard.query.get_or_404(card_id)
    db.session.delete(card)
    db.session.commit()
    flash('カードを削除しました。', 'success')
    return redirect(url_for('teacher_flashcard_manage'))


@app.route('/teacher/flashcard/bulk-delete', methods=['POST'])
@login_required
@teacher_required
def bulk_delete_flashcards():
    """フラッシュカード一括削除"""
    card_ids = request.form.get('card_ids', '')
    
    if not card_ids:
        flash('カードを選択してください。', 'error')
        return redirect(url_for('teacher_flashcard_manage'))
    
    ids = [int(id) for id in card_ids.split(',') if id]
    count = 0
    for card_id in ids:
        card = JapaneseFlashcard.query.get(card_id)
        if card:
            db.session.delete(card)
            count += 1
    
    db.session.commit()
    flash(f'{count}枚のカードを削除しました。', 'success')
    return redirect(url_for('teacher_flashcard_manage'))


@app.route('/teacher/flashcard/bulk-send', methods=['POST'])
@login_required
@teacher_required
def bulk_send_flashcards():
    """フラッシュカード一括配信"""
    card_ids = request.form.get('card_ids', '')
    student_ids = request.form.getlist('student_ids')
    
    if not card_ids or not student_ids:
        flash('カードと生徒を選択してください。', 'error')
        return redirect(url_for('teacher_flashcard_manage'))
    
    id_list = [int(id) for id in card_ids.split(',') if id]
    count = 0
    
    for card_id in id_list:
        for student_id in student_ids:
            existing = JapaneseFlashcardAssignment.query.filter_by(
                flashcard_id=card_id,
                student_id=int(student_id)
            ).first()
            if not existing:
                assignment = JapaneseFlashcardAssignment(
                    flashcard_id=card_id,
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
                
    db.session.commit()
    flash(f'{len(id_list)}枚のカードを{len(student_ids)}人の生徒に配信しました！（計{count}件）', 'success')
    return redirect(url_for('teacher_flashcard_manage'))


@app.route('/teacher/flashcard/generate', methods=['POST'])
@login_required
@teacher_required
def generate_flashcards():
    """AIでフラッシュカード生成"""
    theme = request.form.get('theme', '').strip()
    count = int(request.form.get('count', 10))
    
    theme_text = f"テーマは「{theme}」に関連する単語で" if theme else ""
    
    prompt = f"""中国の小学生のための日本語学習フラッシュカードを{count}枚作ってください。
{theme_text}

JSON配列形式で回答してください：
[
  {{"word": "漢字/熟語", "reading": "読み方", "meaning": "中国語の意味（ピンイン付き）", "example": "例文"}}
]"""
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.8
        )
        response_text = completion.choices[0].message.content
        
        import re
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            cards_data = json.loads(json_match.group())
            for card_data in cards_data:
                card = JapaneseFlashcard(
                    word=card_data.get('word', ''),
                    reading=card_data.get('reading', ''),
                    meaning=card_data.get('meaning', ''),
                    example=card_data.get('example', ''),
                    created_by=current_user.id
                )
                db.session.add(card)
            db.session.commit()
            flash(f'{len(cards_data)}枚のカードを生成しました！', 'success')
    except Exception as e:
        flash(f'生成に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('teacher_flashcard_manage'))


# ============================================
# 先生用：書き取り練習管理
# ============================================

@app.route('/teacher/writing')
@login_required
@teacher_required
def teacher_writing_manage():
    """書き取り練習管理画面"""
    writings = JapaneseWriting.query.order_by(JapaneseWriting.created_at.desc()).all()
    chinese_students = User.query.filter_by(role='student', is_chinese_student=True).all()
    return render_template('teacher_writing_manage.html', writings=writings, chinese_students=chinese_students)


@app.route('/teacher/writing/edit', methods=['POST'])
@login_required
@teacher_required
def edit_writing():
    """書き取り練習編集"""
    writing_id = request.form.get('writing_id')
    writing = JapaneseWriting.query.get_or_404(writing_id)
    
    writing.word = request.form.get('word')
    writing.reading = request.form.get('reading')
    writing.meaning = request.form.get('meaning')
    writing.example = request.form.get('example', '')
    # stroke_countはフォームに含まれていれば更新（なければ維持）
    stroke = request.form.get('stroke_count')
    if stroke:
        writing.stroke_count = int(stroke)
    
    db.session.commit()
    flash(f'書き取り「{writing.word}」を更新しました！', 'success')
    return redirect(url_for('teacher_writing_manage'))


@app.route('/teacher/writing/add', methods=['POST'])
@login_required
@teacher_required
def add_writing():
    """書き取り練習追加"""
    stroke = request.form.get('stroke_count')
    writing = JapaneseWriting(
        word=request.form.get('word'),
        reading=request.form.get('reading'),
        meaning=request.form.get('meaning'),
        example=request.form.get('example', ''),
        stroke_count=int(stroke) if stroke else None,
        created_by=current_user.id
    )
    db.session.add(writing)
    db.session.commit()
    flash(f'書き取り「{writing.word}」を追加しました！', 'success')
    return redirect(url_for('teacher_writing_manage'))


@app.route('/teacher/writing/<int:writing_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_writing(writing_id):
    """書き取り練習削除"""
    writing = JapaneseWriting.query.get_or_404(writing_id)
    db.session.delete(writing)
    db.session.commit()
    flash('書き取り練習を削除しました。', 'success')
    return redirect(url_for('teacher_writing_manage'))


@app.route('/teacher/writing/bulk-delete', methods=['POST'])
@login_required
@teacher_required
def bulk_delete_writings():
    """書き取り練習一括削除"""
    writing_ids = request.form.get('writing_ids', '')
    
    if not writing_ids:
        flash('書き取り練習を選択してください。', 'error')
        return redirect(url_for('teacher_writing_manage'))
    
    ids = [int(id) for id in writing_ids.split(',') if id]
    count = 0
    for w_id in ids:
        writing = JapaneseWriting.query.get(w_id)
        if writing:
            db.session.delete(writing)
            count += 1
    
    db.session.commit()
    flash(f'{count}問の書き取り練習を削除しました。', 'success')
    return redirect(url_for('teacher_writing_manage'))


@app.route('/teacher/writing/bulk-send', methods=['POST'])
@login_required
@teacher_required
def bulk_send_writings():
    """書き取り練習一括配信"""
    writing_ids = request.form.get('writing_ids', '')
    student_ids = request.form.getlist('student_ids')
    
    if not writing_ids or not student_ids:
        flash('書き取り練習と生徒を選択してください。', 'error')
        return redirect(url_for('teacher_writing_manage'))
    
    id_list = [int(id) for id in writing_ids.split(',') if id]
    count = 0
    
    for w_id in id_list:
        for student_id in student_ids:
            existing = JapaneseWritingAssignment.query.filter_by(
                writing_id=w_id,
                student_id=int(student_id)
            ).first()
            if not existing:
                assignment = JapaneseWritingAssignment(
                    writing_id=w_id,
                    student_id=int(student_id)
                )
                db.session.add(assignment)
                count += 1
                
    db.session.commit()
    flash(f'{len(id_list)}問の書き取り練習を{len(student_ids)}人の生徒に配信しました！（計{count}件）', 'success')
    return redirect(url_for('teacher_writing_manage'))


@app.route('/teacher/writing/generate', methods=['POST'])
@login_required
@teacher_required
def generate_writings():
    """AIで書き取り漢字生成"""
    level = request.form.get('level', 'medium')
    count = int(request.form.get('count', 10))
    
    level_map = {
        'easy': '小学1-2年生レベル（画数が少なく簡単な漢字）',
        'medium': '小学3-4年生レベル（よく使う基本的な漢字）',
        'hard': '小学5-6年生レベル（少し難しい漢字）'
    }
    
    prompt = f"""中国の小学生が練習するための日本語の漢字を{count}字選んでください。
レベル: {level_map.get(level, '小学3-4年生レベル')}

JSON配列形式で回答してください：
[
  {{"word": "漢字1文字", "reading": "読み方（音読み/訓読み）", "meaning": "中国語の意味（ピンイン付き）", "example": "例文", "stroke_count": 画数}}
]"""
    
    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.8
        )
        response_text = completion.choices[0].message.content
        
        import re
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            kanjis_data = json.loads(json_match.group())
            for kanji_data in kanjis_data:
                kanji = JapaneseWriting(
                    word=kanji_data.get('word', '')[:2],
                    reading=kanji_data.get('reading', ''),
                    meaning=kanji_data.get('meaning', ''),
                    example=kanji_data.get('example', ''),
                    stroke_count=kanji_data.get('stroke_count'),
                    created_by=current_user.id
                )
                db.session.add(kanji)
            db.session.commit()
            flash(f'{len(kanjis_data)}字の漢字を生成しました！', 'success')
    except Exception as e:
        flash(f'生成に失敗しました: {str(e)}', 'error')
    
    return redirect(url_for('teacher_writing_manage'))


# ============================================
# 先生用：学年別漢字管理
# ============================================

@app.route('/teacher/kanji')
@login_required
@teacher_required
def teacher_kanji_list():
    """先生用：学年別漢字一覧"""
    from kanji_data import GRADE_NAMES
    
    current_grade = request.args.get('grade', 'grade1')
    search_query = request.args.get('q', '').strip()
    
    # 利用可能な学年リスト
    grades = GradeKanji.get_grades()
    
    # 各学年の漢字数
    kanji_counts = {}
    for grade_code, _ in grades:
        kanji_counts[grade_code] = GradeKanji.query.filter_by(grade=grade_code).count()
    
    # 検索クエリがある場合は全学年から検索
    if search_query:
        kanji_list = GradeKanji.query.filter(
            db.or_(
                GradeKanji.kanji.contains(search_query),
                GradeKanji.on_reading.contains(search_query),
                GradeKanji.kun_reading.contains(search_query),
                GradeKanji.meaning.contains(search_query)
            )
        ).order_by(GradeKanji.grade, GradeKanji.id).all()
        current_grade_name = f'検索結果: 「{search_query}」'
        is_search = True
    else:
        # 現在の学年の漢字リスト
        kanji_list = GradeKanji.query.filter_by(grade=current_grade).order_by(GradeKanji.id).all()
        current_grade_name = GRADE_NAMES.get(current_grade, current_grade)
        is_search = False
    
    return render_template('teacher_kanji_list.html',
                           grades=grades,
                           current_grade=current_grade,
                           current_grade_name=current_grade_name,
                           kanji_list=kanji_list,
                           kanji_counts=kanji_counts,
                           search_query=search_query,
                           is_search=is_search)


@app.route('/api/kanji/<grade>')
@login_required
@teacher_required
def api_kanji_by_grade(grade):
    """API: 指定学年の漢字リストをJSONで返す"""
    kanji_list = GradeKanji.query.filter_by(grade=grade).all()
    return jsonify([{
        'id': k.id,
        'kanji': k.kanji,
        'on_reading': k.on_reading,
        'kun_reading': k.kun_reading,
        'stroke_count': k.stroke_count,
        'meaning': k.meaning
    } for k in kanji_list])


@app.route('/teacher/kanji/generate', methods=['POST'])
@login_required
@teacher_required
def teacher_kanji_generate():
    """先生用：選択した漢字からAI問題生成"""
    selected_kanji = request.form.get('selected_kanji', '')
    problem_type = request.form.get('problem_type', 'quiz')
    count_str = request.form.get('count', '5')
    send_immediately = request.form.get('send_immediately') == '1'
    
    if not selected_kanji:
        flash('漢字を選択してください', 'error')
        return redirect(url_for('teacher_kanji_list'))
    
    kanji_list = list(selected_kanji)
    
    # 生成数の決定
    if count_str == 'all':
        count = len(kanji_list)
    else:
        count = min(int(count_str), len(kanji_list))
    
    # ランダムに選択
    selected = random.sample(kanji_list, count) if count < len(kanji_list) else kanji_list
    kanji_str = '、'.join(selected)
    
    # 即時配信用：中国人生徒を取得
    chinese_students = []
    if send_immediately:
        chinese_students = User.query.filter_by(role='student', is_chinese_student=True).all()
    
    if problem_type == 'quiz':
        # 読み方クイズ生成
        prompt = f"""以下の漢字について、読み方クイズを作ってください。

対象漢字: {kanji_str}

以下のJSON配列形式で回答してください（他のテキストは含めないでください）：
[
  {{
    "word": "漢字を使った熟語（2-3字）",
    "correct_reading": "正しい読み方（ひらがな）",
    "wrong_readings": ["間違い1", "間違い2", "間違い3"],
    "meaning_chinese": "中国語の意味（ピンイン付き）",
    "example": "例文"
  }}
]

各漢字について1問ずつ作成してください。間違い選択肢は正解と似ているが間違っているものにしてください。"""
        
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8
            )
            response_text = completion.choices[0].message.content
            
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                problems_data = json.loads(json_match.group())
                
                generated_quiz_ids = []
                for prob in problems_data:
                    new_quiz = JapaneseQuiz(
                        word=prob.get('word', ''),
                        correct_reading=prob.get('correct_reading', ''),
                        wrong_readings=json.dumps(prob.get('wrong_readings', []), ensure_ascii=False),
                        meaning_chinese=prob.get('meaning_chinese', ''),
                        example=prob.get('example', ''),
                        category='kanji_grade',
                        created_by=current_user.id
                    )
                    db.session.add(new_quiz)
                    db.session.flush()  # IDを取得
                    generated_quiz_ids.append(new_quiz.id)
                
                db.session.commit()
                
                # 即時配信
                if send_immediately and chinese_students and generated_quiz_ids:
                    send_count = 0
                    for quiz_id in generated_quiz_ids:
                        for student in chinese_students:
                            existing = JapaneseAssignment.query.filter_by(
                                quiz_id=quiz_id,
                                student_id=student.id
                            ).first()
                            if not existing:
                                assignment = JapaneseAssignment(
                                    quiz_id=quiz_id,
                                    student_id=student.id
                                )
                                db.session.add(assignment)
                                send_count += 1
                    db.session.commit()
                    flash(f'{len(problems_data)}問の読み方クイズを生成し、{len(chinese_students)}人の生徒に配信しました！', 'success')
                else:
                    flash(f'{len(problems_data)}問の読み方クイズを生成しました！', 'success')
                return redirect(url_for('teacher_japanese_problems'))
            else:
                flash('AIからの応答にJSONが見つかりませんでした', 'error')
        except Exception as e:
            flash(f'問題の生成に失敗しました: {str(e)}', 'error')
    
    elif problem_type == 'flashcard':
        # フラッシュカード生成
        prompt = f"""以下の漢字について、フラッシュカード用のデータを作ってください。

対象漢字: {kanji_str}

以下のJSON配列形式で回答してください（他のテキストは含めないでください）：
[
  {{
    "word": "漢字を含む熟語",
    "reading": "読み方（ひらがな）",
    "meaning": "中国語の意味",
    "example": "例文（日本語）"
  }}
]

各漢字について1つずつ作成してください。"""

        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8
            )
            response_text = completion.choices[0].message.content
            
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                cards_data = json.loads(json_match.group())
                
                generated_ids = []
                for card in cards_data:
                    new_card = JapaneseFlashcard(
                        word=card.get('word', ''),
                        reading=card.get('reading', ''),
                        meaning=card.get('meaning', ''),
                        example=card.get('example', ''),
                        created_by=current_user.id
                    )
                    db.session.add(new_card)
                    db.session.flush()
                    generated_ids.append(new_card.id)
                
                db.session.commit()
                
                # 即時配信
                if send_immediately and chinese_students and generated_ids:
                    send_count = 0
                    for card_id in generated_ids:
                        for student in chinese_students:
                            existing = JapaneseFlashcardAssignment.query.filter_by(
                                flashcard_id=card_id,
                                student_id=student.id
                            ).first()
                            if not existing:
                                assignment = JapaneseFlashcardAssignment(
                                    flashcard_id=card_id,
                                    student_id=student.id
                                )
                                db.session.add(assignment)
                                send_count += 1
                    db.session.commit()
                    flash(f'{len(cards_data)}枚のフラッシュカードを生成し、{len(chinese_students)}人の生徒に配信しました！', 'success')
                else:
                    flash(f'{len(cards_data)}枚のフラッシュカードを生成しました！', 'success')
                return redirect(url_for('teacher_flashcard_manage'))
            else:
                flash('AIからの応答にJSONが見つかりませんでした', 'error')
        except Exception as e:
            flash(f'フラッシュカードの生成に失敗しました: {str(e)}', 'error')

    elif problem_type == 'writing':
        # 書き取り練習生成
        prompt = f"""以下の漢字について、書き取り練習用のデータを作ってください。

対象漢字: {kanji_str}

以下のJSON配列形式で回答してください（他のテキストは含めないでください）：
[
  {{
    "word": "漢字（対象の1文字）",
    "reading": "読み方（音読み・訓読み）",
    "meaning": "中国語の意味",
    "example": "その漢字を使った短い例文",
    "stroke_count": 画数（数値）
  }}
]"""

        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.8
            )
            response_text = completion.choices[0].message.content
            
            import re
            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                writings_data = json.loads(json_match.group())
                
                generated_ids = []
                for item in writings_data:
                    # 漢字1文字であることを確認
                    word = item.get('word', '')
                    if len(word) > 1:
                        # 漢字の部分だけ抽出を試みる、またはそのまま使う
                        pass 
                        
                    new_writing = JapaneseWriting(
                        word=word,
                        reading=item.get('reading', ''),
                        meaning=item.get('meaning', ''),
                        example=item.get('example', ''),
                        stroke_count=item.get('stroke_count', 0),
                        created_by=current_user.id
                    )
                    db.session.add(new_writing)
                    db.session.flush()
                    generated_ids.append(new_writing.id)
                
                db.session.commit()
                
                # 即時配信
                if send_immediately and chinese_students and generated_ids:
                    send_count = 0
                    for writing_id in generated_ids:
                        for student in chinese_students:
                            existing = JapaneseWritingAssignment.query.filter_by(
                                writing_id=writing_id,
                                student_id=student.id
                            ).first()
                            if not existing:
                                assignment = JapaneseWritingAssignment(
                                    writing_id=writing_id,
                                    student_id=student.id
                                )
                                db.session.add(assignment)
                                send_count += 1
                    db.session.commit()
                    flash(f'{len(writings_data)}問の書き取り練習を生成し、{len(chinese_students)}人の生徒に配信しました！', 'success')
                else:
                    flash(f'{len(writings_data)}問の書き取り練習を生成しました！', 'success')
                return redirect(url_for('teacher_writing_manage'))
            else:
                flash('AIからの応答にJSONが見つかりませんでした', 'error')
        except Exception as e:
            flash(f'書き取り練習の生成に失敗しました: {str(e)}', 'error')

    return redirect(url_for('teacher_kanji_list'))






# ============================================
# 先生用：フィードバック管理
# ============================================

@app.route('/teacher/feedback/save', methods=['POST'])
@login_required
@teacher_required
def save_feedback():
    task_type = request.form.get('type')
    assignment_id = request.form.get('id')
    feedback = request.form.get('feedback')
    
    if task_type == 'quiz':
        assignment = JapaneseAssignment.query.get(assignment_id)
    elif task_type == 'flashcard':
        assignment = JapaneseFlashcardAssignment.query.get(assignment_id)
    elif task_type == 'writing':
        assignment = JapaneseWritingAssignment.query.get(assignment_id)
    else:
        flash('不明な課題タイプです', 'error')
        return redirect(url_for('teacher_japanese_problems'))
        
    if assignment:
        assignment.teacher_feedback = feedback
        db.session.commit()
        flash('フィードバックを保存しました', 'success')
        
    
    return redirect(url_for('teacher_japanese_problems'))


@app.route('/teacher/feedback/save_bulk', methods=['POST'])
@login_required
@teacher_required
def save_feedback_bulk():
    """先生用：フィードバック一括保存"""
    data = request.json
    feedbacks = data.get('feedbacks', [])
    
    count = 0
    try:
        for item in feedbacks:
            task_type = item.get('type')
            assignment_id = item.get('id')
            feedback_text = item.get('feedback')
            
            assignment = None
            if task_type == 'quiz':
                assignment = JapaneseAssignment.query.get(assignment_id)
            elif task_type == 'flashcard':
                assignment = JapaneseFlashcardAssignment.query.get(assignment_id)
            elif task_type == 'writing':
                assignment = JapaneseWritingAssignment.query.get(assignment_id)
                
            if assignment:
                assignment.teacher_feedback = feedback_text
                count += 1
                
        db.session.commit()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})



# ============ 生徒用 日本語課題実施ルート ============

@app.route('/student/japanese/quiz/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_quiz_assignment(assignment_id):
    from datetime import datetime
    assignment = JapaneseAssignment.query.get_or_404(assignment_id)
    if assignment.student_id != current_user.id:
        flash('アクセス権がありません', 'error')
        return redirect(url_for('dashboard'))

    # フィードバックがあれば既読にする
    if assignment.teacher_feedback and not assignment.feedback_seen:
        assignment.feedback_seen = True
        db.session.commit()
        
    if request.method == 'POST':
        action = request.form.get('action')
        # クイズ回答ロジック（簡易版）
        if action == 'answer':
            selected_option = request.form.get('option')
            is_correct = (selected_option == assignment.quiz.correct_reading)
            
            if is_correct and not assignment.completed:
                assignment.completed = True
                assignment.completed_at = datetime.utcnow()
                assignment.is_correct = True
                db.session.commit()
                flash('正解です！完了しました！', 'success')
                
                # 次の未完了問題を探す（連続実施のため）
                # 同じ配信グループ（同じ分）の未完了問題を優先的に探す
                group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
                
                next_assignment = JapaneseAssignment.query.filter(
                    JapaneseAssignment.student_id == current_user.id,
                    JapaneseAssignment.completed == False,
                    JapaneseAssignment.id != assignment.id
                ).order_by(JapaneseAssignment.id).first()
                
                # 同じグループのものがあればそれを、なければどれでも古い順（ID順）
                if next_assignment:
                    # グループ内のものかチェック（厳密でなくてもいいが、近い時間のものを優先したいならここでフィルタしてもいい）
                    # 今回は単純に未完了があれば次へ、とする
                     flash('正解！次の問題に進みます。', 'success')
                     return redirect(url_for('student_quiz_assignment', assignment_id=next_assignment.id))
                
            elif not is_correct:
                flash('不正解です。もう一度挑戦しましょう。', 'error')
                
        elif action == 'complete': # 手動完了（予備）
            assignment.completed = True
            assignment.completed_at = datetime.utcnow()
            db.session.commit()
            flash('完了しました！', 'success')
            return redirect(url_for('dashboard'))
    
    import json
    import random
    options = [assignment.quiz.correct_reading]
    try:
        if assignment.quiz.wrong_readings:
            wrongs = json.loads(assignment.quiz.wrong_readings)
            options.extend(wrongs)
    except:
        pass
    random.shuffle(options)
    
    # 同じグループ（同じ配信時間）の課題リストを取得してナビゲーション情報を作成
    group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
    group_assignments = JapaneseAssignment.query.filter(
        JapaneseAssignment.student_id == current_user.id
    ).order_by(JapaneseAssignment.id).all()
    
    # 同じ分のものだけフィルタ
    same_group = [a for a in group_assignments if a.assigned_at.strftime('%Y-%m-%d %H:%M') == group_time_str]
    
    # 現在位置と前後のIDを計算
    current_index = next((i for i, a in enumerate(same_group) if a.id == assignment.id), 0)
    total_count = len(same_group)
    prev_id = same_group[current_index - 1].id if current_index > 0 else None
    next_id = same_group[current_index + 1].id if current_index < total_count - 1 else None
    
    nav_info = {
        'current': current_index + 1,
        'total': total_count,
        'prev_id': prev_id,
        'next_id': next_id,
        'group_items': same_group
    }
            
    return render_template('student_japanese_quiz.html', assignment=assignment, options=options, nav=nav_info)


@app.route('/student/japanese/flashcard/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_flashcard(assignment_id):
    from datetime import datetime
    assignment = JapaneseFlashcardAssignment.query.get_or_404(assignment_id)
    if assignment.student_id != current_user.id:
        flash('アクセス権がありません', 'error')
        return redirect(url_for('dashboard'))

    # フィードバックがあれば既読にする
    if assignment.teacher_feedback and not assignment.feedback_seen:
        assignment.feedback_seen = True
        db.session.commit()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'complete':
            assignment.completed = True
            assignment.completed_at = datetime.utcnow()
            db.session.commit()
            flash('フラッシュカード学習を完了しました！', 'success')
            
            # 次の未完了フラッシュカードを探す（同じグループ優先）
            group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
            
            # 同じ配信時間のものを優先
            all_pending = JapaneseFlashcardAssignment.query.filter(
                JapaneseFlashcardAssignment.student_id == current_user.id,
                JapaneseFlashcardAssignment.completed == False,
                JapaneseFlashcardAssignment.id != assignment.id
            ).order_by(JapaneseFlashcardAssignment.id).all()
            
            # 同じグループのものを探す
            same_group = [a for a in all_pending if a.assigned_at.strftime('%Y-%m-%d %H:%M') == group_time_str]
            
            if same_group:
                return redirect(url_for('student_flashcard', assignment_id=same_group[0].id))
            elif all_pending:
                # グループ外でも未完了があれば続ける（オプション）
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('dashboard'))

    # 同じグループ（同じ配信時間）の課題リストを取得してナビゲーション情報を作成
    group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
    group_assignments = JapaneseFlashcardAssignment.query.filter(
        JapaneseFlashcardAssignment.student_id == current_user.id
    ).order_by(JapaneseFlashcardAssignment.id).all()
    
    # 同じ分のものだけフィルタ
    same_group = [a for a in group_assignments if a.assigned_at.strftime('%Y-%m-%d %H:%M') == group_time_str]
    
    # 現在位置と前後のIDを計算
    current_index = next((i for i, a in enumerate(same_group) if a.id == assignment.id), 0)
    total_count = len(same_group)
    prev_id = same_group[current_index - 1].id if current_index > 0 else None
    next_id = same_group[current_index + 1].id if current_index < total_count - 1 else None
    
    nav_info = {
        'current': current_index + 1,
        'total': total_count,
        'prev_id': prev_id,
        'next_id': next_id,
        'group_items': same_group
    }

    return render_template('student_flashcard.html', assignment=assignment, nav=nav_info)


@app.route('/student/japanese/writing/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_writing(assignment_id):
    from datetime import datetime
    assignment = JapaneseWritingAssignment.query.get_or_404(assignment_id)
    if assignment.student_id != current_user.id:
        flash('アクセス権がありません', 'error')
        return redirect(url_for('dashboard'))

    # フィードバックがあれば既読にする
    if assignment.teacher_feedback and not assignment.feedback_seen:
        assignment.feedback_seen = True
        db.session.commit()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'complete':
            assignment.completed = True
            assignment.completed_at = datetime.utcnow()
            
            # 画像データの保存
            result_image = request.form.get('result_image')
            if result_image:
                assignment.result_image = result_image
                
            db.session.commit()
            flash('書き取り練習を完了しました！', 'success')
            
            # 次の未完了書き取りを探す（同じグループ優先）
            group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
            
            # 同じ配信時間のものを優先
            all_pending = JapaneseWritingAssignment.query.filter(
                JapaneseWritingAssignment.student_id == current_user.id,
                JapaneseWritingAssignment.completed == False,
                JapaneseWritingAssignment.id != assignment.id
            ).order_by(JapaneseWritingAssignment.id).all()
            
            # 同じグループのものを探す
            same_group = [a for a in all_pending if a.assigned_at.strftime('%Y-%m-%d %H:%M') == group_time_str]
            
            if same_group:
                return redirect(url_for('student_writing', assignment_id=same_group[0].id))
            elif all_pending:
                # グループ外でも未完了があれば続ける（オプション）
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('dashboard'))

    # 同じグループ（同じ配信時間）の課題リストを取得してナビゲーション情報を作成
    group_time_str = assignment.assigned_at.strftime('%Y-%m-%d %H:%M')
    group_assignments = JapaneseWritingAssignment.query.filter(
        JapaneseWritingAssignment.student_id == current_user.id
    ).order_by(JapaneseWritingAssignment.id).all()
    
    # 同じ分のものだけフィルタ
    same_group = [a for a in group_assignments if a.assigned_at.strftime('%Y-%m-%d %H:%M') == group_time_str]
    
    # 現在位置と前後のIDを計算
    current_index = next((i for i, a in enumerate(same_group) if a.id == assignment.id), 0)
    total_count = len(same_group)
    prev_id = same_group[current_index - 1].id if current_index > 0 else None
    next_id = same_group[current_index + 1].id if current_index < total_count - 1 else None
    
    nav_info = {
        'current': current_index + 1,
        'total': total_count,
        'prev_id': prev_id,
        'next_id': next_id,
        'group_items': same_group
    }

    return render_template('student_writing.html', assignment=assignment, nav=nav_info)



if __name__ == '__main__':
    init_db()
    print('\n=== 石川七夢講師専用学習アプリを起動します ===')
    print('アクセスURL: http://localhost:5000')
    print('============================================\n')
    app.run(debug=True, host='0.0.0.0', port=5000)
