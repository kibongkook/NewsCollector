"""Module 8: PopularityScorer 테스트"""

from datetime import datetime, timezone, timedelta

import pytest

from news_collector.scoring.popularity_scorer import PopularityScorer
from news_collector.models.news import NormalizedNews


# ─── Fixture ────────────────────────────────────────────

def _make_news(
    view_count=None,
    share_count=None,
    comment_count=None,
    published_at=None,
    **kwargs,
) -> NormalizedNews:
    defaults = {"id": "1", "title": "테스트 뉴스", "body": "본문", "source_id": "test", "url": "https://example.com/1"}
    defaults.update(kwargs)
    return NormalizedNews(
        view_count=view_count,
        share_count=share_count,
        comment_count=comment_count,
        published_at=published_at,
        **defaults,
    )


def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════
# 인기도 점수 테스트
# ═══════════════════════════════════════════════════════════

class TestPopularityScore:
    """인기도 점수 테스트."""

    def setup_method(self):
        self.scorer = PopularityScorer()

    def test_high_metrics(self):
        news = _make_news(view_count=10000, share_count=500, comment_count=200)
        all_news = [news]
        result = self.scorer.score(news, all_news)
        assert result["popularity_score"] == 1.0  # 유일한 기사 = 최대값

    def test_relative_scoring(self):
        low = _make_news(id="1", view_count=100, share_count=10, comment_count=5, url="https://a.com/1")
        high = _make_news(id="2", view_count=10000, share_count=500, comment_count=200, url="https://b.com/2")
        all_news = [low, high]

        low_score = self.scorer.score(low, all_news)
        high_score = self.scorer.score(high, all_news)
        assert low_score["popularity_score"] < high_score["popularity_score"]

    def test_no_metrics_uses_freshness(self):
        news = _make_news(published_at=_now())
        result = self.scorer.score(news, [news])
        assert result["popularity_score"] > 0  # 신선도 기반

    def test_no_metrics_no_date(self):
        news = _make_news()
        result = self.scorer.score(news, [news])
        assert result["popularity_score"] == 0.3  # 기본 신선도

    def test_score_range(self):
        news = _make_news(view_count=50, share_count=5, comment_count=2)
        result = self.scorer.score(news, [news])
        assert 0 <= result["popularity_score"] <= 1


# ═══════════════════════════════════════════════════════════
# 신선도 점수 테스트
# ═══════════════════════════════════════════════════════════

class TestFreshnessScore:
    """신선도 점수 테스트."""

    def setup_method(self):
        self.scorer = PopularityScorer(freshness_half_life_hours=24.0)

    def test_just_published(self):
        news = _make_news(published_at=_now())
        score = self.scorer._freshness_score(news)
        assert score > 0.9  # 방금 발행

    def test_one_day_old(self):
        news = _make_news(published_at=_now() - timedelta(hours=24))
        score = self.scorer._freshness_score(news)
        assert 0.4 < score < 0.6  # 반감기

    def test_very_old(self):
        news = _make_news(published_at=_now() - timedelta(days=7))
        score = self.scorer._freshness_score(news)
        assert score < 0.1

    def test_no_published_at(self):
        news = _make_news()
        score = self.scorer._freshness_score(news)
        assert score == 0.3

    def test_naive_datetime_handled(self):
        """tzinfo 없는 datetime도 처리."""
        news = _make_news(published_at=datetime.now())
        score = self.scorer._freshness_score(news)
        assert score > 0.8


# ═══════════════════════════════════════════════════════════
# 트렌딩 속도 테스트
# ═══════════════════════════════════════════════════════════

class TestTrendingVelocity:
    """트렌딩 속도 테스트."""

    def setup_method(self):
        self.scorer = PopularityScorer()

    def test_high_velocity(self):
        news = _make_news(
            view_count=50000,
            share_count=5000,
            comment_count=3000,
            published_at=_now() - timedelta(hours=1),
        )
        velocity = self.scorer._trending_velocity(news)
        assert velocity > 0

    def test_no_engagement(self):
        news = _make_news(published_at=_now())
        velocity = self.scorer._trending_velocity(news)
        assert velocity == 0.0

    def test_no_published_at(self):
        news = _make_news(view_count=100)
        velocity = self.scorer._trending_velocity(news)
        assert velocity == 0.0

    def test_velocity_capped(self):
        news = _make_news(
            view_count=1000000,
            share_count=100000,
            comment_count=100000,
            published_at=_now() - timedelta(hours=1),
        )
        velocity = self.scorer._trending_velocity(news)
        assert velocity <= 1.0


# ═══════════════════════════════════════════════════════════
# score() 종합 테스트
# ═══════════════════════════════════════════════════════════

class TestPopularityScorerIntegration:
    """종합 score() 테스트."""

    def setup_method(self):
        self.scorer = PopularityScorer()

    def test_result_structure(self):
        news = _make_news(view_count=100)
        result = self.scorer.score(news, [news])
        assert "popularity_score" in result
        assert "trending_velocity" in result

    def test_empty_all_news(self):
        news = _make_news(view_count=100)
        result = self.scorer.score(news, [])
        assert result["popularity_score"] >= 0
