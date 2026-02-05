"""DateParser 테스트"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from news_collector.parsers.date_parser import DateParser

TZ = ZoneInfo("Asia/Seoul")
REF_TIME = datetime(2026, 2, 5, 14, 0, 0, tzinfo=TZ)


@pytest.fixture
def date_config():
    """날짜 패턴 설정."""
    return {
        "relative": {
            "오늘": {"offset_days": 0, "range_days": 1},
            "어제": {"offset_days": -1, "range_days": 1},
            "그저께": {"offset_days": -2, "range_days": 1},
            "이번 주": {"offset_days": -7, "range_days": 7},
            "이번 달": {"offset_days": -30, "range_days": 30},
        },
        "relative_regex": [
            {"pattern": "지난\\s*(\\d+)\\s*일", "type": "days_ago"},
            {"pattern": "지난\\s*(\\d+)\\s*주일?", "type": "weeks_ago"},
            {"pattern": "최근\\s*(\\d+)\\s*일", "type": "days_ago"},
        ],
    }


@pytest.fixture
def date_regex_config():
    """날짜 정규식 설정."""
    return {
        "month_day_range": "(\\d{1,2})월\\s*(\\d{1,2})일\\s*[~\\-부]\\s*(\\d{1,2})일",
        "year_month_day": "(?:(\\d{4})년\\s*)?(\\d{1,2})월\\s*(\\d{1,2})일",
        "iso_range": "(\\d{4}-\\d{2}-\\d{2})\\s*[~\\-]\\s*(\\d{4}-\\d{2}-\\d{2})",
    }


@pytest.fixture
def parser(date_config, date_regex_config):
    """DateParser 인스턴스."""
    return DateParser(
        date_config=date_config,
        date_regex_config=date_regex_config,
        timezone="Asia/Seoul",
        reference_time=REF_TIME,
    )


class TestRelativeDate:
    """상대 날짜 테스트."""

    def test_yesterday(self, parser: DateParser) -> None:
        """'어제' 파싱."""
        date_from, date_to = parser.parse("어제 뉴스")
        assert date_from == datetime(2026, 2, 4, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 4, 23, 59, 59, tzinfo=TZ)

    def test_today(self, parser: DateParser) -> None:
        """'오늘' 파싱."""
        date_from, date_to = parser.parse("오늘 뉴스")
        assert date_from == datetime(2026, 2, 5, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 5, 23, 59, 59, tzinfo=TZ)

    def test_day_before_yesterday(self, parser: DateParser) -> None:
        """'그저께' 파싱."""
        date_from, date_to = parser.parse("그저께 뉴스")
        assert date_from == datetime(2026, 2, 3, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 3, 23, 59, 59, tzinfo=TZ)

    def test_this_week(self, parser: DateParser) -> None:
        """'이번 주' 파싱 (지난 7일)."""
        date_from, date_to = parser.parse("이번 주 뉴스")
        assert date_from == datetime(2026, 1, 29, 0, 0, 0, tzinfo=TZ)
        assert date_to.day == 4  # 7일 범위 - 1초


class TestRelativeRegex:
    """상대 날짜 정규식 테스트."""

    def test_last_n_days(self, parser: DateParser) -> None:
        """'지난 3일' 파싱."""
        date_from, date_to = parser.parse("지난 3일 뉴스")
        assert date_from == datetime(2026, 2, 2, 0, 0, 0, tzinfo=TZ)
        assert date_to.day == 5

    def test_last_n_weeks(self, parser: DateParser) -> None:
        """'지난 2주일' 파싱."""
        date_from, date_to = parser.parse("지난 2주일 뉴스")
        assert date_from == datetime(2026, 1, 22, 0, 0, 0, tzinfo=TZ)
        assert date_to.day == 5

    def test_last_1_week(self, parser: DateParser) -> None:
        """'지난 1주' 파싱."""
        date_from, date_to = parser.parse("지난 1주 뉴스")
        assert date_from == datetime(2026, 1, 29, 0, 0, 0, tzinfo=TZ)

    def test_recent_n_days(self, parser: DateParser) -> None:
        """'최근 5일' 파싱."""
        date_from, date_to = parser.parse("최근 5일 뉴스")
        assert date_from == datetime(2026, 1, 31, 0, 0, 0, tzinfo=TZ)


class TestAbsoluteRange:
    """절대 날짜 범위 테스트."""

    def test_month_day_range(self, parser: DateParser) -> None:
        """'2월 1일~5일' 파싱."""
        date_from, date_to = parser.parse("2월 1일~5일 뉴스")
        assert date_from == datetime(2026, 2, 1, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 5, 23, 59, 59, tzinfo=TZ)

    def test_month_day_range_dash(self, parser: DateParser) -> None:
        """'1월 10일-15일' 파싱."""
        date_from, date_to = parser.parse("1월 10일-15일 뉴스")
        assert date_from.month == 1
        assert date_from.day == 10
        assert date_to.day == 15


class TestAbsoluteSingle:
    """절대 단일 날짜 테스트."""

    def test_month_day(self, parser: DateParser) -> None:
        """'2월 3일' 파싱."""
        date_from, date_to = parser.parse("2월 3일 뉴스")
        assert date_from == datetime(2026, 2, 3, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 3, 23, 59, 59, tzinfo=TZ)

    def test_year_month_day(self, parser: DateParser) -> None:
        """'2026년 1월 15일' 파싱."""
        date_from, date_to = parser.parse("2026년 1월 15일 뉴스")
        assert date_from == datetime(2026, 1, 15, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 1, 15, 23, 59, 59, tzinfo=TZ)

    def test_future_month_infers_last_year(self, parser: DateParser) -> None:
        """미래 달은 작년으로 추론."""
        # REF_TIME은 2026년 2월 -> 12월 25일은 아직 미래
        date_from, date_to = parser.parse("12월 25일 뉴스")
        assert date_from.year == 2025


class TestIsoRange:
    """ISO 형식 범위 테스트."""

    def test_iso_date_range(self, parser: DateParser) -> None:
        """'2026-02-01~2026-02-05' 파싱."""
        date_from, date_to = parser.parse("2026-02-01~2026-02-05 뉴스")
        assert date_from == datetime(2026, 2, 1, 0, 0, 0, tzinfo=TZ)
        assert date_to == datetime(2026, 2, 5, 23, 59, 59, tzinfo=TZ)

    def test_iso_date_range_dash(self, parser: DateParser) -> None:
        """'2026-01-01-2026-01-31' 파싱."""
        date_from, date_to = parser.parse("2026-01-01-2026-01-31")
        assert date_from.month == 1
        assert date_from.day == 1
        assert date_to.month == 1
        assert date_to.day == 31


class TestNoDateFound:
    """날짜 없는 경우 테스트."""

    def test_no_date(self, parser: DateParser) -> None:
        """날짜 표현 없는 텍스트."""
        date_from, date_to = parser.parse("AI 뉴스 보여줘")
        assert date_from is None
        assert date_to is None

    def test_empty_string(self, parser: DateParser) -> None:
        """빈 문자열."""
        date_from, date_to = parser.parse("")
        assert date_from is None
        assert date_to is None
