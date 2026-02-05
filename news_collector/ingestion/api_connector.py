"""API 기반 수집 커넥터"""

import json
import time
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.parse import urlencode

from news_collector.ingestion.base_connector import BaseConnector
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class APIConnector(BaseConnector):
    """REST API 기반 수집 커넥터."""

    def __init__(self, source: NewsSource, api_key: str = "", api_secret: str = "") -> None:
        super().__init__(source)
        self._api_key = api_key
        self._api_secret = api_secret

    async def fetch(self, keywords: List[str] = None, limit: int = 20) -> List[RawNewsRecord]:
        """API에서 뉴스 수집."""
        logger.debug("API 수집 시작: %s", self.source.id)
        start = time.time()

        query = " ".join(keywords) if keywords else ""
        params = {"query": query, "display": min(limit, 100), "start": 1, "sort": "date"}
        url = f"{self.source.base_url}?{urlencode(params)}"

        headers = {"User-Agent": self.source.user_agent}
        if self._api_key:
            headers["X-Naver-Client-Id"] = self._api_key
            headers["X-Naver-Client-Secret"] = self._api_secret

        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                status = resp.status
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("API 수집 실패: %s - %s", self.source.id, e)
            return []

        elapsed_ms = int((time.time() - start) * 1000)
        records: List[RawNewsRecord] = []

        items = data.get("items", data.get("articles", []))
        for item in items[:limit]:
            record = RawNewsRecord(
                source_id=self.source.id,
                source_name=self.source.name,
                raw_data=item,
                raw_html=item.get("description", ""),
                extracted_text=item.get("title", "") + " " + item.get("description", ""),
                url=item.get("link", item.get("originallink", "")),
                page_language=self.source.default_locale[:2],
                http_status=status,
                response_time_ms=elapsed_ms,
            )
            records.append(record)

        logger.info("API 수집 완료: %s → %d건 (%dms)", self.source.id, len(records), elapsed_ms)
        return records
