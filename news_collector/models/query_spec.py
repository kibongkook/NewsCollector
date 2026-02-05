"""QuerySpec - 사용자 요청을 구조화한 데이터 모델"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class QuerySpec:
    """
    Module 1의 출력 객체.
    사용자 입력(자연어/파라미터)을 파싱하여 구조화된 쿼리 사양으로 변환.
    """

    # 시간 범위
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    # 위치/언어 설정
    locale: str = "ko_KR"
    timezone: str = "Asia/Seoul"
    country: str = "KR"
    language: str = "ko"
    market: str = "ko_KR"

    # 콘텐츠 필터
    category: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None

    # 인기도/순서
    popularity_type: str = "latest"
    group_by: str = "none"

    # 페이징
    limit: int = 20
    offset: int = 0

    # 추가 옵션
    verified_sources_only: bool = False
    diversity: bool = True

    def __post_init__(self) -> None:
        """가변 기본값 안전 초기화."""
        if self.category is not None and not isinstance(self.category, list):
            self.category = [self.category]
        if self.keywords is not None and not isinstance(self.keywords, list):
            self.keywords = [self.keywords]
        if self.exclude_keywords is not None and not isinstance(self.exclude_keywords, list):
            self.exclude_keywords = [self.exclude_keywords]

    @classmethod
    def create_default(cls, config: Dict[str, Any]) -> "QuerySpec":
        """
        설정 딕셔너리에서 기본값을 로드하여 QuerySpec 생성.

        Args:
            config: defaults 섹션 딕셔너리.
        """
        return cls(
            locale=config.get("locale", "ko_KR"),
            timezone=config.get("timezone", "Asia/Seoul"),
            country=config.get("country", "KR"),
            language=config.get("language", "ko"),
            market=config.get("market", "ko_KR"),
            popularity_type=config.get("popularity_type", "latest"),
            group_by=config.get("group_by", "none"),
            limit=config.get("limit", 20),
            offset=config.get("offset", 0),
            verified_sources_only=config.get("verified_sources_only", False),
            diversity=config.get("diversity", True),
        )

    def validate(self) -> List[str]:
        """
        필드 유효성 검사.

        Returns:
            오류 메시지 리스트. 비어있으면 유효함.
        """
        errors: List[str] = []

        if self.limit < 1:
            errors.append(f"limit은 1 이상이어야 합니다: {self.limit}")
        if self.limit > 100:
            errors.append(f"limit은 100 이하여야 합니다: {self.limit}")
        if self.offset < 0:
            errors.append(f"offset은 0 이상이어야 합니다: {self.offset}")

        allowed_pop = {"trending", "popular", "latest", "quality"}
        if self.popularity_type not in allowed_pop:
            errors.append(
                f"유효하지 않은 popularity_type: {self.popularity_type} "
                f"(허용: {allowed_pop})"
            )

        allowed_group = {"day", "source", "none"}
        if self.group_by not in allowed_group:
            errors.append(
                f"유효하지 않은 group_by: {self.group_by} "
                f"(허용: {allowed_group})"
            )

        if self.date_from and self.date_to and self.date_from > self.date_to:
            errors.append(
                f"date_from({self.date_from})이 date_to({self.date_to})보다 늦습니다"
            )

        if self.keywords and len(self.keywords) > 10:
            errors.append(f"키워드는 최대 10개입니다: {len(self.keywords)}개")

        if self.category and len(self.category) > 5:
            errors.append(f"카테고리는 최대 5개입니다: {len(self.category)}개")

        return errors
