"""RSS 피드 수집 커넥터"""

import re
import time
from datetime import datetime
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
from xml.etree import ElementTree

from news_collector.ingestion.base_connector import BaseConnector
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class RSSConnector(BaseConnector):
    """RSS/Atom 피드 수집 커넥터."""

    async def fetch(self, keywords: List[str] = None, limit: int = 20) -> List[RawNewsRecord]:
        """RSS 피드에서 뉴스 수집."""
        logger.debug("RSS 수집 시작: %s (%s)", self.source.id, self.source.base_url)
        start = time.time()

        try:
            xml_text = self._fetch_feed(self.source.base_url)
            entries = self._parse_feed(xml_text)
        except Exception as e:
            logger.error("RSS 수집 실패: %s - %s", self.source.id, e)
            return []

        elapsed_ms = int((time.time() - start) * 1000)
        records: List[RawNewsRecord] = []

        for entry in entries[:limit]:
            title = entry.get("title", "")
            if keywords and not self._matches_keywords(title, entry.get("description", ""), keywords):
                continue

            record = RawNewsRecord(
                source_id=self.source.id,
                source_name=self.source.name,
                raw_html=entry.get("description", ""),
                raw_data=entry,
                extracted_text=self._strip_html(entry.get("description", "")),
                url=entry.get("link", ""),
                page_language=self.source.default_locale[:2],
                http_status=200,
                response_time_ms=elapsed_ms,
            )
            records.append(record)

        logger.info("RSS 수집 완료: %s → %d건 (%dms)", self.source.id, len(records), elapsed_ms)
        return records

    def _fetch_feed(self, url: str) -> str:
        """HTTP로 RSS 피드 XML 가져오기."""
        req = Request(url, headers={"User-Agent": self.source.user_agent})
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _parse_feed(self, xml_text: str) -> List[dict]:
        """RSS/Atom XML 파싱."""
        entries = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("XML 파싱 실패: %s", self.source.id)
            return []

        # RSS 2.0
        for item in root.iter("item"):
            entries.append({
                "title": self._text(item, "title"),
                "link": self._text(item, "link"),
                "description": self._text(item, "description"),
                "pubDate": self._text(item, "pubDate"),
                "author": self._text(item, "author") or self._text(item, "{http://purl.org/dc/elements/1.1/}creator"),
            })

        # Atom
        if not entries:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns):
                link_el = entry.find("atom:link", ns)
                entries.append({
                    "title": self._text_ns(entry, "atom:title", ns),
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "description": self._text_ns(entry, "atom:summary", ns) or self._text_ns(entry, "atom:content", ns),
                    "pubDate": self._text_ns(entry, "atom:published", ns) or self._text_ns(entry, "atom:updated", ns),
                    "author": self._text_ns(entry, "atom:author/atom:name", ns),
                })

        return entries

    @staticmethod
    def _text(element, tag: str) -> str:
        el = element.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _text_ns(element, tag: str, ns: dict) -> str:
        el = element.find(tag, ns)
        return el.text.strip() if el is not None and el.text else ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """HTML 태그 제거."""
        return re.sub(r"<[^>]+>", "", html).strip()

    @staticmethod
    def _matches_keywords(title: str, description: str, keywords: List[str]) -> bool:
        """키워드 매칭."""
        text = (title + " " + description).lower()
        return any(kw.lower() in text for kw in keywords)
