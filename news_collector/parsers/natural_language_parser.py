"""한국어 자연어 쿼리 파서"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from news_collector.models.query_spec import QuerySpec
from news_collector.parsers.date_parser import DateParser
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class NaturalLanguageParser:
    """
    한국어 자연어 입력을 QuerySpec 필드로 변환.
    모든 패턴은 natural_language_mapping.yaml에서 로드.
    """

    def __init__(
        self,
        nl_config: Dict[str, Any],
        defaults: Dict[str, Any],
        reference_time: Optional[datetime] = None,
    ) -> None:
        """
        Args:
            nl_config: natural_language_mapping.yaml 전체 내용.
            defaults: config.yaml의 defaults 섹션.
            reference_time: 테스트용 기준 시각.
        """
        self._intent_patterns = nl_config.get("intent_patterns", {})
        self._category_keywords = nl_config.get("category_keywords", {})
        self._limit_patterns = nl_config.get("limit_patterns", [])
        self._keyword_patterns = nl_config.get("keyword_patterns", [])
        self._exclude_patterns = nl_config.get("exclude_patterns", [])
        self._option_keywords = nl_config.get("option_keywords", {})
        self._defaults = defaults

        self._date_parser = DateParser(
            date_config=nl_config.get("date_patterns", {}),
            date_regex_config=nl_config.get("date_regex", {}),
            timezone=defaults.get("timezone", "Asia/Seoul"),
            reference_time=reference_time,
        )

    def parse(self, text: str) -> QuerySpec:
        """
        자연어 문자열을 QuerySpec으로 변환.

        Args:
            text: 사용자 자연어 입력.

        Returns:
            파싱된 QuerySpec.
        """
        logger.debug("자연어 파싱 시작: %s", text)

        # 각 요소 추출
        intent = self._extract_intent(text)
        date_from, date_to = self._extract_dates(text)
        categories = self._extract_categories(text)
        keywords = self._extract_keywords(text, categories)
        exclude_keywords = self._extract_exclude_keywords(text)
        limit = self._extract_limit(text)
        options = self._extract_options(text)

        query = QuerySpec(
            date_from=date_from,
            date_to=date_to,
            locale=self._defaults.get("locale", "ko_KR"),
            timezone=self._defaults.get("timezone", "Asia/Seoul"),
            country=self._defaults.get("country", "KR"),
            language=self._defaults.get("language", "ko"),
            market=self._defaults.get("market", "ko_KR"),
            category=categories,
            keywords=keywords,
            exclude_keywords=exclude_keywords,
            popularity_type=intent.get(
                "popularity_type",
                self._defaults.get("popularity_type", "latest"),
            ),
            group_by=intent.get(
                "group_by",
                self._defaults.get("group_by", "none"),
            ),
            limit=limit if limit else self._defaults.get("limit", 20),
            offset=self._defaults.get("offset", 0),
            verified_sources_only=options.get(
                "verified_sources_only",
                self._defaults.get("verified_sources_only", False),
            ),
            diversity=options.get(
                "diversity",
                self._defaults.get("diversity", True),
            ),
        )

        logger.debug("자연어 파싱 결과: %s", query)
        return query

    def _extract_intent(self, text: str) -> Dict[str, Any]:
        """
        의도 패턴 매칭 (YAML 선언 순서 우선).

        Returns:
            매칭된 intent의 result 딕셔너리. 매칭 없으면 빈 딕셔너리.
        """
        for intent_name, spec in self._intent_patterns.items():
            keywords = spec.get("keywords", [])
            for keyword in keywords:
                if keyword in text:
                    logger.debug("의도 매칭: %s (키워드: %s)", intent_name, keyword)
                    return spec.get("result", {})
        return {}

    def _extract_dates(
        self, text: str
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """DateParser에 위임."""
        return self._date_parser.parse(text)

    def _extract_categories(self, text: str) -> Optional[List[str]]:
        """
        카테고리 키워드 매칭.

        Returns:
            매칭된 카테고리 리스트. 없으면 None.
        """
        matched: List[str] = []
        for category, keywords in self._category_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    if category not in matched:
                        matched.append(category)
                    break
        return matched if matched else None

    def _extract_keywords(
        self, text: str, categories: Optional[List[str]] = None
    ) -> Optional[List[str]]:
        """
        콘텐츠 키워드 추출 (카테고리명과 중복 제거).

        Returns:
            추출된 키워드 리스트. 없으면 None.
        """
        extracted: List[str] = []
        # 카테고리명 자체만 제외 (카테고리 감지 키워드는 제외하지 않음)
        category_names = set(categories) if categories else set()

        for rule in self._keyword_patterns:
            pattern = rule["pattern"]
            group = rule.get("group", 1)
            matches = re.finditer(pattern, text)
            for match in matches:
                word = match.group(group).strip()
                if word and word not in extracted and word not in category_names:
                    extracted.append(word)

        return extracted if extracted else None

    def _extract_exclude_keywords(self, text: str) -> Optional[List[str]]:
        """제외 키워드 추출."""
        extracted: List[str] = []
        for rule in self._exclude_patterns:
            pattern = rule["pattern"]
            group = rule.get("group", 1)
            matches = re.finditer(pattern, text)
            for match in matches:
                word = match.group(group).strip()
                if word and word not in extracted:
                    extracted.append(word)
        return extracted if extracted else None

    def _extract_limit(self, text: str) -> Optional[int]:
        """결과 수 추출 ("Top 10", "20개" 등)."""
        for rule in self._limit_patterns:
            pattern = rule["pattern"]
            group = rule.get("group", 1)
            match = re.search(pattern, text)
            if match:
                try:
                    return int(match.group(group))
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_options(self, text: str) -> Dict[str, bool]:
        """옵션 키워드 추출."""
        options: Dict[str, bool] = {}
        for option_name, spec in self._option_keywords.items():
            keywords = spec.get("keywords", [])
            for keyword in keywords:
                if keyword in text:
                    options[option_name] = spec.get("value", True)
                    break
        return options
