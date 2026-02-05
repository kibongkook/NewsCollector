"""원본 뉴스 레코드 데이터 모델"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class RawNewsRecord:
    """Module 3 출력: 소스에서 수집된 원본 뉴스 레코드."""

    source_id: str = ""
    source_name: str = ""

    # 원본 데이터
    raw_html: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    extracted_text: str = ""

    # 메타데이터
    url: str = ""
    fetch_timestamp: Optional[datetime] = None
    page_charset: str = "utf-8"
    page_language: str = "ko"

    # Crawling 메타
    http_status: int = 200
    response_time_ms: int = 0

    # ID (자동 생성)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id and self.url:
            raw = f"{self.source_id}:{self.url}"
            self.id = hashlib.md5(raw.encode()).hexdigest()
        if self.fetch_timestamp is None:
            self.fetch_timestamp = datetime.now()
