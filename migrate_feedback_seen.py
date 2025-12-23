from app import app, db
import sqlite3

def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    try:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        print(f"Added {column_name} to {table_name}")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e) or "no such table" in str(e):
            print(f"Column {column_name} might already exist in {table_name} or table missing: {e}")
        else:
            print(f"Error adding {column_name} to {table_name}: {e}")

with app.app_context():
    # SQLiteファイルのパスを取得
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    print(f"Database path: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 各テーブルにカラム追加
    add_column_if_not_exists(cursor, 'japanese_assignments', 'feedback_seen', 'BOOLEAN DEFAULT 0')
    add_column_if_not_exists(cursor, 'japanese_flashcard_assignments', 'feedback_seen', 'BOOLEAN DEFAULT 0')
    add_column_if_not_exists(cursor, 'japanese_writing_assignments', 'feedback_seen', 'BOOLEAN DEFAULT 0')
    
    conn.commit()
    conn.close()
    print("Migration completed.")
