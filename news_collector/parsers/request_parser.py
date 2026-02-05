"""Module 1: Request Parser - 사용자 요청 파싱 오케스트레이터"""

from datetime import datetime
from typing import Any, Dict, Optional, Union

from news_collector.models.query_spec import QuerySpec
from news_collector.parsers.natural_language_parser import NaturalLanguageParser
from news_collector.parsers.parameter_parser import ParameterParser
from news_collector.utils.config_manager import ConfigManager
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class RequestParser:
    """
    Module 1: 사용자 입력(자연어 또는 파라미터)을 QuerySpec으로 변환.

    사용법:
        config = ConfigManager()
        parser = RequestParser(config)
        query = parser.parse("어제 정치 뉴스 Top 10")
        query = parser.parse({"keywords": ["AI"], "limit": 20})
    """

    def __init__(
        self,
        config: ConfigManager,
        reference_time: Optional[datetime] = None,
    ) -> None:
        """
        Args:
            config: 설정 관리자.
            reference_time: 테스트용 기준 시각.
        """
        self._config = config
        self._defaults = config.get_section("defaults")
        self._nl_config = config.get_file_config("natural_language_mapping")

        self._nl_parser = NaturalLanguageParser(
            nl_config=self._nl_config,
            defaults=self._defaults,
            reference_time=reference_time,
        )
        self._param_parser = ParameterParser(defaults=self._defaults)

    def parse(self, user_input: Union[str, Dict[str, Any]]) -> QuerySpec:
        """
        사용자 입력을 QuerySpec으로 변환.

        Args:
            user_input: 자연어 문자열 또는 파라미터 딕셔너리.

        Returns:
            검증된 QuerySpec.

        Raises:
            ValueError: 입력을 파싱할 수 없거나 검증 실패 시.
        """
        input_type = self._detect_input_type(user_input)
        logger.info("요청 파싱 시작 (타입: %s)", input_type)

        if input_type == "natural_language":
            query_spec = self._nl_parser.parse(str(user_input))
        elif input_type == "parameter":
            query_spec = self._param_parser.parse(user_input)
        else:
            raise ValueError(f"지원하지 않는 입력 타입: {type(user_input)}")

        query_spec = self._apply_defaults(query_spec)
        return self._validate_and_return(query_spec)

    def _detect_input_type(self, user_input: Union[str, Dict[str, Any]]) -> str:
        """입력 타입 감지."""
        if isinstance(user_input, str):
            return "natural_language"
        if isinstance(user_input, dict):
            return "parameter"
        raise ValueError(f"지원하지 않는 입력 타입: {type(user_input)}")

    def _apply_defaults(self, query_spec: QuerySpec) -> QuerySpec:
        """None 필드에 설정 기본값 적용."""
        if query_spec.locale is None:
            query_spec.locale = self._defaults.get("locale", "ko_KR")
        if query_spec.timezone is None:
            query_spec.timezone = self._defaults.get("timezone", "Asia/Seoul")
        if query_spec.country is None:
            query_spec.country = self._defaults.get("country", "KR")
        if query_spec.language is None:
            query_spec.language = self._defaults.get("language", "ko")
        if query_spec.market is None:
            query_spec.market = self._defaults.get("market", "ko_KR")
        return query_spec

    def _validate_and_return(self, query_spec: QuerySpec) -> QuerySpec:
        """검증 수행. 실패 시 ValueError."""
        errors = query_spec.validate()
        if errors:
            error_msg = "; ".join(errors)
            logger.error("QuerySpec 검증 실패: %s", error_msg)
            raise ValueError(f"QuerySpec 검증 실패: {error_msg}")

        logger.info("요청 파싱 완료: %s", query_spec)
        return query_spec
