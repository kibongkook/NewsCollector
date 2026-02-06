"""Google News RSS 커넥터 - 날짜 범위 검색 지원"""

import html
import re
import time
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote
from xml.etree import ElementTree

from news_collector.ingestion.base_connector import BaseConnector
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource, RateLimit
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# Google News RSS 정책
# - 최대 100건 반환
# - 날짜 검색: after:YYYY-MM-DD, before:YYYY-MM-DD
# - 언어/지역: hl, gl, ceid 파라미터
GOOGLE_NEWS_BASE_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_MAX_RESULTS = 100


class GoogleNewsConnector(BaseConnector):
    """
    Google News RSS 커넥터.

    특징:
    - 날짜 범위 검색 지원 (after:, before: 파라미터)
    - 키워드 검색 지원
    - 한국어/영어 등 다국어 지원
    - API 키 불필요 (무료)

    사용법:
        connector = GoogleNewsConnector()
        records = await connector.fetch(
            keywords=["경제"],
            limit=50,
            date_from=datetime(2025, 1, 1),
            date_to=datetime(2025, 1, 31),
        )
    """

    def __init__(
        self,
        source: Optional[NewsSource] = None,
        language: str = "ko",
        country: str = "KR",
    ) -> None:
        """
        GoogleNewsConnector 초기화.

        Args:
            source: 뉴스 소스 메타데이터 (None이면 기본값 사용)
            language: 언어 코드 (ko, en, ja 등)
            country: 국가 코드 (KR, US, JP 등)
        """
        if source is None:
            source = NewsSource(
                id="google_news",
                name="Google News",
                ingestion_type="rss",
                base_url=GOOGLE_NEWS_BASE_URL,
                tier="tier1",
                credibility_base_score=90.0,
                rate_limit=RateLimit(
                    requests_per_minute=60,
                    requests_per_hour=600,
                    daily_quota=10000,
                ),
            )

        super().__init__(source)
        self._language = language
        self._country = country

    async def fetch(
        self,
        keywords: Optional[List[str]] = None,
        limit: int = 50,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[RawNewsRecord]:
        """
        Google News RSS에서 뉴스 수집.

        Args:
            keywords: 검색 키워드 리스트
            limit: 최대 결과 수 (1~100)
            date_from: 시작 날짜 (포함)
            date_to: 종료 날짜 (포함)

        Returns:
            수집된 RawNewsRecord 리스트
        """
        query = self._build_query(keywords, date_from, date_to)
        url = self._build_url(query)

        logger.info(
            "Google News 검색: query='%s', date_from=%s, date_to=%s",
            " ".join(keywords) if keywords else "(none)",
            date_from.strftime("%Y-%m-%d") if date_from else "(none)",
            date_to.strftime("%Y-%m-%d") if date_to else "(none)",
        )

        start_time = time.time()
        try:
            xml_text = self._fetch_feed(url)
            entries = self._parse_feed(xml_text)
        except Exception as e:
            logger.error("Google News 수집 실패: %s", e)
            return []

        elapsed_ms = int((time.time() - start_time) * 1000)
        records: List[RawNewsRecord] = []

        for entry in entries[:min(limit, GOOGLE_NEWS_MAX_RESULTS)]:
            title = self._clean_html(entry.get("title", ""))
            description = self._clean_html(entry.get("description", ""))
            source_name = entry.get("source", "Google News")

            record = RawNewsRecord(
                source_id="google_news",
                source_name=source_name,
                raw_data={
                    **entry,
                    "title": title,
                    "description": description,
                    "source_tier": self._infer_tier(source_name),
                },
                raw_html=entry.get("description", ""),
                extracted_text=f"{title} {description}",
                url=entry.get("link", ""),
                page_language=self._language,
                http_status=200,
                response_time_ms=elapsed_ms,
            )
            records.append(record)

        logger.info("Google News 수집 완료: %d건 (%dms)", len(records), elapsed_ms)
        return records

    def _build_query(
        self,
        keywords: Optional[List[str]],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> str:
        """검색 쿼리 문자열 생성."""
        parts = []

        # 키워드
        if keywords:
            parts.append(" ".join(keywords))

        # 날짜 범위 (after:, before: 파라미터)
        # Google News: after:는 exclusive (해당일 이후), before:도 exclusive (해당일 이전)
        if date_from:
            # after: exclusive - 전날로 설정하면 해당 날짜부터 포함
            after_date = date_from - timedelta(days=1)
            parts.append(f"after:{after_date.strftime('%Y-%m-%d')}")
        if date_to:
            # before: exclusive - 다음날로 설정하면 해당 날짜까지 포함
            before_date = date_to + timedelta(days=1)
            parts.append(f"before:{before_date.strftime('%Y-%m-%d')}")

        return " ".join(parts) if parts else "뉴스"

    def _build_url(self, query: str) -> str:
        """RSS URL 생성."""
        params = {
            "q": query,
            "hl": self._language,
            "gl": self._country,
            "ceid": f"{self._country}:{self._language}",
        }
        return f"{GOOGLE_NEWS_BASE_URL}?{urlencode(params, quote_via=quote)}"

    def _fetch_feed(self, url: str) -> str:
        """HTTP로 RSS 피드 XML 가져오기."""
        req = Request(url, headers={"User-Agent": self.source.user_agent})
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _parse_feed(self, xml_text: str) -> List[dict]:
        """RSS XML 파싱."""
        entries = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            logger.warning("XML 파싱 실패: %s", e)
            return []

        for item in root.iter("item"):
            # Google News RSS는 source 태그에 원본 출처 포함
            source_el = item.find("source")
            source_name = source_el.text if source_el is not None and source_el.text else "Unknown"

            entries.append({
                "title": self._text(item, "title"),
                "link": self._text(item, "link"),
                "description": self._text(item, "description"),
                "pubDate": self._text(item, "pubDate"),
                "source": source_name,
                "guid": self._text(item, "guid"),
            })

        return entries

    @staticmethod
    def _text(element, tag: str) -> str:
        """XML 요소에서 텍스트 추출."""
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    def _clean_html(self, text: str) -> str:
        """HTML 엔티티 디코딩 및 태그 제거."""
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _infer_tier(self, source_name: str) -> str:
        """소스 이름으로 신뢰도 tier 추론."""
        tier1_sources = {
            "연합뉴스", "KBS", "MBC", "SBS", "조선일보", "중앙일보",
            "한겨레", "동아일보", "YTN", "JTBC", "Reuters", "AP",
            "Bloomberg", "BBC", "CNN",
        }
        tier2_sources = {
            "매일경제", "한국경제", "뉴시스", "뉴스1", "아시아경제",
            "서울신문", "경향신문", "한국일보",
        }

        if source_name in tier1_sources:
            return "tier1"
        if source_name in tier2_sources:
            return "tier2"
        return "tier3"


# 편의 함수: 동기 버전
def fetch_google_news_sync(
    keywords: List[str],
    limit: int = 50,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    language: str = "ko",
    country: str = "KR",
) -> List[RawNewsRecord]:
    """
    Google News RSS 동기 호출.

    Args:
        keywords: 검색 키워드 리스트
        limit: 최대 결과 수
        date_from: 시작 날짜
        date_to: 종료 날짜
        language: 언어 코드
        country: 국가 코드

    Returns:
        RawNewsRecord 리스트
    """
    import asyncio

    connector = GoogleNewsConnector(language=language, country=country)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                connector.fetch(keywords, limit, date_from, date_to)
            )
            return future.result()
    else:
        return asyncio.run(connector.fetch(keywords, limit, date_from, date_to))
