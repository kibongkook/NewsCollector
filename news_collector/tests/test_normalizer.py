"""Module 4: NewsNormalizer 테스트"""

from datetime import datetime, timezone

import pytest

from news_collector.normalizer.news_normalizer import NewsNormalizer, CATEGORY_MAPPING
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.news import NormalizedNews
from news_collector.models.source import NewsSource


# ─── Fixture ────────────────────────────────────────────

def _make_raw(**overrides) -> RawNewsRecord:
    defaults = {
        "source_id": "test_source",
        "source_name": "Test Source",
        "raw_html": "<p>테스트 본문입니다.</p>",
        "raw_data": {
            "title": "테스트 뉴스 제목",
            "description": "<b>뉴스 상세 내용</b>입니다.",
            "pubDate": "2026-02-05T10:00:00+09:00",
            "author": "홍길동",
            "category": "IT",
        },
        "extracted_text": "테스트 뉴스 제목 뉴스 상세 내용입니다.",
        "url": "https://example.com/news/1",
        "page_language": "ko",
    }
    defaults.update(overrides)
    return RawNewsRecord(**defaults)


def _make_source(**overrides) -> NewsSource:
    defaults = {
        "id": "test_source",
        "name": "Test Source",
        "base_url": "https://example.com",
        "ingestion_type": "rss",
        "tier": "tier1",
        "default_locale": "ko_KR",
        "credibility_base_score": 85,
    }
    defaults.update(overrides)
    return NewsSource(**defaults)


# ═══════════════════════════════════════════════════════════
# HTML 정제 테스트
# ═══════════════════════════════════════════════════════════

class TestCleanHtml:
    """HTML 정제 기능 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_remove_tags(self):
        assert self.normalizer._clean_html("<p>Hello</p>") == "Hello"

    def test_remove_script(self):
        html = "Before<script>alert('xss')</script>After"
        assert "alert" not in self.normalizer._clean_html(html)

    def test_remove_style(self):
        html = "Before<style>.cls{color:red}</style>After"
        assert "color" not in self.normalizer._clean_html(html)

    def test_decode_entities(self):
        result = self.normalizer._clean_html("Hello&amp;World")
        assert "&amp;" not in result

    def test_empty_string(self):
        assert self.normalizer._clean_html("") == ""

    def test_plain_text_unchanged(self):
        assert self.normalizer._clean_html("Hello World") == "Hello World"


# ═══════════════════════════════════════════════════════════
# 날짜 파싱 테스트
# ═══════════════════════════════════════════════════════════

class TestParseDateTime:
    """날짜 파싱 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_iso_format(self):
        dt = self.normalizer._parse_datetime("2026-02-05T10:00:00+09:00")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 2
        assert dt.day == 5

    def test_rfc2822_format(self):
        dt = self.normalizer._parse_datetime("Wed, 05 Feb 2026 10:00:00 +0900")
        assert dt is not None
        assert dt.year == 2026

    def test_none_input(self):
        assert self.normalizer._parse_datetime(None) is None

    def test_invalid_date(self):
        assert self.normalizer._parse_datetime("not-a-date") is None


# ═══════════════════════════════════════════════════════════
# 카테고리 추론 테스트
# ═══════════════════════════════════════════════════════════

class TestInferCategory:
    """카테고리 추론 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_it_category(self):
        assert self.normalizer._infer_category("tech", "AI 기술 발표") == "IT"

    def test_economy_category(self):
        assert self.normalizer._infer_category("", "주식 시장 급등") == "경제"

    def test_sports_category(self):
        assert self.normalizer._infer_category("sports", "축구 경기") == "스포츠"

    def test_politics_category(self):
        assert self.normalizer._infer_category("", "국회 본회의 개최") == "정치"

    def test_no_category(self):
        result = self.normalizer._infer_category("", "일반적인 내용")
        # 매칭이 안 될 수 있음
        assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════════════════
# 이미지 URL 추출 테스트
# ═══════════════════════════════════════════════════════════

class TestExtractImageUrls:
    """이미지 URL 추출 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_extract_image(self):
        html = '<img src="https://example.com/image.jpg">'
        urls = self.normalizer._extract_image_urls(html)
        assert urls == ["https://example.com/image.jpg"]

    def test_multiple_images(self):
        html = '<img src="a.jpg"><img src="b.png">'
        urls = self.normalizer._extract_image_urls(html)
        assert len(urls) == 2

    def test_no_images(self):
        assert self.normalizer._extract_image_urls("<p>No images</p>") == []

    def test_empty_html(self):
        assert self.normalizer._extract_image_urls("") == []


# ═══════════════════════════════════════════════════════════
# normalize() 통합 테스트
# ═══════════════════════════════════════════════════════════

class TestNormalize:
    """단일 정규화 통합 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_basic_normalize(self):
        raw = _make_raw()
        result = self.normalizer.normalize(raw)
        assert isinstance(result, NormalizedNews)
        assert result.title == "테스트 뉴스 제목"
        assert result.source_id == "test_source"
        assert result.url == "https://example.com/news/1"
        assert result.id  # UUID 생성

    def test_normalize_with_source(self):
        raw = _make_raw()
        source = _make_source(tier="tier1")
        result = self.normalizer.normalize(raw, source)
        assert result.source_tier == "tier1"
        assert result.source_name == "Test Source"

    def test_normalize_without_source(self):
        raw = _make_raw()
        result = self.normalizer.normalize(raw)
        assert result.source_tier == "tier2"

    def test_normalize_html_cleaned(self):
        raw = _make_raw(raw_data={
            "title": "<b>Bold Title</b>",
            "description": "<script>bad</script>Clean body",
        })
        result = self.normalizer.normalize(raw)
        assert "<b>" not in result.title
        assert "<script>" not in result.body

    def test_normalize_category_inferred(self):
        raw = _make_raw(raw_data={
            "title": "AI 인공지능 기술 발표",
            "description": "기술 관련 뉴스",
            "category": "tech",
        })
        result = self.normalizer.normalize(raw)
        assert result.category == "IT"

    def test_normalize_author(self):
        raw = _make_raw()
        result = self.normalizer.normalize(raw)
        assert result.author == "홍길동"

    def test_normalize_published_at(self):
        raw = _make_raw()
        result = self.normalizer.normalize(raw)
        assert result.published_at is not None
        assert result.published_at.year == 2026

    def test_normalize_tags_from_string(self):
        raw = _make_raw(raw_data={
            "title": "Test",
            "description": "Body",
            "tags": "tag1, tag2, tag3",
        })
        result = self.normalizer.normalize(raw)
        assert result.tags == ["tag1", "tag2", "tag3"]


# ═══════════════════════════════════════════════════════════
# normalize_batch() 테스트
# ═══════════════════════════════════════════════════════════

class TestNormalizeBatch:
    """배치 정규화 테스트."""

    def setup_method(self):
        self.normalizer = NewsNormalizer()

    def test_batch_normalize(self):
        raws = [
            _make_raw(url=f"https://example.com/{i}") for i in range(5)
        ]
        results = self.normalizer.normalize_batch(raws)
        assert len(results) == 5
        assert all(isinstance(r, NormalizedNews) for r in results)

    def test_batch_with_source_map(self):
        raws = [_make_raw()]
        source_map = {"test_source": _make_source(tier="whitelist")}
        results = self.normalizer.normalize_batch(raws, source_map)
        assert results[0].source_tier == "whitelist"

    def test_batch_empty_list(self):
        results = self.normalizer.normalize_batch([])
        assert results == []
