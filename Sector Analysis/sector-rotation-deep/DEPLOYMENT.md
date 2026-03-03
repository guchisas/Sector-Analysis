# デプロイ手順書: Japan Stock Sector Rotation Deep Dive

## 1. 事前準備

### 1.1 銘柄リストの生成（初回のみ）

デプロイ前に、最新の銘柄リストを生成してください：

```bash
cd sector-rotation-deep
pip install -r requirements.txt
python scripts/update_stock_list.py
```

これにより `utils/constants.py` が最新の売買代金上位600銘柄で更新されます。

> ⚠️ **重要**: `update_stock_list.py` はJPXからデータを取得するため、ローカル環境で実行してください。クラウド環境では実行しません。

### 1.2 Gemini API キーの取得

1. [Google AI Studio](https://aistudio.google.com/) にアクセス
2. APIキーを作成
3. `.env` ファイルにキーを記入：
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

---

## 2. GitHub リポジトリの作成

### 2.1 リポジトリ作成

1. [GitHub](https://github.com) で新しいリポジトリを作成
2. リポジトリ名: `sector-rotation-deep`（任意）
3. Public/Private: お好みで設定

### 2.2 `.gitignore` の作成

```gitignore
# 環境ファイル
.env
__pycache__/
*.pyc

# データベース
data/*.db

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

### 2.3 プッシュ

```bash
cd sector-rotation-deep
git init
git add .
git commit -m "Initial commit: Sector Rotation Deep Dive"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/sector-rotation-deep.git
git push -u origin main
```

> ⚠️ **重要**: `utils/constants.py` が生成済みであることを確認してからプッシュしてください。

---

## 3. Streamlit Community Cloud へのデプロイ

### 3.1 アカウント作成

1. [Streamlit Community Cloud](https://share.streamlit.io/) にアクセス
2. GitHubアカウントでサインイン

### 3.2 アプリのデプロイ

1. 「New app」をクリック
2. 以下を設定：
   - **Repository**: `YOUR_USERNAME/sector-rotation-deep`
   - **Branch**: `main`
   - **Main file path**: `app.py`
3. 「Deploy!」をクリック

### 3.3 Secrets 設定（GEMINI_API_KEY）

1. デプロイ画面 or アプリ管理画面で「Settings」→「Secrets」
2. 以下の内容を記入：

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
```

3. 「Save」で保存

---

## 4. 運用メモ

### 銘柄リストの更新

定期的（月1回程度推奨）にローカル環境で以下を実行し、GitHubにプッシュしてください：

```bash
python scripts/update_stock_list.py
git add utils/constants.py
git commit -m "Update stock list"
git push
```

Streamlit Cloud は自動的に再デプロイされます。

### データベースについて

- SQLiteファイル (`data/sector_rotation.db`) はクラウド環境では**永続化されません**
- アプリ再起動ごとに「データを最新化」ボタンでデータを取得してください
- ローカル環境では永続化されます

### トラブルシューティング

| 問題 | 対処法 |
|------|--------|
| アプリ起動時にエラー | `requirements.txt` の依存関係を確認 |
| データ取得が遅い | バッチサイズを調整（`BATCH_SIZE` in `market_data_fetcher.py`） |
| Gemini APIエラー | Secrets設定を確認。APIキーが正しいか確認 |
| スマホで表示が崩れる | CSS対応済み。ブラウザキャッシュをクリア |
