"""뉴스 소스 데이터 모델"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class RateLimit:
    """소스별 요청 제한."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    daily_quota: int = 10000


@dataclass
class ProvidesMetadata:
    """소스가 제공하는 메타데이터 여부."""

    author: bool = False
    views: bool = False
    shares: bool = False
    comments: bool = False
    publish_date: bool = True


@dataclass
class NewsSource:
    """뉴스 소스 메타데이터."""

    # 식별자
    id: str = ""
    name: str = ""

    # 수집 방식
    ingestion_type: str = "rss"  # "api", "rss", "web_crawl"
    base_url: str = ""

    # 로케일 설정
    default_locale: str = "ko_KR"
    default_timezone: str = "Asia/Seoul"
    supported_locales: List[str] = field(default_factory=lambda: ["ko_KR"])
    supported_categories: List[str] = field(default_factory=list)

    # 신뢰도 등급
    tier: str = "tier2"  # "whitelist", "tier1", "tier2", "tier3", "blacklist"
    credibility_base_score: float = 70.0

    # Rate Limiting & 캐시
    rate_limit: RateLimit = field(default_factory=RateLimit)
    cache_ttl_minutes: int = 30

    # 크롤링 정책
    respect_robots_txt: bool = True
    crawl_delay_seconds: int = 1
    user_agent: str = "NewsCollector/1.0"

    # 메타데이터 제공 여부
    provides_metadata: ProvidesMetadata = field(default_factory=ProvidesMetadata)

    # 상태
    is_active: bool = True
    last_crawled: Optional[datetime] = None
    last_success: Optional[datetime] = None
    failure_count: int = 0

    @property
    def tier_weight(self) -> float:
        """Tier에 따른 가중치 반환."""
        weights = {
            "whitelist": 1.0,
            "tier1": 0.95,
            "tier2": 0.80,
            "tier3": 0.60,
            "blacklist": 0.0,
        }
        return weights.get(self.tier, 0.5)

    @classmethod
    def from_dict(cls, data: Dict) -> "NewsSource":
        """딕셔너리에서 NewsSource 생성."""
        rate_limit_data = data.get("rate_limit", {})
        rate_limit = RateLimit(
            requests_per_minute=rate_limit_data.get("requests_per_minute", 60),
            requests_per_hour=rate_limit_data.get("requests_per_hour", 1000),
            daily_quota=rate_limit_data.get("daily_quota", 10000),
        )

        metadata_data = data.get("provides_metadata", {})
        provides_metadata = ProvidesMetadata(
            author=metadata_data.get("author", False),
            views=metadata_data.get("views", False),
            shares=metadata_data.get("shares", False),
            comments=metadata_data.get("comments", False),
            publish_date=metadata_data.get("publish_date", True),
        )

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            ingestion_type=data.get("ingestion_type", "rss"),
            base_url=data.get("base_url", ""),
            default_locale=data.get("default_locale", "ko_KR"),
            default_timezone=data.get("default_timezone", "Asia/Seoul"),
            supported_locales=data.get("supported_locales", ["ko_KR"]),
            supported_categories=data.get("supported_categories", []),
            tier=data.get("tier", "tier2"),
            credibility_base_score=float(data.get("credibility_base_score", 70.0)),
            rate_limit=rate_limit,
            cache_ttl_minutes=data.get("cache_ttl_minutes", 30),
            respect_robots_txt=data.get("respect_robots_txt", True),
            crawl_delay_seconds=data.get("crawl_delay_seconds", 1),
            user_agent=data.get("user_agent", "NewsCollector/1.0"),
            provides_metadata=provides_metadata,
            is_active=data.get("is_active", True),
            failure_count=data.get("failure_count", 0),
        )


@dataclass
class TierDefinition:
    """신뢰도 Tier 정의."""

    name: str = ""
    description: str = ""
    base_credibility: float = 70.0
    weight: float = 0.8
