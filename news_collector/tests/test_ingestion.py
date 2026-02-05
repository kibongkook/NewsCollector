"""Module 3: Ingestion Engine 테스트"""

import asyncio
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree

import pytest

from news_collector.ingestion.rss_connector import RSSConnector
from news_collector.ingestion.api_connector import APIConnector
from news_collector.ingestion.ingestion_engine import IngestionEngine
from news_collector.models.source import NewsSource
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.query_spec import QuerySpec
from news_collector.registry.source_registry import SourceRegistry


# ─── Fixture ────────────────────────────────────────────

def _make_source(**overrides) -> NewsSource:
    defaults = {
        "id": "test_rss",
        "name": "Test RSS",
        "base_url": "https://example.com/feed.xml",
        "ingestion_type": "rss",
        "tier": "tier1",
        "supported_categories": ["IT"],
        "default_locale": "ko_KR",
        "user_agent": "TestBot/1.0",
        "credibility_base_score": 85,
    }
    defaults.update(overrides)
    return NewsSource(**defaults)


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>AI 기술 혁신 발표</title>
      <link>https://example.com/news/1</link>
      <description>인공지능 기술의 새로운 혁신이 발표되었습니다.</description>
      <pubDate>Wed, 05 Feb 2026 10:00:00 +0900</pubDate>
      <author>홍길동</author>
    </item>
    <item>
      <title>경제 전망 보고서</title>
      <link>https://example.com/news/2</link>
      <description>2026년 경제 전망 보고서가 공개되었습니다.</description>
      <pubDate>Wed, 05 Feb 2026 09:00:00 +0900</pubDate>
    </item>
    <item>
      <title>스포츠 경기 결과</title>
      <link>https://example.com/news/3</link>
      <description>오늘 열린 축구 경기 결과입니다.</description>
    </item>
  </channel>
</rss>"""

SAMPLE_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>Atom 뉴스 제목</title>
    <link href="https://atom.example.com/1"/>
    <summary>Atom 뉴스 요약</summary>
    <published>2026-02-05T10:00:00+09:00</published>
  </entry>
</feed>"""


# ═══════════════════════════════════════════════════════════
# RSSConnector 테스트
# ═══════════════════════════════════════════════════════════

class TestRSSConnectorParsing:
    """RSS XML 파싱 테스트 (네트워크 불필요)."""

    def setup_method(self):
        self.source = _make_source()
        self.connector = RSSConnector(self.source)

    def test_parse_rss20(self):
        entries = self.connector._parse_feed(SAMPLE_RSS_XML)
        assert len(entries) == 3
        assert entries[0]["title"] == "AI 기술 혁신 발표"
        assert entries[0]["link"] == "https://example.com/news/1"
        assert "인공지능" in entries[0]["description"]

    def test_parse_atom(self):
        entries = self.connector._parse_feed(SAMPLE_ATOM_XML)
        assert len(entries) == 1
        assert entries[0]["title"] == "Atom 뉴스 제목"
        assert entries[0]["link"] == "https://atom.example.com/1"

    def test_parse_invalid_xml(self):
        entries = self.connector._parse_feed("<not valid xml")
        assert entries == []

    def test_parse_empty_feed(self):
        entries = self.connector._parse_feed('<?xml version="1.0"?><rss><channel></channel></rss>')
        assert entries == []


class TestRSSConnectorHelpers:
    """RSS 유틸리티 메서드 테스트."""

    def test_strip_html(self):
        assert RSSConnector._strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_strip_html_empty(self):
        assert RSSConnector._strip_html("") == ""

    def test_matches_keywords_true(self):
        assert RSSConnector._matches_keywords("AI 기술 혁신", "상세 내용", ["AI"])

    def test_matches_keywords_false(self):
        assert not RSSConnector._matches_keywords("경제 뉴스", "경제 전망", ["스포츠"])

    def test_matches_keywords_case_insensitive(self):
        assert RSSConnector._matches_keywords("KPOP News", "description", ["kpop"])


