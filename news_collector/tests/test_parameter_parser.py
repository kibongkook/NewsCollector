"""ParameterParser 테스트"""

from datetime import datetime

import pytest

from news_collector.parsers.parameter_parser import ParameterParser


@pytest.fixture
def parser(defaults):
    """ParameterParser 인스턴스."""
    return ParameterParser(defaults=defaults)


class TestFullDict:
    """전체 필드 딕셔너리 테스트."""

    def test_full_parameters(self, parser: ParameterParser) -> None:
        """모든 필드가 포함된 입력."""
        params = {
            "date_from": "2026-02-01",
            "date_to": "2026-02-05",
            "keywords": ["AI", "기술"],
            "category": "경제",
            "limit": 50,
            "sort_by": "quality",
            "group_by": "day",
        }
        q = parser.parse(params)
        assert q.date_from.year == 2026
        assert q.date_from.month == 2
        assert q.date_from.day == 1
        assert q.date_to.day == 5
        assert q.keywords == ["AI", "기술"]
        assert q.category == ["경제"]
        assert q.limit == 50
        assert q.popularity_type == "quality"
        assert q.group_by == "day"

    def test_minimal_parameters(self, parser: ParameterParser) -> None:
        """최소 필드만 포함."""
        params = {"keywords": ["AI"]}
        q = parser.parse(params)
        assert q.keywords == ["AI"]
        assert q.limit == 20  # 기본값
        assert q.locale == "ko_KR"  # 기본값


class TestDateParsing:
    """날짜 필드 파싱 테스트."""

    def test_date_string_iso(self, parser: ParameterParser) -> None:
        """ISO 형식 문자열."""
        params = {"date_from": "2026-02-01"}
        q = parser.parse(params)
        assert q.date_from.year == 2026

    def test_date_string_with_time(self, parser: ParameterParser) -> None:
        """시간 포함 문자열."""
        params = {"date_from": "2026-02-01T10:00:00"}
        q = parser.parse(params)
        assert q.date_from.hour == 10

    def test_date_datetime_object(self, parser: ParameterParser) -> None:
        """datetime 객체 그대로."""
        dt = datetime(2026, 2, 1)
        params = {"date_from": dt}
        q = parser.parse(params)
        assert q.date_from == dt

    def test_date_invalid_returns_none(self, parser: ParameterParser) -> None:
        """유효하지 않은 날짜 문자열."""
        params = {"date_from": "not-a-date"}
        q = parser.parse(params)
        assert q.date_from is None

    def test_date_none(self, parser: ParameterParser) -> None:
        """None은 None 유지."""
        params = {}
        q = parser.parse(params)
        assert q.date_from is None


class TestListParsing:
    """리스트 필드 파싱 테스트."""

    def test_list_input(self, parser: ParameterParser) -> None:
        """리스트 그대로."""
        params = {"keywords": ["A", "B"]}
        q = parser.parse(params)
        assert q.keywords == ["A", "B"]

    def test_string_comma_separated(self, parser: ParameterParser) -> None:
        """쉼표 구분 문자열."""
        params = {"keywords": "A, B, C"}
        q = parser.parse(params)
        assert q.keywords == ["A", "B", "C"]

    def test_single_string(self, parser: ParameterParser) -> None:
        """단일 문자열."""
        params = {"category": "정치"}
        q = parser.parse(params)
        assert q.category == ["정치"]

    def test_none_returns_none(self, parser: ParameterParser) -> None:
        """None은 None."""
        params = {}
        q = parser.parse(params)
        assert q.keywords is None


class TestTypeParsing:
    """타입 변환 테스트."""

    def test_int_from_string(self, parser: ParameterParser) -> None:
        """문자열에서 정수 변환."""
        params = {"limit": "50"}
        q = parser.parse(params)
        assert q.limit == 50

    def test_int_invalid_uses_default(self, parser: ParameterParser) -> None:
        """유효하지 않은 정수는 기본값."""
        params = {"limit": "abc"}
        q = parser.parse(params)
        assert q.limit == 20

    def test_bool_true_string(self, parser: ParameterParser) -> None:
        """'true' 문자열."""
        params = {"verified_sources_only": "true"}
        q = parser.parse(params)
        assert q.verified_sources_only is True

    def test_bool_false_string(self, parser: ParameterParser) -> None:
        """'false' 문자열."""
        params = {"verified_sources_only": "false"}
        q = parser.parse(params)
        assert q.verified_sources_only is False

    def test_bool_native(self, parser: ParameterParser) -> None:
        """네이티브 bool."""
        params = {"diversity": True}
        q = parser.parse(params)
        assert q.diversity is True


class TestValidation:
    """유효성 검증 테스트."""

    def test_invalid_popularity_type_uses_default(self, parser: ParameterParser) -> None:
        """유효하지 않은 popularity_type은 기본값."""
        params = {"popularity_type": "invalid"}
        q = parser.parse(params)
        assert q.popularity_type == "latest"

    def test_invalid_group_by_uses_default(self, parser: ParameterParser) -> None:
        """유효하지 않은 group_by는 기본값."""
        params = {"group_by": "invalid"}
        q = parser.parse(params)
        assert q.group_by == "none"

    def test_unknown_keys_ignored(self, parser: ParameterParser) -> None:
        """알 수 없는 키는 무시."""
        params = {"unknown_key": "value", "keywords": ["test"]}
        q = parser.parse(params)
        assert q.keywords == ["test"]
