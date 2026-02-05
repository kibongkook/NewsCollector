"""Module 7: CredibilityScorer 테스트"""

import pytest

from news_collector.scoring.credibility_scorer import CredibilityScorer, EVIDENCE_PATTERNS, SENSATIONAL_WORDS
from news_collector.models.news import NormalizedNews


# ─── Fixture ────────────────────────────────────────────

def _make_news(
    title: str = "한국 경제 성장률 2.5% 전망",
    body: str = '관계자는 "올해 경제 성장률은 2.5%"라고 밝혔다. 보고서에 따르면 1000억 규모의 투자가 진행된다.',
    source_id: str = "source_a",
    source_tier: str = "tier1",
    **kwargs,
) -> NormalizedNews:
    defaults = {"id": "1", "url": "https://example.com/1"}
    defaults.update(kwargs)
    return NormalizedNews(title=title, body=body, source_id=source_id, source_tier=source_tier, **defaults)


# ═══════════════════════════════════════════════════════════
# 소스 신뢰도 테스트
# ═══════════════════════════════════════════════════════════

class TestSourceTrust:
    """소스 Tier 기반 신뢰도 테스트."""

    def setup_method(self):
        self.scorer = CredibilityScorer()

    def test_whitelist_high(self):
        news = _make_news(source_tier="whitelist")
        score = self.scorer._source_trust_score(news)
        assert score == 0.95

    def test_tier1(self):
        news = _make_news(source_tier="tier1")
        score = self.scorer._source_trust_score(news)
        assert score == 0.85

    def test_tier2(self):
        news = _make_news(source_tier="tier2")
        score = self.scorer._source_trust_score(news)
        assert score == 0.65

    def test_tier3(self):
        news = _make_news(source_tier="tier3")
        score = self.scorer._source_trust_score(news)
        assert score == 0.40

    def test_blacklist(self):
        news = _make_news(source_tier="blacklist")
        score = self.scorer._source_trust_score(news)
        assert score == 0.0

    def test_unknown_tier(self):
        news = _make_news(source_tier="unknown")
        score = self.scorer._source_trust_score(news)
        assert score == 0.5


# ═══════════════════════════════════════════════════════════
# 크로스 소스 보너스 테스트
# ═══════════════════════════════════════════════════════════

class TestCrossSourceBonus:
    """크로스 소스 검증 보너스 테스트."""

    def setup_method(self):
        self.scorer = CredibilityScorer()

    def test_no_other_news(self):
        news = _make_news()
        bonus = self.scorer._cross_source_bonus(news, [])
        assert bonus == 0.0

    def test_similar_from_other_sources(self):
        news = _make_news(id="1", title="한국 경제 성장률 전망 발표", source_id="src_a")
        others = [
            _make_news(id="2", title="한국 경제 성장률 전망 공개", source_id="src_b"),
        ]
        bonus = self.scorer._cross_source_bonus(news, others)
        assert bonus >= 0.05

    def test_three_or_more_cross_sources(self):
        news = _make_news(id="1", title="AI 인공지능 기술 혁신 발표 뉴스", source_id="src_a")
        others = [
            _make_news(id="2", title="AI 인공지능 기술 혁신 발표 소식", source_id="src_b"),
            _make_news(id="3", title="AI 인공지능 기술 혁신 발표 보도", source_id="src_c"),
            _make_news(id="4", title="AI 인공지능 기술 혁신 발표 기사", source_id="src_d"),
        ]
        bonus = self.scorer._cross_source_bonus(news, others)
        assert bonus == 0.15

    def test_unrelated_articles_no_bonus(self):
        news = _make_news(id="1", title="한국 경제 뉴스", source_id="src_a")
        others = [
            _make_news(id="2", title="스포츠 축구 경기 결과", source_id="src_b"),
        ]
        bonus = self.scorer._cross_source_bonus(news, others)
        assert bonus == 0.0

    def test_short_title_no_bonus(self):
        news = _make_news(id="1", title="뉴스", source_id="src_a")
        others = [_make_news(id="2", title="뉴스", source_id="src_b")]
        bonus = self.scorer._cross_source_bonus(news, others)
        assert bonus == 0.0


