"""
Slack Web API クライアントモジュール
Bot Token (xoxb-) または User Session (xoxc- + Cookie) による検索に対応
"""

import time
import requests
from typing import List, Dict, Any, Optional


SLACK_API_BASE = "https://slack.com/api"


class SlackAPIError(Exception):
    """Slack API呼び出し時の例外クラス"""
    pass


class SlackClient:
    def __init__(self, token: str, cookie_d: Optional[str] = None):
        self.token = token.strip() if token else ""
        self.cookie_d = cookie_d.strip() if cookie_d else ""
        self.headers = {
            "Authorization": f"Bearer {self.token}",
        }
        if self.cookie_d:
            self.headers["Cookie"] = f"d={self.cookie_d}"
        self._user_cache: Dict[str, str] = {}

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{SLACK_API_BASE}/{endpoint}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method.upper() == "GET":
                    res = requests.get(url, headers=self.headers, params=params or {}, timeout=15)
                else:
                    res = requests.post(url, headers=self.headers, data=data or {}, timeout=15)
            except requests.RequestException as e:
                raise SlackAPIError(f"通信エラーが発生しました: {e}")

            if res.status_code == 429:
                retry_after = int(res.headers.get("Retry-After", 1))
                time.sleep(retry_after)
                continue

            data_res = res.json()
            if not data_res.get("ok"):
                error_code = data_res.get("error", "unknown_error")
                error_msg = self._translate_error(error_code)
                raise SlackAPIError(f"Slack APIエラー: {error_msg} (コード: {error_code})")

            return data_res

        raise SlackAPIError("Slack APIのレートリミット超過によりリトライ上限に達しました。")

    @staticmethod
    def _translate_error(code: str) -> str:
        messages = {
            "invalid_auth": "認証トークンが無効です。",
            "not_authed": "トークンが設定されていません。",
            "account_inactive": "このアカウントは無効化されています。",
            "token_revoked": "トークンが失効しています。",
            "channel_not_found": "指定されたチャンネルが見つかりません。",
            "not_in_channel": "Botがチャンネルに参加していません。",
            "missing_scope": "必要な権限が不足しています。",
            "ratelimited": "APIのレート制限に達しました。"
        }
        return messages.get(code, f"エラーコード: {code}")

    def test_auth(self) -> Dict[str, Any]:
        data = self._request("GET", "auth.test")
        return {
            "ok": True,
            "user_id": data.get("user_id"),
            "user": data.get("user"),
            "team": data.get("team"),
            "team_id": data.get("team_id")
        }

    def search_all_messages(self, query: str, max_pages: int = 10) -> List[Dict[str, Any]]:
        """
        Slackの検索APIを使って、複数ページに跨がるメッセージをすべて自動取得する
        """
        all_matches = []
        page = 1

        while page <= max_pages:
            params = {
                "query": query,
                "count": 100,
                "page": page,
                "sort": "timestamp",
                "sort_dir": "desc"
            }
            try:
                data = self._request("GET", "search.messages", params=params)
            except Exception:
                # search.modules.messages へのフォールバック
                data = self._request("GET", "search.modules.messages", params=params)

            msg_obj = data.get("messages", {})
            matches = msg_obj.get("matches", [])
            if not matches:
                # search.modules.messages の構造
                items = data.get("items", []) or data.get("results", [])
                if items:
                    matches = items
                else:
                    break

            all_matches.extend(matches)

            pagination = msg_obj.get("pagination", {}) or data.get("pagination", {})
            total_pages = pagination.get("page_count", 1)
            if page >= total_pages:
                break
            page += 1

        return all_matches

    def fetch_messages(
        self,
        channel_id: str,
        oldest_ts: Optional[float] = None,
        max_messages: int = 1000
    ) -> List[Dict[str, Any]]:
        messages = []
        cursor = None
        while len(messages) < max_messages:
            limit = min(200, max_messages - len(messages))
            params = {"channel": channel_id, "limit": limit}
            if oldest_ts:
                params["oldest"] = str(oldest_ts)
            if cursor:
                params["cursor"] = cursor

            data = self._request("GET", "conversations.history", params=params)
            batch = data.get("messages", [])
            if not batch:
                break
            messages.extend(batch)
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor or not data.get("has_more"):
                break

        return messages
