"""Module 9: Ranker 테스트"""

from datetime import datetime, timezone, timedelta

import pytest

from news_collector.ranking.ranker import Ranker, RANKING_PRESETS, DEFAULT_WEIGHTS
from news_collector.models.news import NormalizedNews, NewsWithScores


# ─── Fixture ────────────────────────────────────────────

def _make_news(
    id: str = "1",
    title: str = "한국 경제 성장률 2.5% 전망 발표",
    body: str = '관계자는 "올해 경제 성장률은 2.5%"라고 밝혔다. 보고서에 따르면 1000억 규모의 투자가 진행된다. 전문가들은 긍정적 전망을 내놓았다.',
    source_id: str = "source_a",
    source_tier: str = "tier1",
    url: str = "https://example.com/1",
    **kwargs,
) -> NormalizedNews:
    return NormalizedNews(
        id=id, title=title, body=body,
        source_id=source_id, source_tier=source_tier, url=url,
        published_at=datetime.now(timezone.utc),
        view_count=100, share_count=10, comment_count=5,
        **kwargs,
    )


def _make_scored(**kwargs) -> NewsWithScores:
    defaults = {
        "id": "1", "title": "Test", "body": "Body",
        "source_id": "src", "source_tier": "tier1", "url": "https://example.com/1",
        "integrity_score": 0.8,
        "credibility_score": 0.7,
        "quality_score": 0.6,
        "popularity_score": 0.5,
        "spam_score": 0.1,
    }
    defaults.update(kwargs)
    return NewsWithScores(**defaults)


# ═══════════════════════════════════════════════════════════
# 최종 점수 계산 테스트
# ═══════════════════════════════════════════════════════════

class TestCalculateFinalScore:
    """최종 가중 점수 계산 테스트."""

    def setup_method(self):
        self.ranker = Ranker()

    def test_equal_weights(self):
        news = _make_scored(
            popularity_score=1.0,
            relevance_score=1.0,
            quality_score=1.0,
            credibility_score=1.0,
        )
        score = self.ranker._calculate_final_score(news, DEFAULT_WEIGHTS)
        assert score == 100.0

    def test_zero_scores(self):
        news = _make_scored(
            popularity_score=0.0,
            relevance_score=0.0,
            quality_score=0.0,
            credibility_score=0.0,
        )
        score = self.ranker._calculate_final_score(news, DEFAULT_WEIGHTS)
        assert score == 0.0

    def test_quality_preset_weights(self):
        news = _make_scored(
            popularity_score=0.5,
            integrity_score=0.8,
            quality_score=0.9,
            credibility_score=0.7,
        )
        score = self.ranker._calculate_final_score(news, RANKING_PRESETS["quality"])
        assert 0 < score < 100


# ═══════════════════════════════════════════════════════════
# 정책 필터 테스트
# ═══════════════════════════════════════════════════════════

class TestPolicyFilter:
    """정책 필터 테스트."""

    def setup_method(self):
        self.ranker = Ranker()

    def test_pass_filter(self):
        news_list = [_make_scored(integrity_score=0.8, credibility_score=0.7, spam_score=0.1)]
        result = self.ranker._apply_policy_filter(news_list)
        assert len(result) == 1

    def test_low_integrity_filtered(self):
        news_list = [_make_scored(integrity_score=0.3, credibility_score=0.7, spam_score=0.1)]
        result = self.ranker._apply_policy_filter(news_list)
        assert len(result) == 0

    def test_high_spam_filtered(self):
        news_list = [_make_scored(integrity_score=0.8, credibility_score=0.7, spam_score=0.8)]
        result = self.ranker._apply_policy_filter(news_list)
        assert len(result) == 0

    def test_low_credibility_flagged_but_kept(self):
        news_list = [_make_scored(integrity_score=0.8, credibility_score=0.3, spam_score=0.1)]
        result = self.ranker._apply_policy_filter(news_list)
        assert len(result) == 1
        assert "suspicious_credibility" in result[0].policy_flags

    def test_mixed_filtering(self):
        news_list = [
            _make_scored(id="good", integrity_score=0.8, credibility_score=0.7, spam_score=0.1),
            _make_scored(id="bad_integrity", integrity_score=0.2, credibility_score=0.7, spam_score=0.1),
            _make_scored(id="spam", integrity_score=0.8, credibility_score=0.7, spam_score=0.9),
        ]
        result = self.ranker._apply_policy_filter(news_list)
        assert len(result) == 1
        assert result[0].id == "good"


# ═══════════════════════════════════════════════════════════
# 다양성 보장 테스트
# ═══════════════════════════════════════════════════════════

