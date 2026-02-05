"""뉴스 데이터 모델 (후속 모듈에서 구현 예정)"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class NormalizedNews:
    """Module 4 출력: 정규화된 뉴스 기사."""

    id: str = ""
    source_id: str = ""
    source_name: str = ""
    title: str = ""
    body: str = ""
    summary: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    url: str = ""
    language: str = "ko"
    country: str = "KR"
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    image_urls: List[str] = field(default_factory=list)
    view_count: Optional[int] = None
    share_count: Optional[int] = None
    comment_count: Optional[int] = None
