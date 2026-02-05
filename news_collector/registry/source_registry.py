"""Module 2: Source Registry - 뉴스 소스 메타데이터 중앙 관리"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from news_collector.models.source import NewsSource, TierDefinition
from news_collector.utils.config_manager import ConfigManager
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

VALID_TIERS = {"whitelist", "tier1", "tier2", "tier3", "blacklist"}
VALID_INGESTION_TYPES = {"api", "rss", "web_crawl"}


class SourceRegistry:
    """
    Module 2: 모든 뉴스 소스의 메타데이터 및 수집 정책 중앙 관리.

    - sources_registry.yaml에서 소스 로드
    - ID/Tier/카테고리/수집방식 기반 조회
    - QuerySpec 기반 소스 선택
    - 소스 상태(실패 횟수, 마지막 크롤 시각) 런타임 관리

    사용법:
        config = ConfigManager()
        registry = SourceRegistry(config)
        sources = registry.get_active_sources()
        naver = registry.get("naver_news")
    """

    def __init__(self, config: ConfigManager) -> None:
        self._config = config
        self._sources: Dict[str, NewsSource] = {}
        self._tier_definitions: Dict[str, TierDefinition] = {}
        self._load()

    def _load(self) -> None:
        """sources_registry.yaml에서 소스와 Tier 정의 로드."""
        registry_data = self._config.get_file_config("sources_registry")
        if not registry_data:
            logger.warning("sources_registry.yaml을 찾을 수 없습니다")
            return

        # Tier 정의 로드
        for tier_name, tier_data in registry_data.get("tier_definitions", {}).items():
            self._tier_definitions[tier_name] = TierDefinition(
                name=tier_name,
                description=tier_data.get("description", ""),
                base_credibility=float(tier_data.get("base_credibility", 70)),
                weight=float(tier_data.get("weight", 0.5)),
            )

        # 소스 로드
        for source_id, source_data in registry_data.get("sources", {}).items():
            if "id" not in source_data:
                source_data["id"] = source_id
            source = NewsSource.from_dict(source_data)
            self._sources[source.id] = source
            logger.debug("소스 로드: %s (tier=%s, active=%s)", source.id, source.tier, source.is_active)

        logger.info("소스 레지스트리 로드 완료: %d개 소스, %d개 Tier",
                     len(self._sources), len(self._tier_definitions))

    # ===== 단일 조회 =====

    def get(self, source_id: str) -> Optional[NewsSource]:
        """ID로 소스 조회."""
        return self._sources.get(source_id)

    def get_tier_definition(self, tier_name: str) -> Optional[TierDefinition]:
        """Tier 정의 조회."""
        return self._tier_definitions.get(tier_name)

    # ===== 목록 조회 =====

    def get_all(self) -> List[NewsSource]:
        """전체 소스 목록."""
        return list(self._sources.values())

    def get_active_sources(self) -> List[NewsSource]:
        """활성 소스만 (is_active=True, blacklist 제외)."""
        return [
            s for s in self._sources.values()
            if s.is_active and s.tier != "blacklist"
        ]

    def get_by_tier(self, tier: str) -> List[NewsSource]:
        """특정 Tier의 활성 소스."""
        return [
            s for s in self._sources.values()
            if s.tier == tier and s.is_active
        ]

    def get_by_ingestion_type(self, ingestion_type: str) -> List[NewsSource]:
        """수집 방식별 활성 소스."""
        return [
            s for s in self._sources.values()
            if s.ingestion_type == ingestion_type and s.is_active
        ]

    def get_by_category(self, category: str) -> List[NewsSource]:
        """특정 카테고리를 지원하는 활성 소스."""
        return [
            s for s in self._sources.values()
            if s.is_active and s.tier != "blacklist"
            and category in s.supported_categories
        ]

    def get_by_locale(self, locale: str) -> List[NewsSource]:
        """특정 로케일을 지원하는 활성 소스."""
        return [
            s for s in self._sources.values()
            if s.is_active and s.tier != "blacklist"
            and locale in s.supported_locales
        ]

    def get_verified_sources(self) -> List[NewsSource]:
        """검증된 소스 (whitelist + tier1)."""
        return [
            s for s in self._sources.values()
            if s.is_active and s.tier in ("whitelist", "tier1")
        ]

    # ===== QuerySpec 기반 소스 선택 =====

    def select_sources(
        self,
        categories: Optional[List[str]] = None,
        locale: Optional[str] = None,
        verified_only: bool = False,
        ingestion_type: Optional[str] = None,
    ) -> List[NewsSource]:
        """
        조건 기반 소스 선택.

        Args:
            categories: 카테고리 필터 (하나라도 지원하면 포함).
            locale: 로케일 필터.
            verified_only: True면 whitelist+tier1만.
            ingestion_type: 수집 방식 필터.

        Returns:
            조건에 맞는 활성 소스 목록 (신뢰도순 정렬).
        """
        candidates = self.get_active_sources()

        if verified_only:
            candidates = [s for s in candidates if s.tier in ("whitelist", "tier1")]

        if categories:
            candidates = [
                s for s in candidates
                if any(cat in s.supported_categories for cat in categories)
                or not s.supported_categories  # 카테고리 미지정 소스는 포함
            ]

        if locale:
            candidates = [
                s for s in candidates
                if locale in s.supported_locales
            ]

        if ingestion_type:
            candidates = [
                s for s in candidates
                if s.ingestion_type == ingestion_type
            ]

        # 신뢰도순 정렬 (높은 순)
        candidates.sort(key=lambda s: s.credibility_base_score, reverse=True)
        return candidates

    # ===== 상태 관리 (런타임) =====

    def record_success(self, source_id: str) -> None:
        """수집 성공 기록."""
        source = self._sources.get(source_id)
        if source:
            source.last_crawled = datetime.now()
            source.last_success = datetime.now()
            source.failure_count = 0
            logger.debug("소스 성공 기록: %s", source_id)

    def record_failure(self, source_id: str) -> None:
        """수집 실패 기록. 연속 실패 시 자동 비활성화."""
        source = self._sources.get(source_id)
        if source:
            source.last_crawled = datetime.now()
            source.failure_count += 1
            logger.warning("소스 실패 기록: %s (연속 %d회)", source_id, source.failure_count)

            max_failures = self._config.get("source_management.max_consecutive_failures", 5)
            if source.failure_count >= max_failures:
                source.is_active = False
                logger.error("소스 자동 비활성화: %s (%d회 연속 실패)", source_id, source.failure_count)

    def reactivate(self, source_id: str) -> bool:
        """비활성화된 소스 재활성화."""
        source = self._sources.get(source_id)
        if source and source.tier != "blacklist":
            source.is_active = True
            source.failure_count = 0
            logger.info("소스 재활성화: %s", source_id)
            return True
        return False

    # ===== 통계 =====

    @property
    def total_count(self) -> int:
        """전체 소스 수."""
        return len(self._sources)

    @property
    def active_count(self) -> int:
        """활성 소스 수."""
        return len(self.get_active_sources())

    def get_stats(self) -> Dict[str, Any]:
        """레지스트리 통계."""
        tier_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {}

        for source in self._sources.values():
            tier_counts[source.tier] = tier_counts.get(source.tier, 0) + 1
            type_counts[source.ingestion_type] = type_counts.get(source.ingestion_type, 0) + 1

        return {
            "total": self.total_count,
            "active": self.active_count,
            "by_tier": tier_counts,
            "by_type": type_counts,
        }
