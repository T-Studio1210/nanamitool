import sqlite3
import os

# Check both possible locations
db_paths = [
    'nanami_learning.db',
    'instance/nanami_learning.db'
]

# Tables to update (with correct names from models.py)
target_tables = [
    'japanese_assignments',           # JapaneseAssignment
    'japanese_flashcard_assignments', # JapaneseFlashcardAssignment
    'japanese_writing_assignments'    # JapaneseWritingAssignment
]

for db_path in db_paths:
    if not os.path.exists(db_path):
        print(f"{db_path}: NOT FOUND")
        continue
    
    print(f"\n=== Checking {db_path} ===")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # List all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables found: {len(tables)}")
    
    for table in target_tables:
        if table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'feedback_seen' in columns:
                print(f"  {table}: feedback_seen EXISTS")
            else:
                print(f"  {table}: feedback_seen MISSING - adding...")
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN feedback_seen BOOLEAN DEFAULT 0")
                    print(f"  {table}: Added successfully!")
                except Exception as e:
                    print(f"  {table}: Error - {e}")
        else:
            print(f"  {table}: TABLE NOT FOUND in this DB")
    
    conn.commit()
    conn.close()

print("\n=== Migration Complete ===")
