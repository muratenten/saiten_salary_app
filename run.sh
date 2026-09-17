#!/bin/bash
# Slack 月別集計ダッシュボード 起動スクリプト

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "========================================="
echo "📊 Slack 月別集計ダッシュボード を起動します"
echo "========================================="

# 既存のトンネルプロセスがあれば整理
pkill -f "cloudflared tunnel --url http://localhost:8501" 2>/dev/null || true

echo "🌐 外出先・スマホ用アクセスURLを準備中..."
cloudflared tunnel --url http://localhost:8501 > cloudflare.log 2>&1 &
TUNNEL_PID=$!

# URLが取得できるまで少し待機
sleep 4
TUNNEL_URL=$(grep -o 'https://[-a-zA-Z0-9@:%._\+~#=]*\.trycloudflare\.com' cloudflare.log | head -n 1)

if [ -n "$TUNNEL_URL" ]; then
    echo "---------------------------------------------------------"
    echo "📱 【スマホ・外出先用アクセスURL】"
    echo "   $TUNNEL_URL"
    echo "---------------------------------------------------------"
    curl -s "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=$TUNNEL_URL" -o "$HOME/Desktop/スマホ用QRコード.png" 2>/dev/null
    open "$HOME/Desktop/スマホ用QRコード.png" 2>/dev/null || true
fi

# streamlit コマンドの起動
if ! command -v streamlit &> /dev/null; then
    echo "⚠️ streamlit コマンドが見つかりませんでした。python3 -m streamlit で起動を試みます..."
    python3 -m streamlit run app.py
else
    streamlit run app.py
fi

kill $TUNNEL_PID 2>/dev/null || true

