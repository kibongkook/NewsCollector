"""Module 5: DeduplicationEngine 테스트"""

import pytest

from news_collector.dedup.dedup_engine import DeduplicationEngine
from news_collector.models.news import NormalizedNews


# ─── Fixture ────────────────────────────────────────────

def _make_news(
    id: str = "1",
    title: str = "테스트 뉴스 제목",
    body: str = "테스트 본문 내용입니다.",
    url: str = "https://example.com/1",
    source_id: str = "source_a",
) -> NormalizedNews:
    return NormalizedNews(
        id=id,
        title=title,
        body=body,
        url=url,
        source_id=source_id,
    )


# ═══════════════════════════════════════════════════════════
# URL 정규화 테스트
# ═══════════════════════════════════════════════════════════

class TestNormalizeUrl:
    """URL 정규화 테스트."""

    def test_strip_query_params(self):
        result = DeduplicationEngine._normalize_url("https://example.com/article?ref=twitter&id=123")
        assert result == "https://example.com/article"

    def test_strip_fragment(self):
        result = DeduplicationEngine._normalize_url("https://example.com/article#section1")
        assert result == "https://example.com/article"

    def test_lowercase(self):
        result = DeduplicationEngine._normalize_url("https://Example.COM/Article")
        assert result == "https://example.com/article"

    def test_strip_trailing_slash(self):
        result = DeduplicationEngine._normalize_url("https://example.com/article/")
        assert result == "https://example.com/article"


# ═══════════════════════════════════════════════════════════
# Jaccard 유사도 테스트
# ═══════════════════════════════════════════════════════════

class TestJaccardSimilarity:
    """Jaccard 유사도 테스트."""

    def test_identical_strings(self):
        sim = DeduplicationEngine._jaccard_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different(self):
        sim = DeduplicationEngine._jaccard_similarity("hello world", "foo bar baz")
        assert sim == 0.0

    def test_partial_overlap(self):
        sim = DeduplicationEngine._jaccard_similarity("AI 기술 혁신", "AI 기술 발전")
        assert 0.0 < sim < 1.0

    def test_empty_string(self):
        sim = DeduplicationEngine._jaccard_similarity("", "hello")
        assert sim == 0.0

    def test_both_empty(self):
        sim = DeduplicationEngine._jaccard_similarity("", "")
        assert sim == 0.0


# ═══════════════════════════════════════════════════════════
# URL 기반 중복 제거 테스트
# ═══════════════════════════════════════════════════════════

class TestDedupByUrl:
    """URL 기반 중복 제거 테스트."""

    def setup_method(self):
        self.engine = DeduplicationEngine()

    def test_exact_url_dedup(self):
        news_list = [
            _make_news(id="1", url="https://example.com/1"),
            _make_news(id="2", url="https://example.com/1"),
        ]
        result = self.engine._dedup_by_url(news_list)
        assert len(result) == 1

    def test_url_with_different_params(self):
        news_list = [
            _make_news(id="1", url="https://example.com/1?ref=a"),
            _make_news(id="2", url="https://example.com/1?ref=b"),
        ]
        result = self.engine._dedup_by_url(news_list)
        assert len(result) == 1

    def test_different_urls_kept(self):
        news_list = [
            _make_news(id="1", url="https://example.com/1"),
            _make_news(id="2", url="https://example.com/2"),
        ]
        result = self.engine._dedup_by_url(news_list)
        assert len(result) == 2


# ═══════════════════════════════════════════════════════════
# 제목 해시 중복 제거 테스트
# ═══════════════════════════════════════════════════════════

