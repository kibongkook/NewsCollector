"""한국어 날짜 표현 파서"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class DateParser:
    """
    한국어 날짜 표현을 (date_from, date_to) 튜플로 변환.

    지원 형식:
    - 상대: "어제", "오늘", "지난 1주일", "지난 3일", "이번 달"
    - 절대: "2월 1일", "2026년 2월 1일"
    - 범위: "2월 1일~5일", "2026-02-01~2026-02-05"
    """

    def __init__(
        self,
        date_config: Dict[str, Any],
        date_regex_config: Dict[str, str],
        timezone: str = "Asia/Seoul",
        reference_time: Optional[datetime] = None,
    ) -> None:
        """
        Args:
            date_config: natural_language_mapping.yaml의 date_patterns 섹션.
            date_regex_config: natural_language_mapping.yaml의 date_regex 섹션.
            timezone: 기본 타임존.
            reference_time: 테스트용 기준 시각. None이면 현재 시각 사용.
        """
        self._relative_dates = date_config.get("relative", {})
        self._relative_regex = date_config.get("relative_regex", [])
        self._date_regex = date_regex_config
        self._tz = ZoneInfo(timezone)
        self._reference_time = reference_time

    def parse(self, text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        텍스트에서 날짜 범위 추출.

        Args:
            text: 사용자 입력 문자열.

        Returns:
            (date_from, date_to) 튜플. 날짜 없으면 (None, None).
        """
        # 1. ISO 범위 (YYYY-MM-DD~YYYY-MM-DD) 먼저 시도
        result = self._try_iso_range(text)
        if result:
            logger.debug("ISO 범위 매칭: %s", result)
            return result

        # 2. 상대 날짜 키워드 ("어제", "오늘" 등)
        result = self._try_relative_keyword(text)
        if result:
            logger.debug("상대 날짜 키워드 매칭: %s", result)
            return result

        # 3. 상대 날짜 정규식 ("지난 N일", "최근 N주")
        result = self._try_relative_regex(text)
        if result:
            logger.debug("상대 날짜 정규식 매칭: %s", result)
            return result

        # 4. 절대 범위 ("M월 D일~D일")
        result = self._try_absolute_range(text)
        if result:
            logger.debug("절대 범위 매칭: %s", result)
            return result

        # 5. 절대 단일 날짜 ("M월 D일")
        result = self._try_absolute_single(text)
        if result:
            logger.debug("절대 단일 날짜 매칭: %s", result)
            return result

        logger.debug("날짜 표현 없음: %s", text)
        return None, None

    def _get_now(self) -> datetime:
        """기준 시각 반환 (테스트 주입 가능)."""
        if self._reference_time is not None:
            return self._reference_time
        return datetime.now(self._tz)

    def _make_date(
        self, year: int, month: int, day: int, end_of_day: bool = False
    ) -> datetime:
        """타임존 인식 datetime 생성."""
        if end_of_day:
            return datetime(year, month, day, 23, 59, 59, tzinfo=self._tz)
        return datetime(year, month, day, 0, 0, 0, tzinfo=self._tz)

    def _infer_year(self, month: int, day: int) -> int:
        """연도 미지정 시 추론. 미래 날짜면 작년으로."""
        now = self._get_now()
        try:
            candidate = datetime(now.year, month, day, tzinfo=self._tz)
            if candidate > now:
                return now.year - 1
            return now.year
        except ValueError:
            return now.year

    def _try_relative_keyword(
        self, text: str
    ) -> Optional[Tuple[datetime, datetime]]:
        """상대 날짜 키워드 매칭 ("어제", "오늘" 등)."""
        now = self._get_now()
        for keyword, spec in self._relative_dates.items():
            if keyword in text:
                offset = spec["offset_days"]
                range_days = spec["range_days"]
                start = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=offset)
                end = start + timedelta(days=range_days) - timedelta(seconds=1)
                return start, end
        return None

    def _try_relative_regex(
        self, text: str
    ) -> Optional[Tuple[datetime, datetime]]:
        """상대 날짜 정규식 매칭 ("지난 N일", "최근 N주")."""
        now = self._get_now()
        for rule in self._relative_regex:
            pattern = rule["pattern"]
            match = re.search(pattern, text)
            if match:
                n = int(match.group(1))
                if rule["type"] == "days_ago":
                    days = n
                elif rule["type"] == "weeks_ago":
                    days = n * 7
                else:
                    continue

                start = now.replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(days=days)
                end = now.replace(
                    hour=23, minute=59, second=59, microsecond=0
                )
                return start, end
        return None

    def _try_absolute_range(
        self, text: str
    ) -> Optional[Tuple[datetime, datetime]]:
        """절대 날짜 범위 매칭 ("M월 D일~D일")."""
        pattern = self._date_regex.get("month_day_range", "")
        if not pattern:
            return None

        match = re.search(pattern, text)
        if match:
            month = int(match.group(1))
            day_start = int(match.group(2))
            day_end = int(match.group(3))
            year = self._infer_year(month, day_start)
            try:
                return (
                    self._make_date(year, month, day_start),
                    self._make_date(year, month, day_end, end_of_day=True),
                )
            except ValueError:
                logger.warning("유효하지 않은 날짜: %d-%d-%d~%d", year, month, day_start, day_end)
                return None
        return None

    def _try_absolute_single(
        self, text: str
    ) -> Optional[Tuple[datetime, datetime]]:
        """절대 단일 날짜 매칭 ("M월 D일" 또는 "YYYY년 M월 D일")."""
        pattern = self._date_regex.get("year_month_day", "")
        if not pattern:
            return None

        match = re.search(pattern, text)
        if match:
            year_str = match.group(1)
            month = int(match.group(2))
            day = int(match.group(3))

            if year_str:
                year = int(year_str)
            else:
                year = self._infer_year(month, day)

            try:
                return (
                    self._make_date(year, month, day),
                    self._make_date(year, month, day, end_of_day=True),
                )
            except ValueError:
                logger.warning("유효하지 않은 날짜: %d-%d-%d", year, month, day)
                return None
        return None

    def _try_iso_range(
        self, text: str
    ) -> Optional[Tuple[datetime, datetime]]:
        """ISO 형식 범위 매칭 ("YYYY-MM-DD~YYYY-MM-DD")."""
        pattern = self._date_regex.get("iso_range", "")
        if not pattern:
            return None

        match = re.search(pattern, text)
        if match:
            try:
                d1 = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
                    tzinfo=self._tz
                )
                d2 = datetime.strptime(match.group(2), "%Y-%m-%d").replace(
                    hour=23, minute=59, second=59, tzinfo=self._tz
                )
                return d1, d2
            except ValueError:
                logger.warning("유효하지 않은 ISO 날짜: %s", match.group(0))
                return None
        return None
