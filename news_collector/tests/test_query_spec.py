"""QuerySpec 데이터 모델 테스트"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_collector.models.query_spec import QuerySpec


class TestQuerySpecDefaults:
    """기본값 테스트."""

    def test_default_values(self) -> None:
        """기본 생성 시 올바른 기본값."""
        q = QuerySpec()
        assert q.locale == "ko_KR"
        assert q.timezone == "Asia/Seoul"
        assert q.limit == 20
        assert q.offset == 0
        assert q.popularity_type == "latest"
        assert q.group_by == "none"
        assert q.diversity is True
        assert q.verified_sources_only is False
        assert q.date_from is None
        assert q.category is None
        assert q.keywords is None

    def test_create_default_from_config(self) -> None:
        """설정 딕셔너리에서 생성."""
        config = {
            "locale": "en_US",
            "timezone": "UTC",
            "country": "US",
            "language": "en",
            "market": "en_US",
            "limit": 50,
            "popularity_type": "trending",
        }
        q = QuerySpec.create_default(config)
        assert q.locale == "en_US"
        assert q.limit == 50
        assert q.popularity_type == "trending"


class TestQuerySpecPostInit:
    """__post_init__ 테스트."""

    def test_string_category_to_list(self) -> None:
        """문자열 카테고리가 리스트로 변환."""
        q = QuerySpec(category="정치")
        assert q.category == ["정치"]

    def test_string_keywords_to_list(self) -> None:
        """문자열 키워드가 리스트로 변환."""
        q = QuerySpec(keywords="AI")
        assert q.keywords == ["AI"]

    def test_list_stays_list(self) -> None:
        """리스트는 그대로 유지."""
        q = QuerySpec(category=["정치", "경제"])
        assert q.category == ["정치", "경제"]


class TestQuerySpecValidation:
    """유효성 검사 테스트."""

    def test_valid_query(self) -> None:
        """정상 쿼리는 오류 없음."""
        q = QuerySpec(limit=10, popularity_type="trending", group_by="day")
        errors = q.validate()
        assert errors == []

    def test_invalid_limit_too_low(self) -> None:
        """limit < 1이면 오류."""
        q = QuerySpec(limit=0)
        errors = q.validate()
        assert any("limit" in e for e in errors)

    def test_invalid_limit_too_high(self) -> None:
        """limit > 100이면 오류."""
        q = QuerySpec(limit=200)
        errors = q.validate()
        assert any("limit" in e for e in errors)

    def test_invalid_offset_negative(self) -> None:
        """offset < 0이면 오류."""
        q = QuerySpec(offset=-1)
        errors = q.validate()
        assert any("offset" in e for e in errors)

    def test_invalid_popularity_type(self) -> None:
        """유효하지 않은 popularity_type."""
        q = QuerySpec(popularity_type="invalid")
        errors = q.validate()
        assert any("popularity_type" in e for e in errors)

    def test_invalid_group_by(self) -> None:
        """유효하지 않은 group_by."""
        q = QuerySpec(group_by="invalid")
        errors = q.validate()
        assert any("group_by" in e for e in errors)

    def test_date_order_invalid(self) -> None:
        """date_from > date_to이면 오류."""
        tz = ZoneInfo("Asia/Seoul")
        q = QuerySpec(
            date_from=datetime(2026, 2, 5, tzinfo=tz),
            date_to=datetime(2026, 2, 1, tzinfo=tz),
        )
        errors = q.validate()
        assert any("date_from" in e for e in errors)

    def test_date_order_valid(self) -> None:
        """date_from <= date_to이면 오류 없음."""
        tz = ZoneInfo("Asia/Seoul")
        q = QuerySpec(
            date_from=datetime(2026, 2, 1, tzinfo=tz),
            date_to=datetime(2026, 2, 5, tzinfo=tz),
        )
        errors = q.validate()
        assert errors == []

    def test_too_many_keywords(self) -> None:
        """키워드 10개 초과 시 오류."""
        q = QuerySpec(keywords=[f"kw{i}" for i in range(15)])
        errors = q.validate()
        assert any("키워드" in e for e in errors)

    def test_too_many_categories(self) -> None:
        """카테고리 5개 초과 시 오류."""
        q = QuerySpec(category=[f"cat{i}" for i in range(8)])
        errors = q.validate()
        assert any("카테고리" in e for e in errors)