class TestDedupByTitleHash:
    """제목 해시 기반 중복 제거 테스트."""

    def setup_method(self):
        self.engine = DeduplicationEngine()

    def test_same_title_dedup(self):
        news_list = [
            _make_news(id="1", title="동일한 뉴스 제목", url="https://a.com/1"),
            _make_news(id="2", title="동일한 뉴스 제목", url="https://b.com/2"),
        ]
        result = self.engine._dedup_by_title_hash(news_list)
        assert len(result) == 1

    def test_different_titles_kept(self):
        news_list = [
            _make_news(id="1", title="제목 A"),
            _make_news(id="2", title="제목 B"),
        ]
        result = self.engine._dedup_by_title_hash(news_list)
        assert len(result) == 2

    def test_case_insensitive(self):
        news_list = [
            _make_news(id="1", title="Hello World", url="https://a.com/1"),
            _make_news(id="2", title="hello world", url="https://b.com/2"),
        ]
        result = self.engine._dedup_by_title_hash(news_list)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════
# 클러스터링 테스트
# ═══════════════════════════════════════════════════════════

class TestClusterSimilar:
    """유사도 기반 클러스터링 테스트."""

    def setup_method(self):
        self.engine = DeduplicationEngine(similarity_threshold=0.6)

    def test_similar_articles_clustered(self):
        news_list = [
            _make_news(id="1", title="AI 인공지능 기술 혁신 발표", body="긴 본문" * 50, url="https://a.com/1", source_id="a"),
            _make_news(id="2", title="AI 인공지능 기술 혁신 발견", body="짧은 본문", url="https://b.com/2", source_id="b"),
        ]
        result = self.engine._cluster_similar(news_list)
        assert len(result) == 1
        assert result[0].cluster_id is not None  # 클러스터 ID 부여
        assert result[0].id == "1"  # 긴 본문이 대표

    def test_dissimilar_articles_not_clustered(self):
        news_list = [
            _make_news(id="1", title="AI 인공지능 기술 혁신", url="https://a.com/1"),
            _make_news(id="2", title="한국 경제 전망 보고서", url="https://b.com/2"),
        ]
        result = self.engine._cluster_similar(news_list)
        assert len(result) == 2

    def test_single_item(self):
        news_list = [_make_news(id="1")]
        result = self.engine._cluster_similar(news_list)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════
# 전체 파이프라인 테스트
# ═══════════════════════════════════════════════════════════

class TestDeduplicatePipeline:
    """전체 중복 제거 파이프라인 테스트."""

    def setup_method(self):
        self.engine = DeduplicationEngine()

    def test_empty_list(self):
        assert self.engine.deduplicate([]) == []

    def test_all_unique(self):
        news_list = [
            _make_news(id="1", title="뉴스 A", url="https://a.com/1"),
            _make_news(id="2", title="뉴스 B", url="https://b.com/2"),
            _make_news(id="3", title="뉴스 C", url="https://c.com/3"),
        ]
        result = self.engine.deduplicate(news_list)
        assert len(result) == 3

    def test_url_duplicates_removed(self):
        news_list = [
            _make_news(id="1", title="뉴스 A", url="https://a.com/1"),
            _make_news(id="2", title="뉴스 A 다른 제목", url="https://a.com/1?ref=b"),
        ]
        result = self.engine.deduplicate(news_list)
        assert len(result) == 1

    def test_title_duplicates_removed(self):
        news_list = [
            _make_news(id="1", title="동일 제목 뉴스", url="https://a.com/1"),
            _make_news(id="2", title="동일 제목 뉴스", url="https://b.com/2"),
        ]
        result = self.engine.deduplicate(news_list)
        assert len(result) == 1

    def test_mixed_duplicates(self):
        """URL 중복 + 제목 중복 + 유사 기사 모두 처리."""
        news_list = [
            _make_news(id="1", title="AI 기술 혁신 발표 내용", body="상세 본문" * 100, url="https://a.com/1"),
            _make_news(id="2", title="AI 기술 혁신 발표 내용", url="https://b.com/2"),  # 제목 중복
            _make_news(id="3", title="완전히 다른 경제 뉴스", url="https://c.com/3"),
        ]
        result = self.engine.deduplicate(news_list)
        assert len(result) == 2
