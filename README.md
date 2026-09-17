# 📊 Slack 数値項目 月別集計ダッシュボード

Slackチャンネルに投稿された「ある項目（例: 売上、工数、件数など）」の数値を自動で抽出し、月毎に集計・グラフ化するWebアプリケーションです。

---

## 🚀 主な機能

1. **Slack API 直接連携**
   - Slack Bot Token (`xoxb-...`) を設定するだけで、パブリック/プライベートチャンネルからメッセージ履歴を自動取得。
2. **柔軟な数値抽出パーサー**
   - 「`売上: 50,000円`」「`工数：7.5h`」「`利益 = 3000`」など、コロンや全角・半角・カンマ区切り・単位（円、h、件など）に柔軟に対応。
   - 抽出ルールの正規表現カスタマイズ機能やプレビューテストも搭載。
3. **インタラクティブなダッシュボード**
   - **月別推移グラフ**: 月別合計（棒グラフ）と投稿件数（折れ線グラフ）の複合チャート。
   - **月別集計テーブル**: 年月、合計、平均、最小/最大、投稿件数を一覧表示。ワンクリックで **CSVダウンロード** 可能。
   - **メンバー別集計**: 誰がどれだけ貢献しているかの割合（円グラフ）と集計一覧。
   - **抽出元ログ閲覧**: 抽出された元メッセージ本文の確認と絞り込みフィルター。
4. **デモモード搭載**
   - Slackのトークンを発行する前でも、ダミーデータを使って即座に画面の動作を確認可能。

---

## 💻 起動方法

ターミナルで本ディレクトリ（`slack_aggregator`）に移動し、以下のコマンドを実行します。

```bash
cd /Users/muraten/Desktop/Tex/slack_aggregator
./run.sh
```

または直接 Streamlit で起動:

```bash
streamlit run app.py
```

ブラウザが自動で立ち上がり、`http://localhost:8501` でアプリが開きます。

---

## 🔑 Slack API のセットアップ手順 (Botトークンの取得)

Slackからデータを取得するには、以下の4ステップでSlack App（Bot）を準備します。

### ステップ 1: Slack App の新規作成
1. [Slack API: Your Apps](https://api.slack.com/apps) にアクセスします。
2. 右上の **「Create New App」** をクリックします。
3. **「From scratch」** を選択します。
4. **App Name**（例: `Data-Aggregator`）を入力し、対象の **Workspace** を選択して **「Create App」** をクリックします。

### ステップ 2: 必要な権限 (OAuth Scopes) の設定
1. 左側メニューの **「OAuth & Permissions」** をクリックします。
2. ページ下部の **「Scopes」** > **「Bot Token Scopes」** に進み、**「Add an OAuth Scope」** をクリックして以下を追加します:
   - `channels:history` （パブリックチャンネルの履歴閲覧）
   - `groups:history` （プライベートチャンネルの履歴閲覧）
   - `channels:read` （パブリックチャンネル一覧の取得）
   - `groups:read` （プライベートチャンネル一覧の取得）
   - `users:read` （投稿者名・表示名の解決）

### ステップ 3: ワークスペースへのインストールとトークン取得
1. 同じページの最上部にある **「Install to Workspace」** ボタンをクリックします。
2. 権限の許可画面が出るので **「許可する」** をクリックします。
3. 発行された **「Bot User OAuth Token」** （`xoxb-` から始まる文字列）をコピーします。

### ステップ 4: 対象チャンネルへ Bot を招待
1. Slackアプリを開き、集計したいチャンネルに移動します。
2. メッセージ入力欄で以下のように入力して送信します:
   ```text
   /invite @アプリ名
   ```
   （※またはチャンネル詳細の「インテグレーション」>「アプリを追加」から追加します）

---

## ⚙️ 環境変数の設定 (オプション)

起動時に毎回トークンを入力するのが面倒な場合は、`.env` ファイルを作成しておくと自動入力されます。

```bash
cp .env.example .env
```

`.env` 内を編集:
```env
SLACK_BOT_TOKEN=xoxb-あなたのトークン
SLACK_DEFAULT_CHANNEL=C0123456789
SLACK_DEFAULT_ITEM=売上
```

---

## 📁 ディレクトリ構成

- [app.py](file:///Users/muraten/Desktop/Tex/slack_aggregator/app.py): Streamlit Webダッシュボード本体
- [parser.py](file:///Users/muraten/Desktop/Tex/slack_aggregator/parser.py): メッセージから「項目名: 数値」を抽出するロジック
- [slack_client.py](file:///Users/muraten/Desktop/Tex/slack_aggregator/slack_client.py): Slack API 通信モジュール（requests使用）
- [sample_data.py](file:///Users/muraten/Desktop/Tex/slack_aggregator/sample_data.py): デモ用テストデータ生成モジュール
- [run.sh](file:///Users/muraten/Desktop/Tex/slack_aggregator/run.sh): ワンクリック起動スクリプト
- [requirements.txt](file:///Users/muraten/Desktop/Tex/slack_aggregator/requirements.txt): 依存パッケージ一覧
