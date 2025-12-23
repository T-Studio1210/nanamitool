from app import app, db
from sqlalchemy import text

def update_db():
    with app.app_context():
        # JapaneseAssignment
        try:
            db.session.execute(text("ALTER TABLE japanese_assignments ADD COLUMN student_comment TEXT"))
            print("Added student_comment to japanese_assignments")
        except Exception as e:
            print(f"Skipped student_comment for japanese_assignments: {e}")

        try:
            db.session.execute(text("ALTER TABLE japanese_assignments ADD COLUMN teacher_feedback TEXT"))
            print("Added teacher_feedback to japanese_assignments")
        except Exception as e:
            print(f"Skipped teacher_feedback for japanese_assignments: {e}")

        # JapaneseFlashcardAssignment
        try:
            db.session.execute(text("ALTER TABLE japanese_flashcard_assignments ADD COLUMN student_comment TEXT"))
            print("Added student_comment to japanese_flashcard_assignments")
        except Exception as e:
            print(f"Skipped student_comment for japanese_flashcard_assignments: {e}")
            
        try:
            db.session.execute(text("ALTER TABLE japanese_flashcard_assignments ADD COLUMN teacher_feedback TEXT"))
            print("Added teacher_feedback to japanese_flashcard_assignments")
        except Exception as e:
            print(f"Skipped teacher_feedback for japanese_flashcard_assignments: {e}")

        # JapaneseWritingAssignment
        try:
            db.session.execute(text("ALTER TABLE japanese_writing_assignments ADD COLUMN student_comment TEXT"))
            print("Added student_comment to japanese_writing_assignments")
        except Exception as e:
            print(f"Skipped student_comment for japanese_writing_assignments: {e}")
            
        try:
            db.session.execute(text("ALTER TABLE japanese_writing_assignments ADD COLUMN teacher_feedback TEXT"))
            print("Added teacher_feedback to japanese_writing_assignments")
        except Exception as e:
            print(f"Skipped teacher_feedback for japanese_writing_assignments: {e}")

        try:
            db.session.execute(text("ALTER TABLE japanese_writing_assignments ADD COLUMN result_image TEXT"))
            print("Added result_image to japanese_writing_assignments")
        except Exception as e:
            print(f"Skipped result_image for japanese_writing_assignments: {e}")
            
        db.session.commit()
        print("Done.")

if __name__ == "__main__":
    update_db()
