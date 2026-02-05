"""수집 커넥터 베이스 클래스"""

from abc import ABC, abstractmethod
from typing import List

from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource


class BaseConnector(ABC):
    """모든 수집 커넥터의 추상 베이스."""

    def __init__(self, source: NewsSource) -> None:
        self.source = source

    @abstractmethod
    async def fetch(self, keywords: List[str] = None, limit: int = 20) -> List[RawNewsRecord]:
        """소스에서 뉴스 수집."""
        ...
