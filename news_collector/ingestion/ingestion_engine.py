"""Module 3: Ingestion Engine - 다중 소스 병렬 수집 오케스트레이터"""

import asyncio
from typing import Any, Dict, List, Optional

from news_collector.ingestion.base_connector import BaseConnector
from news_collector.ingestion.api_connector import APIConnector
from news_collector.ingestion.rss_connector import RSSConnector
from news_collector.models.query_spec import QuerySpec
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource
from news_collector.registry.source_registry import SourceRegistry
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionEngine:
    """
    Module 3: 다중 소스에서 병렬로 뉴스 수집.

    사용법:
        engine = IngestionEngine(registry)
        records = engine.collect(query_spec)
    """

    def __init__(
        self,
        registry: SourceRegistry,
        api_credentials: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> None:
        """
        Args:
            registry: 소스 레지스트리.
            api_credentials: {"source_id": {"api_key": "...", "api_secret": "..."}}
        """
        self._registry = registry
        self._api_credentials = api_credentials or {}

    def collect(self, query_spec: QuerySpec) -> List[RawNewsRecord]:
        """
        QuerySpec 기반으로 소스 선택 후 병렬 수집.

        Returns:
            수집된 RawNewsRecord 리스트.
        """
        sources = self._registry.select_sources(
            categories=query_spec.category,
            locale=query_spec.locale,
            verified_only=query_spec.verified_sources_only,
        )

        if not sources:
            logger.warning("수집 가능한 소스가 없습니다")
            return []

        logger.info("수집 시작: %d개 소스 → %s", len(sources), [s.id for s in sources])

        # 비동기 수집 실행
        try:
            # Python 3.10+에서도 안전한 이벤트 루프 감지
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 이미 이벤트 루프가 실행 중이면 (Jupyter 등)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    results = pool.submit(
                        asyncio.run, self._collect_all(sources, query_spec)
                    ).result()
            else:
                results = asyncio.run(self._collect_all(sources, query_spec))
        except RuntimeError:
            results = asyncio.run(self._collect_all(sources, query_spec))

        logger.info("수집 완료: 총 %d건", len(results))
        return results

    async def _collect_all(
        self, sources: List[NewsSource], query_spec: QuerySpec
    ) -> List[RawNewsRecord]:
        """모든 소스에서 병렬 수집."""
        tasks = []
        for source in sources:
            connector = self._create_connector(source)
            if connector:
                tasks.append(self._collect_from_source(connector, source, query_spec))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_records: List[RawNewsRecord] = []
        for i, result in enumerate(results):
            source = sources[i] if i < len(sources) else None
            if isinstance(result, Exception):
                logger.error("소스 수집 실패: %s - %s", source.id if source else "?", result)
                if source:
                    self._registry.record_failure(source.id)
            elif isinstance(result, list):
                all_records.extend(result)
                if source:
                    self._registry.record_success(source.id)

        return all_records

    async def _collect_from_source(
        self, connector: BaseConnector, source: NewsSource, query_spec: QuerySpec
    ) -> List[RawNewsRecord]:
        """단일 소스에서 수집."""
        keywords = query_spec.keywords or []
        return await connector.fetch(keywords=keywords, limit=query_spec.limit)

    def _create_connector(self, source: NewsSource) -> Optional[BaseConnector]:
        """소스 타입에 맞는 커넥터 생성."""
        if source.ingestion_type == "rss":
            return RSSConnector(source)
        elif source.ingestion_type == "api":
            creds = self._api_credentials.get(source.id, {})
            return APIConnector(
                source,
                api_key=creds.get("api_key", ""),
                api_secret=creds.get("api_secret", ""),
            )
        elif source.ingestion_type == "web_crawl":
            logger.debug("웹 크롤러는 별도 구현 필요: %s", source.id)
            return None
        else:
            logger.warning("알 수 없는 수집 타입: %s (%s)", source.ingestion_type, source.id)
            return None