# ═══════════════════════════════════════════════════════════
# 증거 점수 테스트
# ═══════════════════════════════════════════════════════════

class TestEvidenceScore:
    """증거 기반 품질 점수 테스트."""

    def setup_method(self):
        self.scorer = CredibilityScorer()

    def test_rich_evidence(self):
        news = _make_news(
            body='관계자는 "올해 경제 성장률은 2.5%"라고 밝혔다. 보고서에 따르면 1000억 규모의 투자가 진행된다. https://example.com/report 참고.'
        )
        score = self.scorer._evidence_score(news)
        assert score > 0.3

    def test_no_evidence(self):
        news = _make_news(body="그냥 일반적인 내용입니다")
        score = self.scorer._evidence_score(news)
        assert score < 0.5

    def test_no_body(self):
        news = _make_news(body="")
        score = self.scorer._evidence_score(news)
        assert score == 0.3

    def test_long_body_bonus(self):
        short_news = _make_news(body="짧은 본문")
        long_news = _make_news(body="긴 본문 " * 500)
        short_score = self.scorer._evidence_score(short_news)
        long_score = self.scorer._evidence_score(long_news)
        assert long_score >= short_score


# ═══════════════════════════════════════════════════════════
# 선정성 감점 테스트
# ═══════════════════════════════════════════════════════════

class TestSensationalismPenalty:
    """선정성 감점 테스트."""

    def setup_method(self):
        self.scorer = CredibilityScorer()

    def test_normal_title(self):
        news = _make_news(title="한국 경제 성장률 전망")
        penalty = self.scorer._sensationalism_penalty(news)
        assert penalty == 0.0

    def test_sensational_title(self):
        news = _make_news(title="충격 경악 대박 역대급 뉴스")
        penalty = self.scorer._sensationalism_penalty(news)
        assert penalty > 0.3

    def test_special_characters(self):
        news = _make_news(title="이거 실화냐?? 대박!!")
        penalty = self.scorer._sensationalism_penalty(news)
        assert penalty > 0

    def test_penalty_capped(self):
        news = _make_news(title="충격 경악 발칵 폭탄 대박 역대급!! ㅋㅋ")
        penalty = self.scorer._sensationalism_penalty(news)
        assert penalty <= 1.0


# ═══════════════════════════════════════════════════════════
# score() 종합 테스트
# ═══════════════════════════════════════════════════════════

class TestCredibilityScore:
    """종합 점수 테스트."""

    def setup_method(self):
        self.scorer = CredibilityScorer()

    def test_score_structure(self):
        news = _make_news()
        result = self.scorer.score(news)
        assert "credibility_score" in result
        assert "quality_score" in result
        assert "evidence_score" in result
        assert "sensationalism_penalty" in result

    def test_score_ranges(self):
        news = _make_news()
        result = self.scorer.score(news)
        assert 0 <= result["credibility_score"] <= 1
        assert 0 <= result["quality_score"] <= 1
        assert 0 <= result["evidence_score"] <= 1
        assert 0 <= result["sensationalism_penalty"] <= 1

    def test_high_tier_higher_credibility(self):
        tier1 = _make_news(source_tier="tier1")
        tier3 = _make_news(source_tier="tier3")
        score1 = self.scorer.score(tier1)
        score3 = self.scorer.score(tier3)
        assert score1["credibility_score"] > score3["credibility_score"]

    def test_sensational_lower_quality(self):
        normal = _make_news(title="정상 경제 뉴스 제목")
        sensational = _make_news(title="충격 대박 경악 폭탄 뉴스")
        score_normal = self.scorer.score(normal)
        score_sensational = self.scorer.score(sensational)
        assert score_normal["quality_score"] >= score_sensational["quality_score"]
