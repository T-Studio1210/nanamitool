# GitHubとRenderへのデプロイ手順

## 📋 事前準備

1. **GitHubアカウント作成**: https://github.com で無料アカウントを作成
2. **Renderアカウント作成**: https://render.com で無料アカウントを作成（GitHubアカウントでサインアップ推奨）
3. **Gitのインストール**: https://git-scm.com からダウンロード・インストール

---

## 🔧 Step 1: GitHubにリポジトリを作成

1. GitHub (https://github.com) にログイン
2. 右上の「+」→「New repository」をクリック
3. 以下を入力：
   - **Repository name**: `nanamitool`
   - **Description**: 石川七夢講師専用学習アプリ（任意）
   - **Public / Private**: お好みで選択
4. 「Create repository」をクリック

---

## 📤 Step 2: コードをGitHubにプッシュ

PowerShellまたはコマンドプロンプトで以下を実行：

```bash
# プロジェクトディレクトリに移動
cd "C:\Users\Tstud\OneDrive\大学授業\nanamitool"

# Gitリポジトリを初期化（初回のみ）
git init

# すべてのファイルをステージング
git add .

# コミット
git commit -m "Initial commit - nanamitool"

# mainブランチに設定
git branch -M main

# GitHubリポジトリをリモートに追加（URLはあなたのリポジトリに置き換え）
git remote add origin https://github.com/あなたのユーザー名/nanamitool.git

# プッシュ
git push -u origin main
```

> ⚠️ 初回プッシュ時にGitHubへのログインが求められます。

---

## 🚀 Step 3: Renderでデプロイ

### 方法A: render.yamlを使用（推奨）

1. https://render.com にログイン
2. 「New」→「Blueprint」をクリック
3. GitHubリポジトリ `nanamitool` を選択
4. 「Connect」をクリック
5. Renderが `render.yaml` を自動検出してサービスを作成
6. 「Apply」をクリック

### 方法B: 手動でWeb Serviceを作成

1. https://render.com にログイン
2. 「New」→「Web Service」をクリック
3. GitHubリポジトリ `nanamitool` を選択
4. 以下を設定：
   - **Name**: nanamitool
   - **Runtime**: Python 3
   - **Build Command**: `./build.sh`
   - **Start Command**: `gunicorn app:app`
5. 「Create Web Service」をクリック

### データベースの作成（方法Bの場合）

1. 「New」→「PostgreSQL」をクリック
2. **Name**: nanamitool-db
3. 「Create Database」をクリック
4. 作成後、「Connect」タブから「Internal Database URL」をコピー
5. Web Serviceの「Environment」に以下を追加：
   - **Key**: `DATABASE_URL`
   - **Value**: コピーしたURL

---

## ⚙️ Step 4: 環境変数の設定

Renderダッシュボードで以下の環境変数を設定：

| Key | Value | 説明 |
|-----|-------|------|
| `SECRET_KEY` | （自動生成または独自の値） | セッション暗号化キー |
| `DATABASE_URL` | （PostgreSQLから取得） | データベース接続URL |
| `GROQ_API_KEY` | あなたのAPIキー | Groq AI用（使用している場合） |

### Firebase通知を使用する場合

Firebase認証情報は環境変数で設定する必要があります。
`firebase-service-account.json` の内容を環境変数として設定：

1. Renderダッシュボード→Environment
2. 新しい環境変数を追加：
   - **Key**: `FIREBASE_CREDENTIALS`
   - **Value**: JSONファイルの内容（1行に圧縮）

※ app.pyでFirebase初期化部分の修正が必要になる場合があります。

---

## ✅ Step 5: デプロイ確認

1. Renderダッシュボードで「Logs」を確認
2. デプロイ完了後、表示されるURLにアクセス
3. アプリが正常に動作することを確認

---

## 🔄 更新方法

コードを更新した場合：

```bash
git add .
git commit -m "変更内容の説明"
git push
```

Renderは自動的に新しいコードを検出してデプロイします。

---

## ⚠️ 注意事項

1. **無料プランの制限**: Renderの無料プランでは、15分間アクセスがないとスリープします
2. **データベース**: 無料PostgreSQLは90日後に削除されます（有料プランで回避可能）
3. **機密情報**: `firebase-service-account.json` はGitHubにアップロードしないでください（.gitignoreで除外済み）

---

## 📞 トラブルシューティング

### ビルドエラーの場合
- Renderの「Logs」でエラー内容を確認
- `requirements.txt` のパッケージが正しいか確認

### データベース接続エラーの場合
- `DATABASE_URL` 環境変数が設定されているか確認
- PostgreSQLが作成されているか確認

---

何か問題があればお知らせください！😊
