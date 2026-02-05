"""뉴스 데이터 모델"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class NormalizedNews:
    """Module 4 출력: 정규화된 뉴스 기사."""

    id: str = ""
    raw_record_id: str = ""
    source_id: str = ""
    source_name: str = ""
    source_tier: str = "tier2"

    # 핵심 콘텐츠
    title: str = ""
    body: str = ""
    summary: Optional[str] = None

    # 메타데이터
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # 분류
    language: str = "ko"
    country: str = "KR"
    category: Optional[str] = None
    section: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # 인기도 메타
    view_count: Optional[int] = None
    share_count: Optional[int] = None
    comment_count: Optional[int] = None
    like_count: Optional[int] = None

    # 참조
    url: str = ""
    image_urls: List[str] = field(default_factory=list)

    # 처리 타임스탬프
    crawl_timestamp: Optional[datetime] = None
    normalized_timestamp: Optional[datetime] = None

    # 클러스터 (Module 5에서 설정)
    cluster_id: Optional[str] = None


@dataclass
class NewsWithScores(NormalizedNews):
    """Module 6~9 출력: 점수가 포함된 최종 뉴스 객체."""

    # Module 6: Content Integrity
    integrity_score: float = 0.0
    title_body_consistency: float = 0.0
    contamination_score: float = 0.0
    spam_score: float = 0.0
    integrity_flags: List[str] = field(default_factory=list)

    # Module 7: Credibility & Quality
    credibility_score: float = 0.0
    quality_score: float = 0.0
    evidence_score: float = 0.0
    sensationalism_penalty: float = 0.0

    # Module 8: Popularity
    popularity_score: float = 0.0
    trending_velocity: float = 0.0

    # Module 9: Final
    final_score: float = 0.0
    rank_position: int = 0
    policy_flags: List[str] = field(default_factory=list)
