"""Module 9: Ranker & Policy Filter - 최종 점수 계산 및 랭킹"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from news_collector.models.news import NormalizedNews, NewsWithScores
from news_collector.integrity.integrity_checker import ContentIntegrityChecker
from news_collector.scoring.credibility_scorer import CredibilityScorer
from news_collector.scoring.popularity_scorer import PopularityScorer
from news_collector.registry.source_registry import SourceRegistry
from news_collector.utils.config_manager import ConfigManager
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_WEIGHTS = {
    "popularity": 0.25,
    "relevance": 0.25,
    "quality": 0.25,
    "credibility": 0.25,
}

RANKING_PRESETS = {
    "quality": {"popularity": 0.15, "relevance": 0.30, "quality": 0.40, "credibility": 0.15},
    "trending": {"popularity": 0.50, "relevance": 0.10, "quality": 0.20, "credibility": 0.20},
    "credible": {"popularity": 0.10, "relevance": 0.20, "quality": 0.20, "credibility": 0.50},
    "latest": {"popularity": 0.10, "relevance": 0.20, "quality": 0.30, "credibility": 0.40},
}


class Ranker:
    """
    Module 9: 최종 점수 계산, 정책 필터, 다양성 보장, 랭킹.

    사용법:
        ranker = Ranker(config, registry)
        results = ranker.rank(news_list, preset="quality")
    """

    def __init__(
        self,
        config: Optional[ConfigManager] = None,
        registry: Optional[SourceRegistry] = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._integrity_checker = ContentIntegrityChecker()
        self._credibility_scorer = CredibilityScorer(registry)
        self._popularity_scorer = PopularityScorer()

        # 설정에서 임계값 로드
        if config:
            self._integrity_threshold = config.get("scoring.integrity_threshold", 0.5)
            self._credibility_threshold = config.get("scoring.credibility_threshold", 0.6)
            self._max_same_source = config.get("scoring.source_diversity.max_same_source_in_top_n", 3)
        else:
            self._integrity_threshold = 0.5
            self._credibility_threshold = 0.6
            self._max_same_source = 3

    def rank(
        self,
        news_list: List[NormalizedNews],
        preset: str = "quality",
        limit: int = 20,
    ) -> List[NewsWithScores]:
        """
        전체 파이프라인: 점수 산출 → 정책 필터 → 다양성 → 정렬 → Top-N.

        Args:
            news_list: 정규화된 뉴스 리스트.
            preset: 랭킹 프리셋 (quality/trending/credible/latest).
            limit: 반환 수.

        Returns:
            점수 포함된 정렬된 뉴스 리스트.
        """
        if not news_list:
            return []

        weights = RANKING_PRESETS.get(preset, DEFAULT_WEIGHTS)
        logger.info("랭킹 시작: %d건, 프리셋=%s", len(news_list), preset)

        # 1. 점수 산출
        scored = self._score_all(news_list)

        # 2. 최종 점수 계산
        for news in scored:
            news.final_score = self._calculate_final_score(news, weights)

        # 3. 정책 필터
        filtered = self._apply_policy_filter(scored)

        # 4. 정렬
        _epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        if preset == "latest":
            filtered.sort(
                key=lambda n: n.published_at if n.published_at else _epoch,
                reverse=True,
            )
        else:
            filtered.sort(key=lambda n: n.final_score, reverse=True)

        # 5. 다양성 보장
        diverse = self._ensure_diversity(filtered)

        # 6. Top-N + 순위 할당
        results = diverse[:limit]
        for i, news in enumerate(results):
            news.rank_position = i + 1

        logger.info("랭킹 완료: %d → 필터(%d) → 최종(%d)", len(news_list), len(filtered), len(results))
        return results

    def _score_all(self, news_list: List[NormalizedNews]) -> List[NewsWithScores]:
        """모든 뉴스에 Module 6/7/8 점수 산출."""
        scored: List[NewsWithScores] = []

        for news in news_list:
            nws = NewsWithScores(**{
                k: v for k, v in news.__dict__.items()
                if k in NormalizedNews.__dataclass_fields__
            })

            # Module 6: Integrity
            integrity, details = self._integrity_checker.assess(news)
            nws.integrity_score = integrity
            nws.title_body_consistency = details["title_body_consistency"]
            nws.contamination_score = details["contamination_score"]
            nws.spam_score = details["spam_score"]
            nws.integrity_flags = details.get("contamination_flags", []) + details.get("spam_flags", [])

            # Module 7: Credibility & Quality
            cred = self._credibility_scorer.score(news, news_list)
            nws.credibility_score = cred["credibility_score"]
            nws.quality_score = cred["quality_score"]
            nws.evidence_score = cred["evidence_score"]
            nws.sensationalism_penalty = cred["sensationalism_penalty"]

            # Module 8: Popularity
            pop = self._popularity_scorer.score(news, news_list)
            nws.popularity_score = pop["popularity_score"]
            nws.trending_velocity = pop["trending_velocity"]

            scored.append(nws)

        return scored

    def _calculate_final_score(self, news: NewsWithScores, weights: Dict[str, float]) -> float:
        """가중 평균으로 최종 점수 (0~100) 계산."""
        raw = (
            news.popularity_score * weights.get("popularity", 0.25)
            + news.integrity_score * weights.get("relevance", 0.25)
            + news.quality_score * weights.get("quality", 0.25)
            + news.credibility_score * weights.get("credibility", 0.25)
        )
        return round(raw * 100, 1)

    def _apply_policy_filter(self, scored: List[NewsWithScores]) -> List[NewsWithScores]:
        """정책 필터 적용."""
        result = []
        for news in scored:
            flags = []

            if news.integrity_score < self._integrity_threshold:
                flags.append("low_integrity")
                logger.debug("정책 필터 제외 (무결성): %s", news.title[:30])
                continue

            if news.credibility_score < self._credibility_threshold:
                flags.append("suspicious_credibility")

            if news.spam_score > 0.7:
                flags.append("spam_detected")
                continue

            news.policy_flags = flags
            result.append(news)

        return result

    def _ensure_diversity(self, news_list: List[NewsWithScores]) -> List[NewsWithScores]:
        """소스 다양성 보장 (같은 소스 최대 N개)."""
        source_count: Dict[str, int] = {}
        diverse: List[NewsWithScores] = []

        # source_id가 모두 같으면(예: google_news) source_name 기반으로 전환
        unique_ids = {n.source_id for n in news_list}
        use_name = len(unique_ids) == 1 and len(news_list) > 1

        for news in news_list:
            key = news.source_name if use_name else news.source_id
            count = source_count.get(key, 0)
            if count < self._max_same_source:
                diverse.append(news)
                source_count[key] = count + 1

        return diverse
