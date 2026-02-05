"""RequestParser E2E 테스트"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_collector.parsers.request_parser import RequestParser
from news_collector.utils.config_manager import ConfigManager

TZ = ZoneInfo("Asia/Seoul")
REF_TIME = datetime(2026, 2, 5, 14, 0, 0, tzinfo=TZ)


@pytest.fixture
def parser(config_manager: ConfigManager):
    """RequestParser 인스턴스."""
    return RequestParser(config=config_manager, reference_time=REF_TIME)


class TestStringInput:
    """자연어 문자열 입력 테스트."""

    def test_simple_query(self, parser: RequestParser) -> None:
        """간단한 자연어 쿼리."""
        q = parser.parse("어제 정치 뉴스 Top 10")
        assert q.date_from is not None
        assert q.date_from.day == 4
        assert q.category == ["정치"]
        assert q.limit == 10

    def test_keyword_query(self, parser: RequestParser) -> None:
        """키워드 포함 쿼리."""
        q = parser.parse("AI 관련 뉴스 20개")
        assert q.keywords is not None
        assert "AI" in q.keywords
        assert q.limit == 20

    def test_trending_query(self, parser: RequestParser) -> None:
        """트렌딩 쿼리."""
        q = parser.parse("화제의 경제 뉴스")
        assert q.popularity_type == "trending"
        assert "경제" in q.category

    def test_empty_string(self, parser: RequestParser) -> None:
        """빈 문자열도 기본값으로 처리."""
        q = parser.parse("")
        assert q.limit == 20
        assert q.popularity_type == "latest"


class TestDictInput:
    """딕셔너리 입력 테스트."""

    def test_basic_dict(self, parser: RequestParser) -> None:
        """기본 딕셔너리."""
        q = parser.parse({
            "keywords": ["AI", "기술"],
            "category": "IT",
            "limit": 30,
        })
        assert q.keywords == ["AI", "기술"]
        assert q.category == ["IT"]
        assert q.limit == 30

    def test_full_dict(self, parser: RequestParser) -> None:
        """전체 필드 딕셔너리."""
        q = parser.parse({
            "date_from": "2026-02-01",
            "date_to": "2026-02-05",
            "keywords": ["AI"],
            "category": "경제",
            "limit": 50,
            "sort_by": "quality",
            "group_by": "day",
            "verified_sources_only": True,
        })
        assert q.date_from.day == 1
        assert q.date_to.day == 5
        assert q.popularity_type == "quality"
        assert q.verified_sources_only is True

    def test_empty_dict(self, parser: RequestParser) -> None:
        """빈 딕셔너리는 기본값."""
        q = parser.parse({})
        assert q.limit == 20
        assert q.locale == "ko_KR"


class TestErrorHandling:
    """오류 처리 테스트."""

    def test_invalid_input_type(self, parser: RequestParser) -> None:
        """지원하지 않는 입력 타입."""
        with pytest.raises(ValueError, match="지원하지 않는 입력 타입"):
            parser.parse(12345)

    def test_invalid_limit_in_dict(self, parser: RequestParser) -> None:
        """유효하지 않은 limit 값."""
        with pytest.raises(ValueError, match="검증 실패"):
            parser.parse({"limit": 0})

    def test_negative_offset_in_dict(self, parser: RequestParser) -> None:
        """음수 offset."""
        with pytest.raises(ValueError, match="검증 실패"):
            parser.parse({"offset": -1})


class TestDefaults:
    """기본값 적용 테스트."""

    def test_defaults_applied(self, parser: RequestParser) -> None:
        """기본값이 올바르게 적용."""
        q = parser.parse("뉴스")
        assert q.locale == "ko_KR"
        assert q.timezone == "Asia/Seoul"
        assert q.country == "KR"
        assert q.language == "ko"
        assert q.diversity is True
