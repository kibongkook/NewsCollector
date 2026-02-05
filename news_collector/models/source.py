"""뉴스 소스 데이터 모델 (후속 모듈에서 구현 예정)"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class NewsSource:
    """Module 2 출력: 뉴스 소스 메타데이터."""

    id: str = ""
    name: str = ""
    tier: str = "tier2"
    ingestion_type: str = "rss"
    base_url: str = ""
    default_locale: str = "ko_KR"
    default_timezone: str = "Asia/Seoul"
    supported_locales: List[str] = field(default_factory=list)
    supported_categories: List[str] = field(default_factory=list)
    credibility_base_score: float = 70.0
    is_active: bool = True
    last_crawled: Optional[datetime] = None
