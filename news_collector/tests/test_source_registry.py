"""Module 2: SourceRegistry 테스트"""

import pytest

from news_collector.models.source import NewsSource, RateLimit, ProvidesMetadata, TierDefinition
from news_collector.registry.source_registry import SourceRegistry
from news_collector.utils.config_manager import ConfigManager


@pytest.fixture
def registry(config_manager: ConfigManager) -> SourceRegistry:
    """실제 sources_registry.yaml 기반 SourceRegistry."""
    return SourceRegistry(config_manager)


# ===== 로드 테스트 =====

class TestRegistryLoad:
    """소스 레지스트리 로드 테스트."""

    def test_sources_loaded(self, registry: SourceRegistry) -> None:
        """소스가 로드되었는지."""
        assert registry.total_count >= 7

    def test_tier_definitions_loaded(self, registry: SourceRegistry) -> None:
        """Tier 정의가 로드되었는지."""
        td = registry.get_tier_definition("tier1")
        assert td is not None
        assert td.base_credibility == 88
        assert td.weight == 0.95

    def test_all_tiers_loaded(self, registry: SourceRegistry) -> None:
        """5개 Tier 모두 로드."""
        for tier in ["whitelist", "tier1", "tier2", "tier3", "blacklist"]:
            assert registry.get_tier_definition(tier) is not None


# ===== 단일 조회 테스트 =====

class TestSingleLookup:
    """ID 기반 소스 조회."""

    def test_get_existing_source(self, registry: SourceRegistry) -> None:
        """존재하는 소스 조회."""
        naver = registry.get("naver_news")
        assert naver is not None
        assert naver.name == "Naver News API"
        assert naver.tier == "tier1"
        assert naver.ingestion_type == "api"
        assert naver.credibility_base_score == 88

    def test_get_nonexistent_source(self, registry: SourceRegistry) -> None:
        """존재하지 않는 소스 조회 시 None."""
        assert registry.get("nonexistent") is None

    def test_source_rate_limit(self, registry: SourceRegistry) -> None:
        """Rate limit 로드 확인."""
        naver = registry.get("naver_news")
        assert naver.rate_limit.requests_per_minute == 100

    def test_source_provides_metadata(self, registry: SourceRegistry) -> None:
        """메타데이터 제공 여부 확인."""
        gov = registry.get("gov_briefing")
        assert gov.provides_metadata.author is True
        assert gov.provides_metadata.publish_date is True

    def test_source_tier_weight(self, registry: SourceRegistry) -> None:
        """Tier weight 프로퍼티."""
        naver = registry.get("naver_news")
        assert naver.tier_weight == 0.95

        blog = registry.get("unknown_blog")
        assert blog.tier_weight == 0.60

    def test_blacklist_source(self, registry: SourceRegistry) -> None:
        """블랙리스트 소스."""
        spam = registry.get("spam_site")
        assert spam is not None
        assert spam.tier == "blacklist"
        assert spam.is_active is False
        assert spam.tier_weight == 0.0


# ===== 목록 조회 테스트 =====

class TestListQueries:
    """목록 조회 테스트."""

    def test_get_all(self, registry: SourceRegistry) -> None:
        """전체 소스 목록."""
        all_sources = registry.get_all()
        assert len(all_sources) >= 7

    def test_get_active_sources(self, registry: SourceRegistry) -> None:
        """활성 소스 (blacklist 제외)."""
        active = registry.get_active_sources()
        for s in active:
            assert s.is_active is True
            assert s.tier != "blacklist"

    def test_blacklist_excluded_from_active(self, registry: SourceRegistry) -> None:
        """블랙리스트는 활성 목록에서 제외."""
        active_ids = [s.id for s in registry.get_active_sources()]
        assert "spam_site" not in active_ids

    def test_get_by_tier(self, registry: SourceRegistry) -> None:
        """Tier별 조회."""
        tier1 = registry.get_by_tier("tier1")
        assert len(tier1) >= 3
        for s in tier1:
            assert s.tier == "tier1"

    def test_get_by_ingestion_type_api(self, registry: SourceRegistry) -> None:
        """API 소스 조회."""
        api_sources = registry.get_by_ingestion_type("api")
        assert len(api_sources) >= 1
        for s in api_sources:
            assert s.ingestion_type == "api"

    def test_get_by_ingestion_type_rss(self, registry: SourceRegistry) -> None:
        """RSS 소스 조회."""
        rss_sources = registry.get_by_ingestion_type("rss")
        assert len(rss_sources) >= 3
        for s in rss_sources:
            assert s.ingestion_type == "rss"

    def test_get_by_category(self, registry: SourceRegistry) -> None:
        """카테고리별 조회."""
        it_sources = registry.get_by_category("IT")
        assert len(it_sources) >= 1
        for s in it_sources:
            assert "IT" in s.supported_categories

    def test_get_by_locale(self, registry: SourceRegistry) -> None:
        """로케일별 조회."""
        ko_sources = registry.get_by_locale("ko_KR")
        assert len(ko_sources) >= 5

    def test_get_verified_sources(self, registry: SourceRegistry) -> None:
        """검증된 소스 (whitelist + tier1)."""
        verified = registry.get_verified_sources()
        assert len(verified) >= 4
        for s in verified:
            assert s.tier in ("whitelist", "tier1")


# ===== 소스 선택 테스트 =====

