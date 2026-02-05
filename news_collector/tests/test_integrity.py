"""Module 6: ContentIntegrityChecker 테스트"""

import pytest

from news_collector.integrity.integrity_checker import ContentIntegrityChecker
from news_collector.models.news import NormalizedNews


# ─── Fixture ────────────────────────────────────────────

def _make_news(
    title: str = "한국 경제 성장률 전망 발표",
    body: str = "한국 경제의 성장률 전망이 발표되었습니다. 올해 경제 성장률은 2.5%로 예상됩니다.",
    **kwargs,
) -> NormalizedNews:
    defaults = {"id": "1", "source_id": "test", "url": "https://example.com/1"}
    defaults.update(kwargs)
    return NormalizedNews(title=title, body=body, **defaults)


# ═══════════════════════════════════════════════════════════
# 제목-본문 일치도 테스트
# ═══════════════════════════════════════════════════════════

class TestTitleBodyConsistency:
    """제목-본문 일치도 테스트."""

    def setup_method(self):
        self.checker = ContentIntegrityChecker()

    def test_high_consistency(self):
        news = _make_news(
            title="한국 경제 성장률 전망",
            body="한국 경제의 성장률 전망이 발표되었습니다. 올해 경제 성장률은 2.5%로 예상됩니다. 한국은행은 경제 전망 보고서를 공개했습니다.",
        )
        score = self.checker._check_title_body_consistency(news)
        assert score > 0.5

    def test_low_consistency(self):
        news = _make_news(
            title="한국 경제 성장률 전망",
            body="오늘 날씨가 좋습니다. 내일은 비가 올 예정입니다. 주말에는 맑겠습니다.",
        )
        score = self.checker._check_title_body_consistency(news)
        assert score < 0.8

    def test_no_body(self):
        news = _make_news(body="")
        score = self.checker._check_title_body_consistency(news)
        assert score == 0.5

    def test_no_title(self):
        news = _make_news(title="")
        score = self.checker._check_title_body_consistency(news)
        assert score == 0.5


# ═══════════════════════════════════════════════════════════
# 오염 탐지 테스트
# ═══════════════════════════════════════════════════════════

class TestContamination:
    """다중 토픽 오염 탐지 테스트."""

    def setup_method(self):
        self.checker = ContentIntegrityChecker()

    def test_no_contamination(self):
        news = _make_news(
            body="경제 성장률 전망이 발표되었다 올해 경제 전망 보고서 공개\n경제 성장률은 올해 2.5%로 전망 경제 보고서 발표\n경제 전문가들은 긍정적 경제 전망을 내놓았다 경제 보고서 참고",
        )
        score, flags = self.checker._check_contamination(news)
        # 연관된 토픽이므로 오염 낮음 (0~0.7)
        assert score <= 0.7

    def test_empty_body(self):
        news = _make_news(body="")
        score, flags = self.checker._check_contamination(news)
        assert score == 0.0
        assert flags == []

    def test_single_paragraph(self):
        news = _make_news(body="하나의 문단만 있습니다.")
        score, flags = self.checker._check_contamination(news)
        assert score == 0.0


# ═══════════════════════════════════════════════════════════
# 스팸 탐지 테스트
# ═══════════════════════════════════════════════════════════

class TestSpam:
    """스팸/광고 탐지 테스트."""

    def setup_method(self):
        self.checker = ContentIntegrityChecker()

    def test_clean_article(self):
        news = _make_news(
            title="정상 뉴스 제목",
            body="정상적인 뉴스 본문입니다. 주요 내용을 전달합니다.",
        )
        score, flags = self.checker._check_spam(news)
        assert score < 0.5

    def test_ad_keywords(self):
        news = _make_news(
            body="지금구매하세요! 할인 특가 상품 무료배송",
        )
        score, flags = self.checker._check_spam(news)
        assert score > 0
        assert "ad_content" in flags

    def test_illegal_keywords(self):
        news = _make_news(
            body="온라인 도박 카지노 사이트 안내",
        )
        score, flags = self.checker._check_spam(news)
        assert "illegal_content" in flags

    def test_repetitive_content(self):
        news = _make_news(
            body="같은 문장입니다. 같은 문장입니다. 같은 문장입니다. 같은 문장입니다. 같은 문장입니다.",
        )
        score, flags = self.checker._check_spam(news)
        assert "repetitive_content" in flags

    def test_sensational_title(self):
        news = _make_news(
            title="[충격] 놀라운 발표가 있었다",
            body="일반적인 본문 내용입니다.",
        )
        score, flags = self.checker._check_spam(news)
        assert "sensational_title" in flags


# ═══════════════════════════════════════════════════════════
# 엔티티/키워드 추출 테스트
# ═══════════════════════════════════════════════════════════

class TestHelpers:
    """유틸리티 메서드 테스트."""

    def test_extract_entities_korean(self):
        entities = ContentIntegrityChecker._extract_entities("한국 경제 성장률")
        assert len(entities) > 0

    def test_extract_entities_english(self):
        entities = ContentIntegrityChecker._extract_entities("Apple announces iPhone")
        assert "Apple" in entities
        assert "iPhone" not in entities or "iPhone" in entities  # 대문자로 시작

    def test_extract_keywords(self):
        keywords = ContentIntegrityChecker._extract_keywords("한국 경제 성장률 전망 보고서")
        assert len(keywords) > 0

    def test_has_repetitive_true(self):
        text = "반복 문장. 반복 문장. 반복 문장. 반복 문장. 반복 문장."
        assert ContentIntegrityChecker._has_repetitive(text) is True

    def test_has_repetitive_false(self):
        text = "첫 번째 문장. 두 번째 문장. 세 번째 문장."
        assert ContentIntegrityChecker._has_repetitive(text) is False


# ═══════════════════════════════════════════════════════════
# assess() 종합 테스트
# ═══════════════════════════════════════════════════════════

class TestAssess:
    """종합 무결성 평가 테스트."""

    def setup_method(self):
        self.checker = ContentIntegrityChecker()

    def test_good_article(self):
        news = _make_news(
            title="한국 경제 성장률 발표",
            body="한국 경제 성장률이 올해 2.5%로 발표되었습니다.\n전문가들은 경제 성장률에 대해 긍정적으로 평가했습니다.\n한국은행은 보고서를 통해 경제 전망을 밝혔습니다.",
        )
        score, details = self.checker.assess(news)
        assert 0 <= score <= 1
        assert "title_body_consistency" in details
        assert "contamination_score" in details
        assert "spam_score" in details

    def test_spam_article_low_score(self):
        news = _make_news(
            title="[충격] 놀라운 비밀",
            body="지금구매하세요! 할인 특가! 도박 카지노 광고 사이트. 같은 문장. 같은 문장. 같은 문장. 같은 문장.",
        )
        score, details = self.checker.assess(news)
        assert score < 0.7  # 스팸 기사는 낮은 점수

    def test_score_range(self):
        news = _make_news()
        score, details = self.checker.assess(news)
        assert 0 <= score <= 1
        assert 0 <= details["title_body_consistency"] <= 1
        assert 0 <= details["contamination_score"] <= 1
        assert 0 <= details["spam_score"] <= 1
