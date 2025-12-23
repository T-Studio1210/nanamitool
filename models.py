# 石川七夢講師専用学習アプリ - データベースモデル

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """ユーザーモデル（先生/生徒）"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # 'teacher' or 'student'
    fcm_token = db.Column(db.String(500), nullable=True)  # Firebase Cloud Messaging トークン
    is_chinese_student = db.Column(db.Boolean, default=False)  # 中国人生徒フラグ（日本語学習アクセス可能）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # リレーション
    problems = db.relationship('Problem', backref='author', lazy='dynamic')
    answers = db.relationship('Answer', backref='student', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_teacher(self):
        return self.role == 'teacher'


# 問題と生徒の関連テーブル（多対多）
problem_assignments = db.Table('problem_assignments',
    db.Column('problem_id', db.Integer, db.ForeignKey('problems.id'), primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)


class Problem(db.Model):
    """問題モデル"""
    __tablename__ = 'problems'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)  # リッチテキストHTML
    problem_type = db.Column(db.String(20), default='text')  # text, choice
    choices_json = db.Column(db.Text, nullable=True)  # 選択肢JSON
    correct_choice = db.Column(db.Integer, nullable=True)  # 正解インデックス
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    deadline = db.Column(db.DateTime, nullable=True)  # 提出期限（任意）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーション
    answers = db.relationship('Answer', backref='problem', lazy='dynamic', cascade='all, delete-orphan')
    assigned_students = db.relationship('User', secondary=problem_assignments, 
                                         backref=db.backref('assigned_problems', lazy='dynamic'))
    
    def is_overdue(self):
        """提出期限が過ぎているかチェック"""
        if self.deadline:
            return datetime.utcnow() > self.deadline
        return False
    
    def get_choices(self):
        """選択肢リストを取得"""
        if self.choices_json:
            import json
            return json.loads(self.choices_json)
        return []


class Answer(db.Model):
    """回答モデル"""
    __tablename__ = 'answers'
    
    id = db.Column(db.Integer, primary_key=True)
    problem_id = db.Column(db.Integer, db.ForeignKey('problems.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # 生徒の回答HTML
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーション
    feedback = db.relationship('Feedback', backref='answer', uselist=False, cascade='all, delete-orphan')


class Feedback(db.Model):
    """フィードバックモデル"""
    __tablename__ = 'feedbacks'
    
    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answers.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)  # フィードバックHTML
    score = db.Column(db.Integer, nullable=True)  # 任意の点数（0-100）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 連絡事項と生徒の関連テーブル（多対多）
announcement_recipients = db.Table('announcement_recipients',
    db.Column('announcement_id', db.Integer, db.ForeignKey('announcements.id'), primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)


class Announcement(db.Model):
    """連絡事項モデル"""
    __tablename__ = 'announcements'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)  # 表示/非表示
    is_global = db.Column(db.Boolean, default=False)  # 全員向けかどうか
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # リレーション
    author = db.relationship('User', backref='announcements')
    recipients = db.relationship('User', secondary=announcement_recipients,
                                  backref=db.backref('received_announcements', lazy='dynamic'))
    reactions = db.relationship('AnnouncementReaction', backref='announcement', lazy='dynamic', cascade='all, delete-orphan')


class AnnouncementReaction(db.Model):
    """連絡事項リアクションモデル"""
    __tablename__ = 'announcement_reactions'
    
    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey('announcements.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reaction_type = db.Column(db.String(20), nullable=False)  # 'seen', 'like', 'ok', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # リレーション
    student = db.relationship('User', backref='announcement_reactions')
    
    # ユニーク制約：1人のユーザーは1つの連絡に1種類のリアクションのみ
    __table_args__ = (db.UniqueConstraint('announcement_id', 'student_id', 'reaction_type'),)


class ProblemComponent(db.Model):
    """問題コンポーネントモデル（説明文やウィジェットの再利用可能なパーツ）"""
    __tablename__ = 'problem_components'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)  # HTMLコンテンツ
    component_type = db.Column(db.String(50), nullable=False)  # text, widget-text, widget-choice, widget-checkbox
    description = db.Column(db.Text, nullable=True) # ウィジェットの説明文（検索用・分離保存用）
    choices_json = db.Column(db.Text, nullable=True) # 選択肢データ（検索用・分離保存用）
    content_hash = db.Column(db.String(64), nullable=False, index=True) # 重複チェック用ハッシュ (SHA256)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ScheduledNotification(db.Model):
    """予約通知モデル"""
    __tablename__ = 'scheduled_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.String(50), nullable=False)  # 'announcement', 'problem', 'feedback'
    target_id = db.Column(db.Integer, nullable=False)  # 対象のID（announcement_id, problem_id, feedback_id）
    scheduled_at = db.Column(db.DateTime, nullable=False)  # 配信予定時刻
    is_sent = db.Column(db.Boolean, default=False)  # 送信済みかどうか
    sent_at = db.Column(db.DateTime, nullable=True)  # 実際に送信した時刻
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================
# 日本語学習モデル
# ============================================

class JapaneseQuiz(db.Model):
    """日本語熟語クイズモデル"""
    __tablename__ = 'japanese_quizzes'
    
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(50), nullable=False)  # 熟語（漢字）
    correct_reading = db.Column(db.String(50), nullable=False)  # 正しい読み方
    wrong_readings = db.Column(db.Text, nullable=False)  # 間違い選択肢（JSON配列）
    meaning_chinese = db.Column(db.String(200), nullable=True)  # 中国語の意味
    example = db.Column(db.String(300), nullable=True)  # 例文
    category = db.Column(db.String(20), default='general')  # カテゴリ
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_wrong_readings(self):
        """間違い選択肢をリストとして取得"""
        import json
        return json.loads(self.wrong_readings) if self.wrong_readings else []


class JapaneseAnswer(db.Model):
    """日本語学習回答履歴モデル"""
    __tablename__ = 'japanese_answers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('japanese_quizzes.id'), nullable=True)
    quiz_word = db.Column(db.String(50), nullable=False)  # 問題の熟語
    is_correct = db.Column(db.Boolean, nullable=False)  # 正解かどうか
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # リレーション
    user = db.relationship('User', backref=db.backref('japanese_answers', lazy='dynamic'))
    quiz = db.relationship('JapaneseQuiz', backref='answers')


# 日本語問題配信用の多対多テーブル
japanese_quiz_assignments = db.Table('japanese_quiz_assignments',
    db.Column('quiz_id', db.Integer, db.ForeignKey('japanese_quizzes.id'), primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow),
    db.Column('completed', db.Boolean, default=False)
)


class JapaneseAssignment(db.Model):
    """日本語問題配信モデル"""
    __tablename__ = 'japanese_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('japanese_quizzes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=True)
    student_comment = db.Column(db.Text, nullable=True)  # 生徒からのコメント
    teacher_feedback = db.Column(db.Text, nullable=True)  # 先生からのフィードバック
    feedback_seen = db.Column(db.Boolean, default=False)  # フィードバック既読フラグ

    
    # リレーション
    quiz = db.relationship('JapaneseQuiz', backref=db.backref('assignments', cascade='all, delete-orphan'))
    student = db.relationship('User', backref=db.backref('japanese_assignments', lazy='dynamic'))


class JapaneseFlashcard(db.Model):
    """フラッシュカードモデル"""
    __tablename__ = 'japanese_flashcards'
    
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(50), nullable=False)  # 漢字/熟語
    reading = db.Column(db.String(50), nullable=False)  # 読み方
    meaning = db.Column(db.String(200), nullable=False)  # 中国語の意味
    example = db.Column(db.String(300), nullable=True)  # 例文
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JapaneseFlashcardAssignment(db.Model):
    """フラッシュカード配信モデル"""
    __tablename__ = 'japanese_flashcard_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    flashcard_id = db.Column(db.Integer, db.ForeignKey('japanese_flashcards.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    student_comment = db.Column(db.Text, nullable=True)  # 生徒からのコメント
    teacher_feedback = db.Column(db.Text, nullable=True)  # 先生からのフィードバック
    feedback_seen = db.Column(db.Boolean, default=False)  # フィードバック既読フラグ

    
    # リレーション
    flashcard = db.relationship('JapaneseFlashcard', backref=db.backref('assignments', cascade='all, delete-orphan'))
    student = db.relationship('User', backref=db.backref('japanese_flashcard_assignments', lazy='dynamic'))


class JapaneseWriting(db.Model):
    """書き取り練習モデル"""
    __tablename__ = 'japanese_writings'
    
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(10), nullable=False)  # 漢字（1-2文字）
    reading = db.Column(db.String(50), nullable=False)  # 読み方
    meaning = db.Column(db.String(200), nullable=False)  # 中国語の意味
    example = db.Column(db.String(300), nullable=True)  # 例文
    stroke_count = db.Column(db.Integer, nullable=True)  # 画数
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JapaneseWritingAssignment(db.Model):
    """書き取り練習配信モデル"""
    __tablename__ = 'japanese_writing_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    writing_id = db.Column(db.Integer, db.ForeignKey('japanese_writings.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    result_image = db.Column(db.Text, nullable=True)  # 書き取り結果画像 (Base64)
    student_comment = db.Column(db.Text, nullable=True)  # 生徒からのコメント
    teacher_feedback = db.Column(db.Text, nullable=True)  # 先生からのフィードバック
    feedback_seen = db.Column(db.Boolean, default=False)  # フィードバック既読フラグ

    
    # リレーション
    writing = db.relationship('JapaneseWriting', backref=db.backref('assignments', cascade='all, delete-orphan'))
    student = db.relationship('User', backref=db.backref('japanese_writing_assignments', lazy='dynamic'))


class GradeKanji(db.Model):
    """学年別漢字マスターデータ"""
    __tablename__ = 'grade_kanji'
    
    id = db.Column(db.Integer, primary_key=True)
    kanji = db.Column(db.String(1), nullable=False, unique=True)  # 漢字1文字
    grade = db.Column(db.String(20), nullable=False, index=True)  # 'grade1' ~ 'grade6', 'junior_high'
    on_reading = db.Column(db.String(100), nullable=True)  # 音読み（カンマ区切り）
    kun_reading = db.Column(db.String(100), nullable=True)  # 訓読み（カンマ区切り）
    stroke_count = db.Column(db.Integer, nullable=True)  # 画数
    meaning = db.Column(db.String(200), nullable=True)  # 意味
    
    @staticmethod
    def get_grades():
        """利用可能な学年リストを返す"""
        return [
            ('grade1', '小学1年生'),
            ('grade2', '小学2年生'),
            ('grade3', '小学3年生'),
            ('grade4', '小学4年生'),
            ('grade5', '小学5年生'),
            ('grade6', '小学6年生'),
            ('junior_high', '中学校'),
        ]
