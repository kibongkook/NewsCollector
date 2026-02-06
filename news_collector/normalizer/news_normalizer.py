"""Module 4: Parsing & Normalization - 뉴스 정규화"""

import html as html_module
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dateutil import parser as dateutil_parser

from news_collector.models.news import NormalizedNews
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource
from news_collector.utils.config_manager import ConfigManager
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

CATEGORY_MAPPING: Dict[str, List[str]] = {
    "정치": ["politics", "정치", "국회", "대통령", "정당"],
    "경제": ["economy", "경제", "기업", "주식", "금융", "business", "finance"],
    "사회": ["society", "사회", "범죄", "교육", "복지"],
    "IT": ["tech", "it", "기술", "소프트웨어", "ai", "인공지능", "technology"],
    "과학": ["science", "과학", "연구", "우주", "바이오"],
    "문화": ["culture", "문화", "예술", "영화", "음악"],
    "스포츠": ["sports", "스포츠", "축구", "야구", "농구"],
    "국제": ["world", "international", "국제", "세계", "외교"],
    "연예": ["entertainment", "연예", "아이돌", "드라마"],
}

# 동영상/방송 뉴스 제외 패턴
VIDEO_NEWS_PATTERNS = [
    r"뉴스와이드\s*\d{1,2}월\s*\d{1,2}일",  # 뉴스와이드 01월 04일
    r"뉴스데스크\s*\d{1,2}월\s*\d{1,2}일",
    r"뉴스룸\s*\d{1,2}월\s*\d{1,2}일",
    r"뉴스특보\s*\d{1,2}월\s*\d{1,2}일",
    r"\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}",  # 11:50 ~ 13:44 시간대 패턴
    r"^\[.*생중계.*\]",  # [생중계]
    r"^\[.*LIVE.*\]",  # [LIVE]
    r"^\[.*라이브.*\]",  # [라이브]
]


class NewsNormalizer:
    """
    Module 4: RawNewsRecord → NormalizedNews 변환.
    HTML 정제, 날짜 파싱, 카테고리 매핑.
    """

    def __init__(self, config: Optional[ConfigManager] = None) -> None:
        self._config = config

    def normalize(
        self, raw: RawNewsRecord, source: Optional[NewsSource] = None
    ) -> NormalizedNews:
        """단일 RawNewsRecord를 NormalizedNews로 변환."""
        data = raw.raw_data or {}
        title = self._clean_html(data.get("title", "") or (raw.extracted_text or "")[:200])
        body = self._clean_html(
            data.get("description", "")
            or data.get("summary", "")
            or data.get("content", "")
            or raw.raw_html
        )
        if not body:
            body = raw.extracted_text

        author = data.get("author", "") or data.get("creator", "")
        pub_date = self._parse_datetime(data.get("pubDate") or data.get("published") or data.get("pub_date"))
        category_hint = data.get("category", "") or data.get("section", "")
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        source_tier = source.tier if source else data.get("source_tier", "tier2")
        source_name = source.name if source else raw.source_name
        language = (source.default_locale[:2] if source else raw.page_language) or "ko"

        return NormalizedNews(
            id=str(uuid.uuid4()),
            raw_record_id=raw.id,
            source_id=raw.source_id,
            source_name=source_name,
            source_tier=source_tier,
            title=title,
            body=body,
            summary=body[:200] if body else None,
            author=author or None,
            published_at=pub_date or raw.fetch_timestamp or datetime.now(timezone.utc),
            language=language,
            country="KR" if language == "ko" else "US",
            category=self._infer_category(category_hint, title),
            tags=tags,
            url=raw.url,
            image_urls=self._extract_image_urls(raw.raw_html),
            view_count=data.get("view_count"),
            share_count=data.get("share_count"),
            comment_count=data.get("comment_count"),
            crawl_timestamp=raw.fetch_timestamp or datetime.now(timezone.utc),
            normalized_timestamp=datetime.now(timezone.utc),
        )

    def normalize_batch(
        self,
        records: List[RawNewsRecord],
        source_map: Optional[Dict[str, NewsSource]] = None,
        filter_video_news: bool = True,
        target_date: Optional[datetime] = None,
        date_tolerance_days: int = 1,
    ) -> List[NormalizedNews]:
        """배치 정규화.

        Args:
            records: 원본 뉴스 레코드 리스트
            source_map: 소스 ID → NewsSource 매핑
            filter_video_news: True면 동영상/방송 뉴스 제외
            target_date: 지정 시 해당 날짜 ± tolerance 범위만 포함
            date_tolerance_days: 날짜 허용 범위 (일)
        """
        source_map = source_map or {}
        results = []
        filtered_video = 0
        filtered_date = 0

        for raw in records:
            try:
                # 동영상 뉴스 필터링
                if filter_video_news and self._is_video_news(raw):
                    filtered_video += 1
                    continue

                source = source_map.get(raw.source_id)
                normalized = self.normalize(raw, source)

                # 날짜 필터링
                if target_date and normalized.published_at:
                    diff_days = abs((normalized.published_at.replace(tzinfo=None) -
                                    target_date.replace(tzinfo=None)).days)
                    if diff_days > date_tolerance_days:
                        filtered_date += 1
                        continue

                results.append(normalized)
            except Exception as e:
                logger.error("정규화 실패: %s - %s", raw.id, e)

        if filtered_video > 0:
            logger.info("동영상 뉴스 제외: %d건", filtered_video)
        if filtered_date > 0:
            logger.info("날짜 불일치 제외: %d건", filtered_date)
        logger.info("정규화 완료: %d/%d건", len(results), len(records))
        return results

    def _is_video_news(self, raw: RawNewsRecord) -> bool:
        """동영상/방송 뉴스인지 확인."""
        data = raw.raw_data or {}
        title = data.get("title", "") or ""

        for pattern in VIDEO_NEWS_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return True
        return False

    def _clean_html(self, html: str) -> str:
        """HTML 태그 제거 및 정제."""
        if not html:
            return ""
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        # HTML entity 올바르게 디코딩 (&amp; → &, &lt; → < 등)
        text = html_module.unescape(text)
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """다양한 날짜 형식 파싱."""
        if not date_str:
            return None
        try:
            return dateutil_parser.parse(date_str)
        except (ValueError, TypeError, OverflowError):
            logger.debug("날짜 파싱 실패: %s", date_str)
            return None

    def _infer_category(self, hint: str, title: str) -> Optional[str]:
        """카테고리 추론."""
        text = (hint + " " + title).lower()
        for category, keywords in CATEGORY_MAPPING.items():
            if any(kw in text for kw in keywords):
                return category
        return None

    def _extract_image_urls(self, html: str) -> List[str]:
        """HTML에서 이미지 URL 추출."""
        if not html:
            return []
        return re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
