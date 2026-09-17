"""
デモ・テスト用のサンプルSlackデータ生成モジュール
画像で提供された「振り分け完了報告」チャンネルの実データに合わせたサンプルを生成します。
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


def generate_sample_distribution_messages(target_name: str = "村本拓海", target_id: str = "948919", count: int = 40) -> List[Dict[str, Any]]:
    """
    「#b01_振り分け完了報告」チャンネルを模したリアルなサンプルデータを生成する
    """
    members = [
        ("945370", "中川圭裕"),
        ("945588", "中川裕貴"),
        ("946321", "西部結衣"),
        ("946444", "野田和輝"),
        ("947122", "廣谷圭亮"),
        ("947785", "米谷匠人"),
        ("948510", "峰澤太朗"),
        (target_id, target_name),
        ("948986", "森下暁仁"),
        ("949338", "山口悠翔"),
        ("949575", "山田想"),
        ("952088", "川平諒"),
        ("953190", "篠田遥斗"),
    ]

    now = datetime.now()
    messages = []

    for i in range(count):
        # 過去180日（約6ヶ月）の間で分散
        days_ago = random.uniform(0, 180)
        msg_date = now - timedelta(days=days_ago)
        ts = str(msg_date.timestamp())

        # 各メンバーの振り分け行を生成
        lines = []
        for mid, mname in members:
            # 村本さんの場合は数値をリアルに（例: 3〜8件, 0.3〜1.2）
            if mname == target_name:
                cnt = random.randint(2, 9)
                val = round(random.uniform(0.200, 1.250), 3)
            else:
                cnt = random.randint(1, 15)
                val = round(random.uniform(0.040, 1.400), 3)
            lines.append(f"@{mid} {mname}  {cnt}  {val:.3f}")

        # シャッフルして並べる
        random.shuffle(lines)

        header = f"【振り分け完了報告】{msg_date.strftime('%Y/%m/%d %H:%M')}\n本日の振り分け結果です。"
        full_text = header + "\n" + "\n".join(lines)

        messages.append({
            "type": "message",
            "user": "U_BOT_ADMIN",
            "user_name": "振り分けBot",
            "text": full_text,
            "ts": ts
        })

    messages.sort(key=lambda x: float(x["ts"]), reverse=True)
    return messages
