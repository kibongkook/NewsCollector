"""구조화된 파라미터(dict/JSON) 파서"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from dateutil import parser as dateutil_parser

from news_collector.models.query_spec import QuerySpec
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

ALLOWED_POPULARITY_TYPES = {"trending", "popular", "latest", "quality"}
ALLOWED_GROUP_BY = {"day", "source", "none"}


class ParameterParser:
    """
    구조화된 dict/JSON 입력을 QuerySpec으로 변환.
    타입 변환, 기본값 적용, 필드 검증 수행.
    """

    def __init__(self, defaults: Dict[str, Any]) -> None:
        """
        Args:
            defaults: config.yaml의 defaults 섹션.
        """
        self._defaults = defaults

    def parse(self, params: Dict[str, Any]) -> QuerySpec:
        """
        파라미터 딕셔너리를 QuerySpec으로 변환.

        Args:
            params: 사용자 입력 딕셔너리.

        Returns:
            변환된 QuerySpec.
        """
        logger.debug("파라미터 파싱 시작: %s", params)

        query = QuerySpec(
            date_from=self._parse_date_field(params.get("date_from")),
            date_to=self._parse_date_field(params.get("date_to")),
            locale=params.get("locale", self._defaults.get("locale", "ko_KR")),
            timezone=params.get("timezone", self._defaults.get("timezone", "Asia/Seoul")),
            country=params.get("country", self._defaults.get("country", "KR")),
            language=params.get("language", self._defaults.get("language", "ko")),
            market=params.get("market", self._defaults.get("market", "ko_KR")),
            category=self._parse_list_field(params.get("category")),
            keywords=self._parse_list_field(params.get("keywords")),
            exclude_keywords=self._parse_list_field(params.get("exclude_keywords")),
            popularity_type=self._validate_popularity_type(
                params.get("popularity_type", params.get("sort_by", ""))
            ),
            group_by=self._validate_group_by(
                params.get("group_by", "")
            ),
            limit=self._parse_int_field(
                params.get("limit"), self._defaults.get("limit", 20)
            ),
            offset=self._parse_int_field(
                params.get("offset"), self._defaults.get("offset", 0)
            ),
            verified_sources_only=self._parse_bool_field(
                params.get("verified_sources_only"),
                self._defaults.get("verified_sources_only", False),
            ),
            diversity=self._parse_bool_field(
                params.get("diversity"),
                self._defaults.get("diversity", True),
            ),
        )

        logger.debug("파라미터 파싱 결과: %s", query)
        return query

    def _parse_date_field(self, value: Any) -> Optional[datetime]:
        """문자열/datetime을 datetime으로 변환."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return dateutil_parser.parse(value)
            except (ValueError, TypeError):
                logger.warning("날짜 파싱 실패: %s", value)
                return None
        return None

    def _parse_list_field(self, value: Any) -> Optional[List[str]]:
        """문자열 또는 리스트를 리스트로 변환."""
        if value is None:
            return None
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            parts = [v.strip() for v in value.split(",") if v.strip()]
            return parts if parts else None
        return [str(value)]

    def _parse_int_field(self, value: Any, default: int) -> int:
        """정수 변환 (실패 시 기본값)."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning("정수 변환 실패: %s (기본값 %d 사용)", value, default)
            return default

    def _parse_bool_field(self, value: Any, default: bool) -> bool:
        """불리언 변환 (실패 시 기본값)."""
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def _validate_popularity_type(self, value: str) -> str:
        """유효한 popularity_type인지 검증."""
        if value in ALLOWED_POPULARITY_TYPES:
            return value
        return self._defaults.get("popularity_type", "latest")

    def _validate_group_by(self, value: str) -> str:
        """유효한 group_by인지 검증."""
        if value in ALLOWED_GROUP_BY:
            return value
        return self._defaults.get("group_by", "none")
