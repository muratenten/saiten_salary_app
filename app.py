"""
Slack 振り分け数値 月別集計 & 給料計算アプリ (マルチユーザー・クラウド対応版)
- 社員番号・名前を入力するだけで誰の給料でも自動集計（方法A対応）
- Streamlit Cloud (24時間常時稼働) & ローカル起動 両対応
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from parser import parse_search_results_dump, parse_slack_message
from slack_client import SlackClient, SlackAPIError
from sample_data import generate_sample_distribution_messages

load_dotenv()

# 日本時間（JST = UTC+9）のタイムゾーン定義
JST = timezone(timedelta(hours=9))

def clean_display_name(raw_name: str) -> str:
    """'948919 村本拓海 948919 村本拓海' などの重複を '948919 村本拓海' に整形"""
    if not raw_name:
        return ""
    words = raw_name.split()
    seen = set()
    cleaned = []
    for w in words:
        if w not in seen:
            seen.add(w)
            cleaned.append(w)
    return " ".join(cleaned)

st.set_page_config(
    page_title="振り分け給料計算",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="collapsed"
)

BASE_DIR = os.path.dirname(__file__)
CREDS_FILE = os.path.join(BASE_DIR, "credentials.json")
USERS_FILE = os.path.join(BASE_DIR, "workspace_users.json")
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")
LEGACY_CACHE_FILE = os.path.join(BASE_DIR, "messages_cache.json")
LEGACY_RATES_FILE = os.path.join(BASE_DIR, "rates_cache.json")

os.makedirs(USER_DATA_DIR, exist_ok=True)


def format_japanese_month(ym_str: str) -> str:
    """'2026-08' -> '2026年8月'"""
    try:
        parts = str(ym_str).split("-")
        if len(parts) >= 2:
            return f"{int(parts[0])}年{int(parts[1])}月"
    except Exception:
        pass
    return str(ym_str)


def load_credentials() -> dict:
    """Streamlit Secrets または ローカル credentials.json から認証情報を取得"""
    # 1. Streamlit Secrets (クラウドデプロイ用)
    try:
        if hasattr(st, "secrets"):
            if "SLACK_TOKEN" in st.secrets:
                return {
                    "token": st.secrets["SLACK_TOKEN"],
                    "cookie_d": st.secrets.get("SLACK_COOKIE_D", ""),
                    "channel_id": st.secrets.get("SLACK_CHANNEL_ID", "C012PFS70JH")
                }
    except Exception:
        pass

    # 2. 環境変数
    env_token = os.getenv("SLACK_TOKEN")
    if env_token:
        return {
            "token": env_token,
            "cookie_d": os.getenv("SLACK_COOKIE_D", ""),
            "channel_id": os.getenv("SLACK_CHANNEL_ID", "C012PFS70JH")
        }

    # 3. ローカルファイル
    if os.path.exists(CREDS_FILE):
        try:
            with open(CREDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_credentials(creds: dict):
    try:
        with open(CREDS_FILE, "w", encoding="utf-8") as f:
            json.dump(creds, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_workspace_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def find_user_by_keyword(kw: str):
    """社員番号または名前から Slack User ID と 氏名 を特定する"""
    kw = (kw or "").strip()
    if not kw:
        return None, None
    users = load_workspace_users()

    # 1. 社員番号が先頭に一致するもの（例: "948919", "960820"）
    for uid, name in users.items():
        if name.startswith(kw) or f" {kw} " in f" {name} ":
            return uid, name

    # 2. 完全一致または部分一致（名前など）
    for uid, name in users.items():
        if kw in name or kw.lower() == uid.lower():
            return uid, name

    return None, None


def get_user_storage_path(user_key: str, prefix: str) -> str:
    safe_key = re.sub(r'[^a-zA-Z0-9_-]', '_', user_key)
    return os.path.join(USER_DATA_DIR, f"{prefix}_{safe_key}.json")


def load_user_rates(user_key: str) -> dict:
    fpath = get_user_storage_path(user_key, "rates")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # レガシー移行
    if user_key in ["948919", "U0BJSQ9362G"] and os.path.exists(LEGACY_RATES_FILE):
        try:
            with open(LEGACY_RATES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_user_rates(user_key: str, rates: dict):
    fpath = get_user_storage_path(user_key, "rates")
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(rates, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def make_initial_demo_records():
    demo_msgs = generate_sample_distribution_messages(
        target_name="テスト太郎",
        target_id="123456",
        count=35
    )
    records = []
    for m in demo_msgs:
        dt = datetime.fromtimestamp(float(m["ts"]), tz=JST)
        items = parse_slack_message(m["text"], mode="person_line", person_keywords=["123456", "テスト太郎"])
        for it in items:
            records.append({
                "date": dt.strftime("%Y-%m-%d"),
                "year_month": dt.strftime("%Y-%m"),
                "target_value": it["value"],
                "count_value": it.get("count_value"),
                "matched_line": it["matched_text"],
                "is_demo": True
            })
    return records


def load_user_records(user_key: str) -> list:
    fpath = get_user_storage_path(user_key, "records")
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    # 村本さんのレガシー移行
    if user_key in ["948919", "U0BJSQ9362G"] and os.path.exists(LEGACY_CACHE_FILE):
        try:
            with open(LEGACY_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    save_user_records(user_key, data)
                    return data
        except Exception:
            pass
    return []


def save_user_records(user_key: str, records: list):
    fpath = get_user_storage_path(user_key, "records")
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def get_tunnel_url():
    log_path = os.path.join(BASE_DIR, "cloudflare.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                m = re.findall(r'https://[-a-zA-Z0-9@:%._\+~#=]*\.trycloudflare\.com', content)
                if m:
                    return m[-1]
        except Exception:
            pass
    return None


def extract_credentials_from_curl(curl_text: str):
    token = None
    t_match = re.search(r'Bearer\s+(xox[a-z]-[0-9a-zA-Z-]+)', curl_text)
    if not t_match:
        t_match = re.search(r'token=(xox[a-z]-[0-9a-zA-Z-]+)', curl_text)
    if not t_match:
        t_match = re.search(r'(xoxc-[0-9a-zA-Z-]+)', curl_text)
    if t_match:
        token = t_match.group(1)

    cookie_d = None
    c_header = re.search(r"-H\s+['\"].*?cookie:.*?['\"]", curl_text, re.IGNORECASE)
    if c_header:
        m = re.search(r'(?:^|[;\s])d=([^;\'\"\s]+)', c_header.group(0))
        if m:
            cookie_d = m.group(1)
    if not cookie_d:
        m = re.search(r'(xoxd-[0-9a-zA-Z%_-]+)', curl_text)
        if m:
            cookie_d = m.group(1)

    return token, cookie_d


# CSS スタイル設定
st.markdown("""
<style>
    [data-testid="collapsedControl"] { display: none; }
    section[data-testid="stSidebar"] { display: none; }
    
    .big-stat-box {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        padding: 24px 20px;
        border-radius: 16px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.12);
        margin: 15px 0 25px 0;
    }
    .big-stat-title {
        font-size: 1.15rem;
        font-weight: 600;
        opacity: 0.95;
        letter-spacing: 0.5px;
    }
    .big-stat-number {
        font-size: min(3.6rem, 11vw);
        font-weight: 800;
        line-height: 1.15;
        margin: 10px 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        word-break: keep-all;
    }
    .big-stat-sub {
        font-size: 1.05rem;
        opacity: 0.95;
        font-weight: 500;
    }
    .user-badge {
        background: #f0f7ff;
        border: 1px solid #cce3ff;
        color: #0052cc;
        padding: 6px 12px;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 10px;
    }
    .demo-banner {
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeeba;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 0.9rem;
        margin-bottom: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- ヘッダー -----------------
st.title("💰 振り分け給料計算・月別集計")

# トンネルURLの表示（ローカル稼働時のみ）
tunnel_url = get_tunnel_url()
if tunnel_url:
    with st.expander("📱 スマホ・外出先から見る（QRコード）", expanded=False):
        st.markdown(f"**外出先スマホ用URL**: [{tunnel_url}]({tunnel_url})")
        st.image(f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={tunnel_url}", width=180, caption="スマホのカメラで読み取れます")
        st.caption("💡 スマホのSafari/Chromeで開いた後、「ホーム画面に追加」をすると本物のアプリのように全画面で使えます！")

creds = load_credentials()
has_creds = bool(creds.get("token") and creds.get("cookie_d"))

# ----------------- 検索・月選択・単価入力エリア -----------------
query_id = st.query_params.get("id", "")
col_input1, col_input2, col_input3 = st.columns([1.5, 1.2, 1.3])

with col_input1:
    search_input = st.text_input(
        "👤 社員番号 または 名前",
        value=query_id,
        placeholder="例: 123456 または 田中"
    ).strip()

if search_input:
    st.query_params["id"] = search_input
elif "id" in st.query_params:
    del st.query_params["id"]

# 未入力時はクリーンな初期案内画面を表示
if not search_input:
    st.info("👆 **上の入力枠に、ご自身の「社員番号」または「お名前」を入力してください。**\n\n入力すると、自動でメンバーを照合して給料計算画面が表示されます。")
    st.stop()

# 入力値からユーザーを自動特定（方法A）
resolved_uid, resolved_name = find_user_by_keyword(search_input)
active_user_key = resolved_uid if resolved_uid else search_input

# ユーザー名バッジの表示
if resolved_name:
    clean_name = clean_display_name(resolved_name)
    st.markdown(f'<div class="user-badge">👤 メンバー: <b>{clean_name}</b></div>', unsafe_allow_html=True)
elif search_input:
    st.markdown(f'<div class="user-badge">🔍 キーワード: <b>{search_input}</b></div>', unsafe_allow_html=True)

# そのユーザー専用のデータをロード
current_records = load_user_records(active_user_key)
current_rates = load_user_rates(active_user_key)

valid_records = []
for r in current_records:
    if isinstance(r, dict) and "target_value" in r:
        if "year_month" not in r:
            r["year_month"] = r.get("date", datetime.now(JST).strftime("%Y-%m-%d"))[:7]
        valid_records.append(r)

df = pd.DataFrame(valid_records)

# 月の選択肢
if not df.empty and "year_month" in df.columns:
    month_options = list(reversed(sorted(df["year_month"].unique().tolist())))
else:
    month_options = [datetime.now(JST).strftime("%Y-%m")]

month_display_map = {ym: format_japanese_month(ym) for ym in month_options}

with col_input2:
    selected_month = st.selectbox(
        "📅 表示月",
        options=month_options,
        format_func=lambda ym: month_display_map.get(ym, ym),
        index=0
    )

with col_input3:
    current_saved_rate = current_rates.get(selected_month, 2000)
    month_short_label = format_japanese_month(selected_month)
    input_rate = st.number_input(
        f"💴 {month_short_label}の単価 (円)",
        value=int(current_saved_rate),
        step=100,
        min_value=0,
        key=f"rate_{active_user_key}_{selected_month}",
        help=f"{month_short_label}の集計値に掛ける単価です。自動保存されます。"
    )
    if input_rate != current_saved_rate:
        current_rates[selected_month] = input_rate
        save_user_rates(active_user_key, current_rates)
        st.rerun()

# ----------------- 自動更新ボタン（Slack連携済みの場合） -----------------
if has_creds:
    col_sync1, col_sync2 = st.columns([3, 1])
    with col_sync1:
        btn_label = f"🔄 「{resolved_name.split()[1] if resolved_name and len(resolved_name.split())>1 else search_input}」の最新データをSlackから取得"
        if st.button(btn_label, type="primary", use_container_width=True):
            with st.spinner(f"Slack（#b01_振り分け完了報告）からデータを検索中..."):
                try:
                    client = SlackClient(token=creds["token"], cookie_d=creds["cookie_d"])
                    target_query_term = resolved_uid if resolved_uid else search_input
                    query = f"in:<#C012PFS70JH|b01_振り分け完了報告> {target_query_term}"
                    matches = client.search_all_messages(query, max_pages=10)

                    parse_kws = [resolved_uid] if resolved_uid else [search_input]
                    new_records = []
                    disp_label = clean_display_name(resolved_name) if resolved_name else search_input
                    for m in matches:
                        # 日本時間 (JST) で正確に変換（海外サーバーのUTCズレを防止）
                        dt = datetime.fromtimestamp(float(m.get("ts", 0)), tz=JST)
                        items = parse_slack_message(m.get("text", ""), mode="person_line", person_keywords=parse_kws)
                        for it in items:
                            new_records.append({
                                "date": dt.strftime("%Y-%m-%d %H:%M"),
                                "year_month": dt.strftime("%Y-%m"),
                                "target_value": it["value"],
                                "count_value": it.get("count_value"),
                                "matched_line": f"{disp_label}  {int(it.get('count_value', 1))}  {it['value']:.3f}",
                                "is_demo": False
                            })
                    if new_records:
                        new_records.sort(key=lambda x: x["date"])
                        save_user_records(active_user_key, new_records)
                        st.success(f"🎉 Slackから全 {len(new_records)} 件を自動取得しました！")
                        st.rerun()
                    else:
                        st.warning(f"「{search_input}」の投稿が見つかりませんでした。社員番号またはお名前をご確認ください。")
                except Exception as e:
                    st.error(f"取得エラー: {e}")
    with col_sync2:
        if st.button("⚙️ 連携解除", use_container_width=True):
            if os.path.exists(CREDS_FILE):
                os.remove(CREDS_FILE)
            st.rerun()

# ----------------- データ未取得時の案内 -----------------
if df.empty:
    st.info(f"💡 「{search_input}」の集計データがまだありません。上の「🔄 最新データをSlackから取得」ボタンを押すと、自動で取得・計算されます！")

# ----------------- データ取り込み・初期設定エリア -----------------
with st.expander("⚡ Slack連携設定 ＆ 手動コピペ", expanded=not has_creds):
    tab_auto_setup, tab_manual_paste = st.tabs([
        "🚀 【おすすめ】初回1回だけ設定して「一生コピペ不要」にする",
        "📋 手動コピペで追加"
    ])

    with tab_auto_setup:
        st.markdown("""
        ### コピペを完全にゼロにする方法（初回1回・1分だけ）
        ブラウザでSlackを開いた通信（cURL）を1回だけここに貼ると、**全員がボタン1つで全自動取得**できるようになります！
        
        **やり方（超かんたん・3ステップ）:**
        1. Chrome等のブラウザで **[Slack (Web版)](https://app.slack.com/client/)** を開きます。
        2. キーボードで **`Command (⌘) + Option + I`** を押し、上部の **「Network（ネットワーク）」** タブをクリック。
        3. Slackの検索バーで `in:#b01_振り分け完了報告` と検索します。
        4. Networkタブの通信一覧に **`search.messages`** が出るので、右クリック ➔ **「Copy」➔「Copy as cURL」** をクリック！
        5. 下の枠に貼り付けて **「設定を保存して全自動取得」** を押すだけ！
        """)

        curl_input = st.text_area(
            "Copy as cURL でコピーした内容をここに貼り付け",
            placeholder="curl 'https://slack.com/api/search.messages?...' -H 'authorization: Bearer xoxc-...' ...",
            height=90
        )
        if st.button("💾 設定を保存して今すぐ全自動取得！", type="primary", use_container_width=True):
            if curl_input.strip():
                t, c = extract_credentials_from_curl(curl_input)
                if t and c:
                    creds_data = {"token": t, "cookie_d": c}
                    save_credentials(creds_data)
                    st.success("🎉 Slack連携設定を保存しました！上の更新ボタンから最新データを取得できます。")
                    st.rerun()
                else:
                    st.error("貼り付けたcURLからトークンまたはCookieが見つかりませんでした。Networkタブの「search.messages」を正しくCopy as cURLできたかご確認ください。")
            else:
                st.warning("cURLを入力してください。")

    with tab_manual_paste:
        paste_mode = st.radio("取り込みモード", ["新規データとして上書き", "既存データに追加"], index=0, horizontal=True)
        pasted_text = st.text_area("Slackからコピーしたテキスト", placeholder="ここに貼り付けてください", height=100)
        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            if st.button("🚀 コピペを取り込んで反映", key="btn_paste_manual", use_container_width=True):
                if pasted_text.strip():
                    kws = [search_input]
                    if resolved_name:
                        kws.extend(resolved_name.split())
                    extracted_records = parse_search_results_dump(pasted_text, kws)
                    if extracted_records:
                        for r in extracted_records:
                            r["is_demo"] = False
                            if "year_month" not in r:
                                r["year_month"] = r.get("date", datetime.now(JST).strftime("%Y-%m-%d"))[:7]

                        if paste_mode == "既存データに追加":
                            cur = load_user_records(active_user_key)
                            seen = set((r["date"], r["matched_line"]) for r in cur)
                            for r in extracted_records:
                                key = (r["date"], r["matched_line"])
                                if key not in seen:
                                    cur.append(r)
                                    seen.add(key)
                            save_user_records(active_user_key, cur)
                        else:
                            save_user_records(active_user_key, extracted_records)
                        st.success(f"🎉 実データから {len(extracted_records)} 件の数値を更新しました！")
                        st.rerun()
                    else:
                        st.error(f"「{search_input}」の行が見つかりませんでした。テキストをご確認ください。")
                else:
                    st.warning("テキストを入力してください。")

        with col_p2:
            if st.button("🗑️ デモ用データを入れる", key="btn_reset", use_container_width=True):
                save_user_records(active_user_key, make_initial_demo_records())
                st.rerun()


# ----------------- データ集計 & 表示 -----------------
if df.empty or "year_month" not in df.columns or "target_value" not in df.columns:
    st.stop()

# 月別集計
agg_dict = {
    "total_value": ("target_value", "sum"),
    "count": ("target_value", "count")
}
if "count_value" in df.columns and df["count_value"].notna().any():
    agg_dict["items_count"] = ("count_value", "sum")

monthly_df = df.groupby("year_month").agg(**agg_dict).reset_index().sort_values(by="year_month")

if monthly_df.empty:
    st.warning("集計データが0件です。")
    st.stop()

# 各月の単価と給料を計算
monthly_df["unit_rate"] = monthly_df["year_month"].apply(lambda ym: current_rates.get(ym, 2000))
monthly_df["salary"] = (monthly_df["total_value"] * monthly_df["unit_rate"]).round().astype(int)
monthly_df["display_month"] = monthly_df["year_month"].apply(format_japanese_month)

# 選択月の行を取得
selected_matches = monthly_df[monthly_df["year_month"] == selected_month]
if selected_matches.empty:
    selected_row = monthly_df.iloc[-1]
    selected_month = selected_row["year_month"]
else:
    selected_row = selected_matches.iloc[0]

sel_total = selected_row["total_value"]
sel_rate = int(selected_row["unit_rate"])
sel_salary = int(selected_row["salary"])
sel_reports = int(selected_row["count"])
has_items = "items_count" in selected_row and pd.notna(selected_row["items_count"])
sel_items = int(selected_row["items_count"]) if has_items else 0
sel_display_name = format_japanese_month(selected_month)

# ----------------- 【一番上】当月の給料を大きく表示 -----------------
sub_text = f"報告回数: {sel_reports} 回"
if has_items:
    sub_text = f"件数合計: <b>{sel_items}</b> 件 ｜ {sub_text}"

st.markdown(f"""
<div class="big-stat-box">
    <div class="big-stat-title">🗓️ {sel_display_name} の給料（支給見込）</div>
    <div class="big-stat-number">¥ {sel_salary:,}</div>
    <div class="big-stat-sub">集計値: <b>{sel_total:.3f}</b> × 単価: <b>¥{sel_rate:,}</b> ｜ {sub_text}</div>
</div>
""", unsafe_allow_html=True)

# ----------------- 【下】月ごとの集計 & グラフ -----------------
col_g1, col_g2 = st.columns([2, 1])
with col_g1:
    st.subheader("📅 月ごとの推移グラフ")
with col_g2:
    chart_view = st.radio(
        "グラフ表示",
        ["💰 給料額 (円)", "📊 集計数値"],
        horizontal=True,
        label_visibility="collapsed"
    )

fig = go.Figure()
if chart_view == "💰 給料額 (円)":
    fig.add_trace(go.Bar(
        x=monthly_df["display_month"],
        y=monthly_df["salary"],
        marker_color="#11998e",
        text=monthly_df["salary"].apply(lambda v: f"¥{v:,}"),
        textposition="outside",
        name="給料額",
        hovertemplate="<b>%{x}</b><br>給料額: ¥%{y:,}<br>集計値: %{customdata[0]:.3f}<br>単価: ¥%{customdata[1]:,}<extra></extra>",
        customdata=monthly_df[["total_value", "unit_rate"]]
    ))
    y_title = "給料額 (円)"
else:
    fig.add_trace(go.Bar(
        x=monthly_df["display_month"],
        y=monthly_df["total_value"],
        marker_color="#3A1C71",
        text=monthly_df["total_value"].apply(lambda v: f"{v:.3f}"),
        textposition="outside",
        name="集計値",
        hovertemplate="<b>%{x}</b><br>集計値: %{y:.3f}<br>単価: ¥%{customdata[1]:,}<br>給料額: ¥%{customdata[0]:,}<extra></extra>",
        customdata=monthly_df[["salary", "unit_rate"]]
    ))
    y_title = "集計値"

fig.update_layout(
    margin=dict(l=15, r=15, t=35, b=30),
    height=340,
    xaxis=dict(
        title="年月",
        type="category",
        categoryorder="array",
        categoryarray=monthly_df["display_month"].tolist(),
        tickangle=0,
        showgrid=False
    ),
    yaxis=dict(
        title=y_title,
        rangemode="tozero",
        showgrid=True,
        gridcolor="#eeeeee"
    ),
    bargap=0.35
)
st.plotly_chart(fig, use_container_width=True)

# 月別一覧テーブル
# 月別一覧テーブル（直接編集可能）
col_tbl1, col_tbl2 = st.columns([2, 1])
with col_tbl1:
    st.subheader("📋 月別データ一覧")
with col_tbl2:
    st.caption("💡 「単価」の数字を押して直接変更できます")

table_df = monthly_df.copy().sort_values(by="year_month", ascending=False)
table_df["avg_value"] = table_df["total_value"] / table_df["count"]

# カラム構成
show_cols = ["display_month", "total_value", "unit_rate", "salary"]
if "items_count" in table_df.columns:
    show_cols.append("items_count")
show_cols.extend(["count", "avg_value"])

col_config = {
    "display_month": st.column_config.TextColumn("年月", disabled=True),
    "total_value": st.column_config.NumberColumn("集計値", format="%.3f", disabled=True),
    "unit_rate": st.column_config.NumberColumn(
        "💴 単価 (円) ✏️",
        min_value=0,
        step=100,
        format="¥%d",
        help="クリックまたはタップして単価を直接変更できます"
    ),
    "salary": st.column_config.NumberColumn("💰 給料合計 (円)", format="¥%d", disabled=True),
    "count": st.column_config.NumberColumn("報告回数", format="%d 回", disabled=True),
    "avg_value": st.column_config.NumberColumn("1回あたり平均", format="%.3f", disabled=True)
}
if "items_count" in table_df.columns:
    col_config["items_count"] = st.column_config.NumberColumn("件数合計", format="%d 件", disabled=True)

edited_table = st.data_editor(
    table_df[show_cols],
    column_config=col_config,
    use_container_width=True,
    hide_index=True,
    key=f"editor_{active_user_key}"
)

# 表内で単価が直接変更された場合の検知 & 即時保存
rate_updated = False
for idx, row in edited_table.iterrows():
    ym = table_df.iloc[idx]["year_month"]
    new_rate = int(row["unit_rate"])
    old_rate = int(current_rates.get(ym, 2000))
    if new_rate != old_rate:
        current_rates[ym] = new_rate
        # 上部のウィジェット状態も同期
        st.session_state[f"rate_{active_user_key}_{ym}"] = new_rate
        rate_updated = True

if rate_updated:
    save_user_rates(active_user_key, current_rates)
    st.rerun()

# 該当ログの確認（折りたたみ）
with st.expander("🔍 取り込まれたメッセージ行一覧"):
    month_filter_df = df[df["year_month"] == selected_month].sort_values(by="date", ascending=False)
    for _, r in month_filter_df.iterrows():
        st.code(f"{r['date']}  {r.get('matched_line', '')}")
