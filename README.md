# 認証bot

Discord ボタン/スラッシュコマンドでロール付与をするシンプルなボットです。
Railway にデプロイして常時稼働させる手順を示します。

## 必要ファイル
- main.py
- requirements.txt
- Procfile (任意)
- .env.template

## ローカルでの動作確認
1. .env を作成して TOKEN を設定
2. python -m pip install -r requirements.txt
3. python main.py

## Discord Developer Portal 設定
- Bot の Privileged Intents（SERVER MEMBERS INTENT）を ON にしてください（メンバーのロール取得に必要）。
- Bot をサーバーに招待する際には applications.commands と bot のスコープを追加。

## GitHub に push
1. git init
2. git add .
3. git commit -m "Initial commit"
4. GitHub でリポジトリ `認証bot` を作成
5. git remote add origin <your-repo-url>
6. git push -u origin main

## Railway にデプロイ
1. Railway で新しいプロジェクトを作成 -> 「Deploy from GitHub」から先ほどのリポジトリを選択
2. Settings で Environment Variables を追加
   - TOKEN = (Discord Bot Token)
   - 必要なら GUILD_ID = (テスト用ギルド ID)
3. Start Command を `python main.py` に設定（または Procfile を使用）
4. デプロイを開始

## メモ
- `認証済み` や `技術班` ロールはサーバー側で事前に作成してください。
- Bot にロール付与権限（Manage Roles）と、付与対象のロールの上にボットのロールが来るようにしてください。