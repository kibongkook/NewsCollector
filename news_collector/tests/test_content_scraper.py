"""content_scraper 테스트"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import replace

from news_collector.ingestion.content_scraper import (
    ContentScraper,
    ContentScraperConfig,
    ScrapedContent,
    NewsSimilarityDetector,
    NewsMerger,
    SimilarNewsGroup,
    scrape_full_content,
    enrich_news_with_full_body,
)
from news_collector.models.news import NewsWithScores


# ============================================================
# ContentScraper 테스트
# ============================================================

class TestScrapedContent:
    """ScrapedContent 데이터클래스 테스트"""

    def test_defaults(self):
        content = ScrapedContent(url="https://example.com", full_body="")
        assert content.url == "https://example.com"
        assert content.full_body == ""
        assert content.title is None
        assert content.success is False
        assert content.error is None
        assert content.response_time_ms == 0

    def test_with_values(self):
        content = ScrapedContent(
            url="https://example.com",
            full_body="Full article content",
            title="Article Title",
            success=True,
            response_time_ms=150,
        )
        assert content.success is True
        assert content.title == "Article Title"
        assert content.response_time_ms == 150


class TestContentScraperConfig:
    """ContentScraperConfig 테스트"""

    def test_defaults(self):
        config = ContentScraperConfig()
        assert config.min_body_length_for_scrape == 150
        assert config.timeout == 10
        assert config.request_delay == 0.5
        assert config.max_retries == 2
        assert config.enable_cache is True
        assert config.cache_ttl_seconds == 3600


class TestContentScraper:
    """ContentScraper 테스트"""

    def test_init(self):
        scraper = ContentScraper()
        assert scraper.config is not None
        assert scraper._cache == {}

    def test_should_scrape_short_body(self):
        scraper = ContentScraper()
        assert scraper.should_scrape("짧은 본문") is True
        assert scraper.should_scrape("이것은 150자 이상의 본문입니다. " * 10) is False

    def test_empty_url(self):
        scraper = ContentScraper()
        result = scraper.scrape("")
        assert result.success is False
        assert "비어있음" in result.error

    @patch("news_collector.ingestion.content_scraper.ContentScraper._check_trafilatura")
    def test_trafilatura_not_available(self, mock_check):
        mock_check.return_value = False
        scraper = ContentScraper()
        result = scraper.scrape("https://example.com")
        assert result.success is False
        assert "trafilatura" in result.error

    def test_cache_operations(self):
        scraper = ContentScraper()
        content = ScrapedContent(
            url="https://example.com",
            full_body="Cached content",
            success=True,
        )
        scraper._save_to_cache("https://example.com", content)

        cached = scraper._get_from_cache("https://example.com")
        assert cached is not None
        assert cached.full_body == "Cached content"

        scraper.clear_cache()
        assert scraper._get_from_cache("https://example.com") is None


# ============================================================
# NewsSimilarityDetector 테스트
# ============================================================

class TestNewsSimilarityDetector:
    """NewsSimilarityDetector 테스트"""

    @pytest.fixture
    def sample_news_list(self):
        return [
            NewsWithScores(
                id="news1",
                title="삼성전자 반도체 투자 10조원 발표",
                body="삼성전자가 반도체에 대규모 투자를 발표했다.",
            ),
            NewsWithScores(
                id="news2",
                title="삼성전자 반도체 사업 투자 확대",
                body="삼성전자가 반도체 사업에 투자를 확대한다.",
            ),
            NewsWithScores(
                id="news3",
                title="현대차 전기차 시장 진출 가속화",
                body="현대차가 전기차 시장에서 점유율을 높이고 있다.",
            ),
        ]

    def test_init(self):
        detector = NewsSimilarityDetector()
        assert detector.title_threshold == 0.6
        assert detector.body_threshold == 0.5
        assert detector.combined_threshold == 0.55

    def test_find_similar_groups(self, sample_news_list):
        detector = NewsSimilarityDetector(combined_threshold=0.3)
        groups = detector.find_similar_groups(sample_news_list)

        # 삼성 관련 뉴스가 그룹화되어야 함
        assert len(groups) >= 1

    def test_find_similar_groups_empty(self):
        detector = NewsSimilarityDetector()
        groups = detector.find_similar_groups([])
        assert groups == []

    def test_find_similar_groups_single(self):
        detector = NewsSimilarityDetector()
        news = NewsWithScores(id="news1", title="단일 뉴스", body="본문")
        groups = detector.find_similar_groups([news])
        assert groups == []

    def test_tokenize(self):
        detector = NewsSimilarityDetector()
        tokens = detector._tokenize("삼성전자 Samsung 반도체 123")
        assert "삼성전자" in tokens
        assert "samsung" in [t.lower() for t in tokens]

    def test_jaccard_similarity(self):
        detector = NewsSimilarityDetector()

        # 동일한 텍스트
        assert detector._jaccard_similarity("삼성 전자", "삼성 전자") == 1.0

        # 부분 일치
        sim = detector._jaccard_similarity("삼성 전자 반도체", "삼성 전자 자동차")
        assert 0 < sim < 1

        # 완전 다름
        sim = detector._jaccard_similarity("삼성 전자", "현대 자동차")
        assert sim < 0.5


# ============================================================
# NewsMerger 테스트
# ============================================================

class TestNewsMerger:
    """NewsMerger 테스트"""

    @pytest.fixture
    def similar_news_list(self):
        return [
            NewsWithScores(
                id="news1",
                title="경제 성장률 발표",
                body="올해 경제 성장률이 3%로 발표되었다. 전문가들은 긍정적으로 평가했다.",
            ),
            NewsWithScores(
                id="news2",
                title="경제 성장률 3% 달성",
                body="경제 성장률 3% 달성. 내년에는 더 높은 성장이 예상된다.",
            ),
        ]

    def test_init(self):
        merger = NewsMerger()
        assert merger.similarity_detector is not None

    def test_merge_similar_news_empty(self):
        merger = NewsMerger()
        result = merger.merge_similar_news([])
        assert result == []

    def test_merge_similar_news_single(self):
        merger = NewsMerger()
        news = NewsWithScores(id="news1", title="단일 뉴스", body="본문")
        result = merger.merge_similar_news([news])
        assert len(result) == 1
        assert result[0].id == "news1"

    def test_merge_bodies(self):
        merger = NewsMerger()
        bodies = [
            "첫 번째 문장입니다. 두 번째 문장입니다.",
            "첫 번째 문장입니다. 세 번째 문장입니다.",  # 첫 번째 중복
        ]
        merged = merger._merge_bodies(bodies)
        # 중복 제거 후 3개 문장
        assert "첫 번째" in merged
        assert "두 번째" in merged
        assert "세 번째" in merged


# ============================================================
# 편의 함수 테스트
# ============================================================

class TestConvenienceFunctions:
    """편의 함수 테스트"""

    @patch("news_collector.ingestion.content_scraper.ContentScraper.scrape")
    def test_scrape_full_content(self, mock_scrape):
        mock_scrape.return_value = ScrapedContent(
            url="https://example.com",
            full_body="Full content",
            success=True,
        )
        result = scrape_full_content("https://example.com")
        assert result.success is True
        mock_scrape.assert_called_once()

    def test_enrich_news_with_full_body_empty(self):
        result = enrich_news_with_full_body([])
        assert result == []

    @patch("news_collector.ingestion.content_scraper.ContentScraper.scrape")
    def test_enrich_news_with_full_body_long_enough(self, mock_scrape):
        # 본문이 충분히 길면 스크래핑 안 함
        news = NewsWithScores(
            id="news1",
            title="테스트",
            body="이것은 150자 이상의 충분히 긴 본문입니다. " * 10,
            url="https://example.com",
        )
        result = enrich_news_with_full_body([news])
        assert len(result) == 1
        mock_scrape.assert_not_called()

    @patch("news_collector.ingestion.content_scraper.ContentScraper.scrape")
    def test_enrich_news_with_full_body_short(self, mock_scrape):
        mock_scrape.return_value = ScrapedContent(
            url="https://example.com",
            full_body="확장된 본문입니다. " * 20,
            success=True,
        )
        news = NewsWithScores(
            id="news1",
            title="테스트",
            body="짧은 본문",
            url="https://example.com",
        )
        result = enrich_news_with_full_body([news])
        assert len(result) == 1
        assert len(result[0].body) > len("짧은 본문")


# ============================================================
# SimilarNewsGroup 테스트
# ============================================================

class TestSimilarNewsGroup:
    """SimilarNewsGroup 데이터클래스 테스트"""

    def test_creation(self):
        group = SimilarNewsGroup(
            primary_news_id="news1",
            similar_news_ids=["news2", "news3"],
            similarity_scores={"news2": 0.8, "news3": 0.7},
        )
        assert group.primary_news_id == "news1"
        assert len(group.similar_news_ids) == 2
        assert group.similarity_scores["news2"] == 0.8
