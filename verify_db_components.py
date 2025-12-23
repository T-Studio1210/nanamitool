from app import app, db, ProblemComponent, save_components_from_html

def verify():
    with app.app_context():
        # テーブル作成（念のため）
        db.create_all()
        
        print("--- Testing Component Saving Logic ---")
        
        # テスト用HTML (create_problem.htmlで生成されるようなもの)
        # 1. テキストブロック
        # 2. 記述式ウィジェット
        # 3. 選択式ウィジェット
        
        html_content = """
        <div class="block-text">ここは共通の説明文です。</div>
        
        <div class="block-widget">
            <div class="question-widget" data-widget-type="text">
                <div class="widget-header">✏️ 記述回答欄</div>
                <div class="widget-description">詳細を記述してください。</div>
            </div>
        </div>
        
        <div class="block-widget">
            <div class="question-widget" data-widget-type="choice" data-choices='["A", "B", "C"]'>
                <div class="widget-header">🔴 選択回答欄 (単一)</div>
                 <div class="widget-description">正しいものを選びなさい。</div>
            </div>
        </div>
        """
        
        print("Saving components from dummy HTML...")
        save_components_from_html(html_content)
        
        print("\n--- Verifying Database Content ---")
        try:
            count = ProblemComponent.query.count()
            print(f"Total components: {count}")
            for c in ProblemComponent.query.order_by(ProblemComponent.id.desc()).limit(10).all():
                print(f"[{c.id}] Type: {c.component_type} | Hash: {c.content_hash[:10]}...")
                if c.description:
                    print(f"  Desc: {c.description.replace('\\n', ' ')}")
                if c.choices_json:
                    print(f"  Choices: {c.choices_json}")
                print("-" * 20)
        except Exception as e:
            print(f"Error reading DB: {e}")

if __name__ == "__main__":
    verify()