class TestRSSConnectorFetch:
    """RSS fetch 테스트 (네트워크 모킹)."""

    def test_fetch_success(self):
        source = _make_source()
        connector = RSSConnector(source)

        with patch.object(connector, "_fetch_feed", return_value=SAMPLE_RSS_XML):
            records = asyncio.run(connector.fetch(limit=10))
            assert len(records) == 3
            assert all(isinstance(r, RawNewsRecord) for r in records)
            assert records[0].source_id == "test_rss"
            assert records[0].url == "https://example.com/news/1"

    def test_fetch_with_keyword_filter(self):
        source = _make_source()
        connector = RSSConnector(source)

        with patch.object(connector, "_fetch_feed", return_value=SAMPLE_RSS_XML):
            records = asyncio.run(connector.fetch(keywords=["AI"], limit=10))
            assert len(records) == 1
            assert "AI" in records[0].raw_data["title"]

    def test_fetch_with_limit(self):
        source = _make_source()
        connector = RSSConnector(source)

        with patch.object(connector, "_fetch_feed", return_value=SAMPLE_RSS_XML):
            records = asyncio.run(connector.fetch(limit=2))
            assert len(records) == 2

    def test_fetch_error_returns_empty(self):
        source = _make_source()
        connector = RSSConnector(source)

        with patch.object(connector, "_fetch_feed", side_effect=Exception("Network error")):
            records = asyncio.run(connector.fetch())
            assert records == []


# ═══════════════════════════════════════════════════════════
# APIConnector 테스트
# ═══════════════════════════════════════════════════════════

class TestAPIConnector:
    """API 커넥터 테스트."""

    def test_init_with_credentials(self):
        source = _make_source(id="naver_api", ingestion_type="api", base_url="https://openapi.naver.com/v1/search/news.json")
        connector = APIConnector(source, api_key="test_key", api_secret="test_secret")
        assert connector._api_key == "test_key"
        assert connector._api_secret == "test_secret"

    def test_init_without_credentials(self):
        source = _make_source(ingestion_type="api")
        connector = APIConnector(source)
        assert connector._api_key == ""


# ═══════════════════════════════════════════════════════════
# IngestionEngine 테스트
# ═══════════════════════════════════════════════════════════

class TestIngestionEngine:
    """수집 엔진 테스트."""

    def _make_registry(self) -> SourceRegistry:
        """테스트용 레지스트리 생성."""
        registry = SourceRegistry.__new__(SourceRegistry)
        registry._sources = {
            "rss_source": _make_source(id="rss_source", ingestion_type="rss", supported_categories=["IT"]),
            "api_source": _make_source(id="api_source", ingestion_type="api", supported_categories=["IT"]),
            "web_source": _make_source(id="web_source", ingestion_type="web_crawl", supported_categories=["IT"]),
        }
        registry._tier_definitions = {}
        return registry

    def test_create_connector_rss(self):
        registry = self._make_registry()
        engine = IngestionEngine(registry)
        source = _make_source(ingestion_type="rss")
        connector = engine._create_connector(source)
        assert isinstance(connector, RSSConnector)

    def test_create_connector_api(self):
        registry = self._make_registry()
        engine = IngestionEngine(registry, api_credentials={"test_rss": {"api_key": "k", "api_secret": "s"}})
        source = _make_source(ingestion_type="api")
        connector = engine._create_connector(source)
        assert isinstance(connector, APIConnector)

    def test_create_connector_webcrawl_returns_none(self):
        registry = self._make_registry()
        engine = IngestionEngine(registry)
        source = _make_source(ingestion_type="web_crawl")
        connector = engine._create_connector(source)
        assert connector is None

    def test_create_connector_unknown_returns_none(self):
        registry = self._make_registry()
        engine = IngestionEngine(registry)
        source = _make_source(ingestion_type="unknown_type")
        connector = engine._create_connector(source)
        assert connector is None

    def test_collect_no_sources(self):
        """소스가 없으면 빈 리스트 반환."""
        registry = SourceRegistry.__new__(SourceRegistry)
        registry._sources = {}
        registry._tier_definitions = {}
        engine = IngestionEngine(registry)
        query = QuerySpec.create_default({"locale": "ko_KR", "limit": 20})
        query.category = ["비존재카테고리"]
        result = engine.collect(query)
        assert result == []
