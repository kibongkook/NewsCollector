"""NaturalLanguageParser 테스트"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_collector.parsers.natural_language_parser import NaturalLanguageParser

TZ = ZoneInfo("Asia/Seoul")
REF_TIME = datetime(2026, 2, 5, 14, 0, 0, tzinfo=TZ)


@pytest.fixture
def parser(nl_config, defaults):
    """NaturalLanguageParser 인스턴스."""
    return NaturalLanguageParser(
        nl_config=nl_config,
        defaults=defaults,
        reference_time=REF_TIME,
    )


class TestIntentExtraction:
    """의도 추출 테스트."""

    def test_trending_intent(self, parser: NaturalLanguageParser) -> None:
        """트렌딩 의도 매칭."""
        q = parser.parse("화제의 뉴스")
        assert q.popularity_type == "trending"

    def test_popular_intent(self, parser: NaturalLanguageParser) -> None:
        """인기 의도 매칭."""
        q = parser.parse("가장 많이 본 뉴스")
        assert q.popularity_type == "popular"

    def test_quality_intent(self, parser: NaturalLanguageParser) -> None:
        """품질 의도 매칭."""
        q = parser.parse("양질의 뉴스")
        assert q.popularity_type == "quality"

    def test_latest_intent(self, parser: NaturalLanguageParser) -> None:
        """최신 의도 매칭."""
        q = parser.parse("최신 뉴스")
        assert q.popularity_type == "latest"

    def test_no_intent_defaults_to_latest(self, parser: NaturalLanguageParser) -> None:
        """의도 없으면 기본값 (latest)."""
        q = parser.parse("뉴스 보여줘")
        assert q.popularity_type == "latest"


class TestDateExtraction:
    """날짜 추출 테스트."""

    def test_yesterday(self, parser: NaturalLanguageParser) -> None:
        """'어제' 날짜 추출."""
        q = parser.parse("어제 뉴스")
        assert q.date_from is not None
        assert q.date_from.day == 4

    def test_date_range(self, parser: NaturalLanguageParser) -> None:
        """날짜 범위 추출."""
        q = parser.parse("2월 1일~5일 뉴스")
        assert q.date_from is not None
        assert q.date_to is not None
        assert q.date_from.day == 1
        assert q.date_to.day == 5


class TestCategoryExtraction:
    """카테고리 추출 테스트."""

    def test_single_category(self, parser: NaturalLanguageParser) -> None:
        """단일 카테고리."""
        q = parser.parse("정치 뉴스")
        assert q.category == ["정치"]

    def test_multiple_categories(self, parser: NaturalLanguageParser) -> None:
        """복수 카테고리."""
        q = parser.parse("경제 IT 뉴스")
        assert "경제" in q.category
        assert "IT" in q.category

    def test_category_by_keyword(self, parser: NaturalLanguageParser) -> None:
        """카테고리 키워드로 매칭."""
        q = parser.parse("주식 관련 뉴스")
        assert q.category is not None
        assert "경제" in q.category

    def test_no_category(self, parser: NaturalLanguageParser) -> None:
        """카테고리 없음."""
        q = parser.parse("뉴스 보여줘")
        assert q.category is None


class TestKeywordExtraction:
    """키워드 추출 테스트."""

    def test_keyword_with_관련(self, parser: NaturalLanguageParser) -> None:
        """'X 관련' 패턴."""
        q = parser.parse("AI 관련 뉴스")
        assert q.keywords is not None
        assert "AI" in q.keywords

    def test_keyword_with_에대한(self, parser: NaturalLanguageParser) -> None:
        """'X에 대한' 패턴."""
        q = parser.parse("반도체에 대한 뉴스")
        assert q.keywords is not None
        assert "반도체" in q.keywords

    def test_no_keywords(self, parser: NaturalLanguageParser) -> None:
        """키워드 없음."""
        q = parser.parse("오늘 뉴스")
        assert q.keywords is None


class TestExcludeKeywords:
    """제외 키워드 테스트."""

    def test_exclude_with_제외(self, parser: NaturalLanguageParser) -> None:
        """'X 제외' 패턴."""
        q = parser.parse("연예 제외 뉴스")
        assert q.exclude_keywords is not None
        assert "연예" in q.exclude_keywords

    def test_exclude_with_빼고(self, parser: NaturalLanguageParser) -> None:
        """'X 빼고' 패턴."""
        q = parser.parse("스포츠 빼고 뉴스")
        assert q.exclude_keywords is not None
        assert "스포츠" in q.exclude_keywords


class TestLimitExtraction:
    """결과 수 추출 테스트."""

    def test_top_n(self, parser: NaturalLanguageParser) -> None:
        """'Top N' 패턴."""
        q = parser.parse("정치 뉴스 Top 10")
        assert q.limit == 10

    def test_n_개(self, parser: NaturalLanguageParser) -> None:
        """'N개' 패턴."""
        q = parser.parse("뉴스 20개")
        assert q.limit == 20

    def test_n_건(self, parser: NaturalLanguageParser) -> None:
        """'N건' 패턴."""
        q = parser.parse("뉴스 30건")
        assert q.limit == 30

    def test_no_limit_uses_default(self, parser: NaturalLanguageParser) -> None:
        """limit 없으면 기본값."""
        q = parser.parse("뉴스")
        assert q.limit == 20


class TestOptionExtraction:
    """옵션 추출 테스트."""

    def test_verified_sources(self, parser: NaturalLanguageParser) -> None:
        """검증된 소스 옵션."""
        q = parser.parse("검증된 소스 뉴스")
        assert q.verified_sources_only is True

    def test_diversity(self, parser: NaturalLanguageParser) -> None:
        """다양성 옵션."""
        q = parser.parse("다양한 소스 뉴스")
        assert q.diversity is True


class TestCombinedParsing:
    """복합 쿼리 테스트."""

    def test_full_query(self, parser: NaturalLanguageParser) -> None:
        """기획서 예시: '어제 정치 뉴스 Top 10'"""
        q = parser.parse("어제 정치 뉴스 Top 10")
        assert q.date_from is not None
        assert q.date_from.day == 4
        assert q.category == ["정치"]
        assert q.limit == 10

    def test_date_range_with_keyword(self, parser: NaturalLanguageParser) -> None:
        """기획서 예시: '2월 1일~5일 동안 AI 관련 뉴스'"""
        q = parser.parse("2월 1일~5일 동안 AI 관련 뉴스")
        assert q.date_from is not None
        assert q.date_from.day == 1
        assert q.date_to.day == 5
        assert q.keywords is not None
        assert "AI" in q.keywords

    def test_popular_science_week(self, parser: NaturalLanguageParser) -> None:
        """기획서 예시: '지난 1주일간 가장 많이 본 과학 뉴스'"""
        q = parser.parse("지난 1주일간 가장 많이 본 과학 뉴스")
        assert q.date_from is not None
        assert q.popularity_type == "popular"
        assert q.category is not None
        assert "과학" in q.category
