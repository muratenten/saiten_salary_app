"""
Slackメッセージから特定ユーザーの行や日付を高度に抽出するモジュール
Slack検索結果画面の全選択コピペ (Cmd+A -> Cmd+C) に完全対応
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


def normalize_text(text: str) -> str:
    """全角英数字・記号を半角に正規化する"""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", text)


def parse_search_results_dump(
    text: str,
    keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Slackの検索結果画面を丸ごと全選択（Cmd+A）してコピーしたテキストから、
    各投稿の日付と、対象メンバー（村本拓海 / 948919）の数値を自動抽出する
    """
    if not text:
        return []

    norm_text = normalize_text(text)
    lines = norm_text.splitlines()

    # 日付パターン
    date_ymd = re.compile(r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})')
    date_md = re.compile(r'(\d{1,2})月(\d{1,2})日')
    date_relative_today = re.compile(r'(今日|本日)')
    date_relative_yesterday = re.compile(r'(昨日)')

    current_dt = datetime.now()
    records = []

    # 無視するヘッダーキーワード
    ignore_headers = ["次の内容に関する検索結果", "件の結果", "並び替え", "フィルター", "フィードバックを送る"]

    norm_keywords = [normalize_text(k).strip() for k in keywords if k.strip()]

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue

        # ヘッダー行をスキップ
        if any(ign in line_clean for ign in ignore_headers):
            continue

        # 1. 行内の日付を探索して更新
        m_ymd = date_ymd.search(line_clean)
        m_md = date_md.search(line_clean)
        if m_ymd:
            y, m, d = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
            try:
                current_dt = datetime(y, m, d)
            except ValueError:
                pass
        elif m_md:
            now = datetime.now()
            m, d = int(m_md.group(1)), int(m_md.group(2))
            try:
                # 9月現在の実行で10月以降の日付が出たら昨年と推測
                year = now.year if m <= now.month else now.year - 1
                current_dt = datetime(year, m, d)
            except ValueError:
                pass
        elif date_relative_today.search(line_clean):
            current_dt = datetime.now()
        elif date_relative_yesterday.search(line_clean):
            current_dt = datetime.now() - timedelta(days=1)

        # 2. キーワードが含まれる行かチェック
        matched_kw = None
        for kw in norm_keywords:
            if kw in line_clean:
                matched_kw = kw
                break

        if not matched_kw:
            continue

        # 「# b01_振り分け完了報告 948919」のような検索クエリ文字列の行は除外
        if "in:#" in line_clean or "検索 :" in line_clean:
            continue

        # 数値をすべて抽出
        nums = re.findall(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', line_clean)
        if not nums:
            continue

        # 最後の数値がキーワードそのもの（例: 948919）と一致している場合は除外
        last_raw = nums[-1].replace(",", "")
        if last_raw in norm_keywords:
            continue

        try:
            target_val = float(last_raw)
        except ValueError:
            continue

        count_val = None
        if len(nums) >= 2:
            prev_raw = nums[-2].replace(",", "")
            # 直前の数値がIDそのものでない場合
            if prev_raw not in norm_keywords:
                try:
                    count_val = float(prev_raw)
                except ValueError:
                    pass

        records.append({
            "datetime": current_dt,
            "year_month": current_dt.strftime("%Y-%m"),
            "date": current_dt.strftime("%Y-%m-%d"),
            "target_value": target_val,
            "count_value": count_val,
            "raw_value": nums[-1],
            "matched_line": line_clean
        })

    return records


def parse_slack_message(
    text: str,
    mode: str = "person_line",
    person_keywords: Optional[List[str]] = None,
    item_name: str = "",
    custom_regex: Optional[str] = None
) -> List[Dict[str, Any]]:
    """既存のメッセージ単体解析用"""
    if not text:
        return []

    norm_text = normalize_text(text)
    results = []

    if mode == "person_line":
        if not person_keywords:
            person_keywords = ["948919", "村本拓海"]

        lines = norm_text.splitlines()
        for line in lines:
            line_clean = line.strip()
            # 検索クエリ行の誤爆防止
            if "in:#" in line_clean or "検索 :" in line_clean or "件の結果" in line_clean:
                continue

            matched_kw = None
            for kw in person_keywords:
                norm_kw = normalize_text(kw).strip()
                if norm_kw and norm_kw in line_clean:
                    matched_kw = norm_kw
                    break
            if not matched_kw:
                continue

            nums = re.findall(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', line_clean)
            if not nums:
                continue

            last_raw = nums[-1].replace(",", "")
            if last_raw == matched_kw:
                continue

            try:
                target_val = float(last_raw)
            except ValueError:
                continue

            count_val = None
            if len(nums) >= 2:
                prev_raw = nums[-2].replace(",", "")
                if prev_raw != matched_kw:
                    try:
                        count_val = float(prev_raw)
                    except ValueError:
                        pass

            results.append({
                "item": matched_kw,
                "value": target_val,
                "count_value": count_val,
                "raw_value": nums[-1],
                "unit": "",
                "matched_text": line_clean
            })
        return results

    return results


def extract_dates_and_blocks_from_paste(text: str) -> List[Dict[str, Any]]:
    """互換性のための関数"""
    return [{"datetime": datetime.now(), "text": text}]