class TestSelectSources:
    """QuerySpec 조건 기반 소스 선택."""

    def test_select_all_active(self, registry: SourceRegistry) -> None:
        """조건 없이 전체 활성 소스."""
        sources = registry.select_sources()
        assert len(sources) >= 6
        # 신뢰도순 정렬 확인
        scores = [s.credibility_base_score for s in sources]
        assert scores == sorted(scores, reverse=True)

    def test_select_by_category(self, registry: SourceRegistry) -> None:
        """카테고리 필터."""
        sources = registry.select_sources(categories=["정치"])
        assert all(
            "정치" in s.supported_categories or not s.supported_categories
            for s in sources
        )

    def test_select_verified_only(self, registry: SourceRegistry) -> None:
        """검증 소스만."""
        sources = registry.select_sources(verified_only=True)
        for s in sources:
            assert s.tier in ("whitelist", "tier1")

    def test_select_by_ingestion_type(self, registry: SourceRegistry) -> None:
        """수집 방식 필터."""
        sources = registry.select_sources(ingestion_type="rss")
        for s in sources:
            assert s.ingestion_type == "rss"

    def test_select_combined_filters(self, registry: SourceRegistry) -> None:
        """복합 조건."""
        sources = registry.select_sources(
            categories=["경제"],
            locale="ko_KR",
            verified_only=True,
        )
        for s in sources:
            assert s.tier in ("whitelist", "tier1")
            assert "ko_KR" in s.supported_locales

    def test_select_sorted_by_credibility(self, registry: SourceRegistry) -> None:
        """결과가 신뢰도 내림차순."""
        sources = registry.select_sources()
        for i in range(len(sources) - 1):
            assert sources[i].credibility_base_score >= sources[i + 1].credibility_base_score


# ===== 상태 관리 테스트 =====

class TestStateManagement:
    """런타임 상태 관리."""

    def test_record_success(self, registry: SourceRegistry) -> None:
        """성공 기록."""
        registry.record_success("naver_news")
        naver = registry.get("naver_news")
        assert naver.last_crawled is not None
        assert naver.last_success is not None
        assert naver.failure_count == 0

    def test_record_failure(self, registry: SourceRegistry) -> None:
        """실패 기록."""
        registry.record_failure("naver_news")
        naver = registry.get("naver_news")
        assert naver.failure_count == 1

    def test_consecutive_failures_deactivate(self, registry: SourceRegistry) -> None:
        """연속 실패 시 자동 비활성화 (기본 5회)."""
        for _ in range(5):
            registry.record_failure("unknown_blog")
        blog = registry.get("unknown_blog")
        assert blog.is_active is False

    def test_reactivate(self, registry: SourceRegistry) -> None:
        """비활성화된 소스 재활성화."""
        # 먼저 비활성화
        source = registry.get("hani_rss")
        source.is_active = False
        source.failure_count = 5

        result = registry.reactivate("hani_rss")
        assert result is True
        assert source.is_active is True
        assert source.failure_count == 0

    def test_reactivate_blacklist_fails(self, registry: SourceRegistry) -> None:
        """블랙리스트는 재활성화 불가."""
        result = registry.reactivate("spam_site")
        assert result is False

    def test_record_nonexistent_source(self, registry: SourceRegistry) -> None:
        """존재하지 않는 소스 기록 시 무시."""
        registry.record_success("nonexistent")  # 에러 없이 무시
        registry.record_failure("nonexistent")


# ===== 통계 테스트 =====

class TestStats:
    """레지스트리 통계."""

    def test_total_count(self, registry: SourceRegistry) -> None:
        """전체 소스 수."""
        assert registry.total_count >= 7

    def test_active_count(self, registry: SourceRegistry) -> None:
        """활성 소스 수."""
        assert registry.active_count < registry.total_count  # blacklist 제외

    def test_get_stats(self, registry: SourceRegistry) -> None:
        """통계 딕셔너리."""
        stats = registry.get_stats()
        assert "total" in stats
        assert "active" in stats
        assert "by_tier" in stats
        assert "by_type" in stats
        assert stats["by_tier"]["tier1"] >= 3


# ===== NewsSource.from_dict 테스트 =====

class TestNewsSourceFromDict:
    """NewsSource.from_dict 단위 테스트."""

    def test_full_dict(self) -> None:
        """전체 필드."""
        data = {
            "id": "test_source",
            "name": "Test",
            "tier": "tier1",
            "ingestion_type": "api",
            "base_url": "https://test.com",
            "credibility_base_score": 85,
            "rate_limit": {"requests_per_minute": 50},
            "provides_metadata": {"author": True, "views": True},
        }
        source = NewsSource.from_dict(data)
        assert source.id == "test_source"
        assert source.tier == "tier1"
        assert source.credibility_base_score == 85.0
        assert source.rate_limit.requests_per_minute == 50
        assert source.provides_metadata.author is True
        assert source.provides_metadata.views is True

    def test_minimal_dict(self) -> None:
        """최소 필드 (기본값 적용)."""
        data = {"id": "minimal", "name": "Min"}
        source = NewsSource.from_dict(data)
        assert source.tier == "tier2"
        assert source.credibility_base_score == 70.0
        assert source.rate_limit.requests_per_minute == 60
        assert source.is_active is True

    def test_tier_weight_property(self) -> None:
        """각 Tier 가중치."""
        for tier, expected in [("whitelist", 1.0), ("tier1", 0.95), ("tier2", 0.80), ("tier3", 0.60), ("blacklist", 0.0)]:
            source = NewsSource.from_dict({"id": f"test_{tier}", "name": "T", "tier": tier})
            assert source.tier_weight == expected