class TestDiversity:
    """소스 다양성 보장 테스트."""

    def setup_method(self):
        self.ranker = Ranker()

    def test_max_same_source(self):
        """같은 소스 최대 3개."""
        news_list = [
            _make_scored(id=str(i), source_id="same_source")
            for i in range(10)
        ]
        result = self.ranker._ensure_diversity(news_list)
        assert len(result) == 3

    def test_different_sources_all_kept(self):
        news_list = [
            _make_scored(id=str(i), source_id=f"source_{i}")
            for i in range(5)
        ]
        result = self.ranker._ensure_diversity(news_list)
        assert len(result) == 5

    def test_mixed_sources(self):
        news_list = [
            _make_scored(id="1", source_id="src_a"),
            _make_scored(id="2", source_id="src_a"),
            _make_scored(id="3", source_id="src_a"),
            _make_scored(id="4", source_id="src_a"),  # 4번째 → 제외
            _make_scored(id="5", source_id="src_b"),
        ]
        result = self.ranker._ensure_diversity(news_list)
        assert len(result) == 4  # src_a 3개 + src_b 1개

    def test_same_source_id_fallback_to_name(self):
        """source_id가 모두 같으면 source_name으로 다양성 판단."""
        news_list = [
            _make_scored(id="1", source_id="google_news", source_name="BBC"),
            _make_scored(id="2", source_id="google_news", source_name="BBC"),
            _make_scored(id="3", source_id="google_news", source_name="BBC"),
            _make_scored(id="4", source_id="google_news", source_name="BBC"),  # 4번째 → 제외
            _make_scored(id="5", source_id="google_news", source_name="CNN"),
            _make_scored(id="6", source_id="google_news", source_name="Reuters"),
        ]
        result = self.ranker._ensure_diversity(news_list)
        assert len(result) == 5  # BBC 3개 + CNN 1개 + Reuters 1개


# ═══════════════════════════════════════════════════════════
# rank() 전체 파이프라인 테스트
# ═══════════════════════════════════════════════════════════

class TestRankPipeline:
    """전체 랭킹 파이프라인 테스트."""

    def setup_method(self):
        self.ranker = Ranker()

    def test_empty_list(self):
        assert self.ranker.rank([]) == []

    def test_basic_ranking(self):
        news_list = [
            _make_news(id="1", source_id="src_a", url="https://a.com/1"),
            _make_news(id="2", source_id="src_b", url="https://b.com/2"),
            _make_news(id="3", source_id="src_c", url="https://c.com/3"),
        ]
        results = self.ranker.rank(news_list, preset="quality", limit=10)
        assert len(results) > 0
        assert all(isinstance(r, NewsWithScores) for r in results)
        # 순위 할당 확인
        for i, r in enumerate(results):
            assert r.rank_position == i + 1
            assert r.final_score >= 0

    def test_limit_respected(self):
        news_list = [
            _make_news(id=str(i), source_id=f"src_{i}", url=f"https://example.com/{i}")
            for i in range(10)
        ]
        results = self.ranker.rank(news_list, limit=3)
        assert len(results) <= 3

    def test_presets(self):
        news_list = [
            _make_news(id="1", source_id="src_a", url="https://a.com/1"),
        ]
        for preset in ["quality", "trending", "credible", "latest"]:
            results = self.ranker.rank(news_list, preset=preset)
            assert len(results) > 0

    def test_unknown_preset_uses_defaults(self):
        news_list = [_make_news()]
        results = self.ranker.rank(news_list, preset="nonexistent")
        assert len(results) > 0

    def test_ranking_order(self):
        """점수 높은 기사가 먼저 와야 함."""
        news_list = [
            _make_news(id="1", source_id="src_a", url="https://a.com/1"),
            _make_news(id="2", source_id="src_b", url="https://b.com/2"),
        ]
        results = self.ranker.rank(news_list, preset="quality")
        if len(results) >= 2:
            assert results[0].final_score >= results[1].final_score

    def test_latest_preset_no_crash_on_none_published_at(self):
        """latest 프리셋에서 published_at=None이어도 크래시 없이 정렬."""
        news_list = [
            _make_news(id="1", source_id="src_a", url="https://a.com/1"),
            NormalizedNews(id="2", title="No date news", body="Body text", source_id="src_b", url="https://b.com/2"),
        ]
        results = self.ranker.rank(news_list, preset="latest")
        assert len(results) > 0


# ═══════════════════════════════════════════════════════════
# 프리셋 설정 테스트
# ═══════════════════════════════════════════════════════════

class TestPresets:
    """랭킹 프리셋 설정 테스트."""

    def test_all_presets_sum_to_one(self):
        for name, weights in RANKING_PRESETS.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.01, f"프리셋 {name}의 가중치 합 = {total}"

    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_preset_keys(self):
        expected_keys = {"popularity", "relevance", "quality", "credibility"}
        for name, weights in RANKING_PRESETS.items():
            assert set(weights.keys()) == expected_keys, f"프리셋 {name} 키 불일치"
