"""Module 5: Dedup & Clustering - 중복 제거 및 이슈 묶기"""

import hashlib
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from news_collector.models.news import NormalizedNews
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class DeduplicationEngine:
    """
    Module 5: 중복 뉴스 제거 및 유사 뉴스 클러스터링.

    1단계: URL 기반 정확한 중복 제거
    2단계: 제목 해시 기반 정확한 중복 제거
    3단계: Jaccard 유사도 기반 클러스터링
    """

    def __init__(self, similarity_threshold: float = 0.6) -> None:
        self._threshold = similarity_threshold

    def deduplicate(self, news_list: List[NormalizedNews]) -> List[NormalizedNews]:
        """
        중복 제거 + 클러스터링 후 대표 뉴스 반환.

        Args:
            news_list: 정규화된 뉴스 리스트.

        Returns:
            중복 제거된 뉴스 리스트 (클러스터 대표).
        """
        if not news_list:
            return []

        original_count = len(news_list)

        # 1단계: URL 기반 중복 제거
        by_url = self._dedup_by_url(news_list)
        after_url = len(by_url)

        # 2단계: 제목 해시 기반 중복 제거
        by_title = self._dedup_by_title_hash(by_url)
        after_title = len(by_title)

        # 3단계: 유사도 기반 클러스터링
        clustered = self._cluster_similar(by_title)
        after_cluster = len(clustered)

        logger.info(
            "중복 제거 완료: %d → URL(%d) → 제목(%d) → 클러스터(%d)",
            original_count, after_url, after_title, after_cluster,
        )
        return clustered

    def _dedup_by_url(self, news_list: List[NormalizedNews]) -> List[NormalizedNews]:
        """URL 정규화 후 중복 제거."""
        seen: Dict[str, NormalizedNews] = {}
        for news in news_list:
            norm_url = self._normalize_url(news.url)
            if norm_url not in seen:
                seen[norm_url] = news
        return list(seen.values())

    def _dedup_by_title_hash(self, news_list: List[NormalizedNews]) -> List[NormalizedNews]:
        """제목 MD5 해시 기반 중복 제거."""
        seen: Dict[str, NormalizedNews] = {}
        for news in news_list:
            title_hash = hashlib.md5(news.title.strip().lower().encode()).hexdigest()
            if title_hash not in seen:
                seen[title_hash] = news
        return list(seen.values())

    def _cluster_similar(self, news_list: List[NormalizedNews]) -> List[NormalizedNews]:
        """Jaccard 유사도 기반 클러스터링, 대표 뉴스 선정."""
        if len(news_list) < 2:
            return news_list

        used: Set[int] = set()
        representatives: List[NormalizedNews] = []

        for i, news_i in enumerate(news_list):
            if i in used:
                continue

            cluster_ids = [news_i.id]
            used.add(i)

            for j in range(i + 1, len(news_list)):
                if j in used:
                    continue
                sim = self._jaccard_similarity(news_i.title, news_list[j].title)
                if sim >= self._threshold:
                    cluster_ids.append(news_list[j].id)
                    used.add(j)

            # 클러스터 대표 선정: 가장 긴 본문
            cluster_members = [news_list[k] for k in range(len(news_list)) if news_list[k].id in cluster_ids]
            best = max(cluster_members, key=lambda n: len(n.body))

            if len(cluster_ids) > 1:
                best.cluster_id = str(uuid.uuid4())
                logger.debug("클러스터 생성: %d건 → 대표: %s", len(cluster_ids), best.title[:50])

            representatives.append(best)

        return representatives

    @staticmethod
    def _normalize_url(url: str) -> str:
        """URL 정규화 (쿼리 파라미터/프래그먼트 제거)."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".lower().rstrip("/")

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """단어 기반 Jaccard 유사도 (0~1)."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union
