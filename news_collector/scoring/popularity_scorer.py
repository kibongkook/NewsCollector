"""Module 8: Popularity Engine - 인기도 점수"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from news_collector.models.news import NormalizedNews
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


class PopularityScorer:
    """
    Module 8: 조회/공유/댓글 기반 인기도 점수.

    가중치: 조회 40%, 공유 35%, 댓글 25%
    """

    def __init__(
        self,
        view_weight: float = 0.4,
        share_weight: float = 0.35,
        comment_weight: float = 0.25,
        freshness_half_life_hours: float = 24.0,
    ) -> None:
        self._view_weight = view_weight
        self._share_weight = share_weight
        self._comment_weight = comment_weight
        self._half_life = freshness_half_life_hours

    def score(
        self,
        news: NormalizedNews,
        all_news: Optional[List[NormalizedNews]] = None,
    ) -> Dict[str, float]:
        """
        인기도 + 트렌딩 속도 산출.

        Returns:
            {"popularity_score": 0~1, "trending_velocity": 0~1}
        """
        all_news = all_news or []

        # 정규화를 위한 최대값 수집
        max_views = max((n.view_count or 0 for n in all_news), default=1) or 1
        max_shares = max((n.share_count or 0 for n in all_news), default=1) or 1
        max_comments = max((n.comment_count or 0 for n in all_news), default=1) or 1

        # 개별 지표 정규화 (0~1)
        norm_views = (news.view_count or 0) / max_views
        norm_shares = (news.share_count or 0) / max_shares
        norm_comments = (news.comment_count or 0) / max_comments

        # 가중 합산
        popularity = (
            norm_views * self._view_weight
            + norm_shares * self._share_weight
            + norm_comments * self._comment_weight
        )

        # 인기도 메트릭이 전혀 없으면 신선도 기반 추정
        has_metrics = any([news.view_count, news.share_count, news.comment_count])
        if not has_metrics:
            popularity = self._freshness_score(news)

        trending = self._trending_velocity(news)

        return {
            "popularity_score": round(min(1.0, popularity), 3),
            "trending_velocity": round(trending, 3),
        }

    def _freshness_score(self, news: NormalizedNews) -> float:
        """발행일 기반 신선도 점수 (0~1, 반감기 적용)."""
        if not news.published_at:
            return 0.3

        now = datetime.now(timezone.utc)
        pub = news.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        hours_ago = max(0, (now - pub).total_seconds() / 3600)
        # 지수 감쇠
        return 0.5 ** (hours_ago / self._half_life)

    def _trending_velocity(self, news: NormalizedNews) -> float:
        """트렌딩 속도: 시간 대비 인기도 상승률."""
        if not news.published_at:
            return 0.0

        now = datetime.now(timezone.utc)
        pub = news.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)

        hours_ago = max(1, (now - pub).total_seconds() / 3600)
        total_engagement = (news.view_count or 0) + (news.share_count or 0) * 3 + (news.comment_count or 0) * 2

        if total_engagement == 0:
            return 0.0

        velocity = total_engagement / hours_ago
        # 정규화 (10000/h를 1.0으로)
        return min(1.0, velocity / 10000)
