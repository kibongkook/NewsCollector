"""Module 7: Credibility & Quality Scoring - 신뢰도/품질 점수"""

import re
from typing import Dict, List, Optional, Tuple

from news_collector.models.news import NormalizedNews
from news_collector.registry.source_registry import SourceRegistry
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# 증거 패턴
EVIDENCE_PATTERNS = [
    r'\d+%', r'\d+억', r'\d+만', r'\d+조',  # 통계
    r'"[^"]{5,}"', r"'[^']{5,}'",  # 직접 인용
    r'관계자는?\s', r'대변인',  # 공식 발표
    r'보고서', r'연구\s결과', r'발표\s자료',  # 참조
    r'https?://\S+',  # 참고 링크
]

# 선정적 표현
SENSATIONAL_WORDS = [
    "충격", "경악", "발칵", "폭탄", "대박", "역대급", "초대형",
    "긴급", "속보", "단독", "breaking", "shock",
]


class CredibilityScorer:
    """
    Module 7: 신뢰도 및 품질 점수 산출.

    - 소스 신뢰도 (Tier 기반)
    - 크로스 소스 검증
    - 증거 점수
    - 선정성 감점
    """

    def __init__(self, registry: Optional[SourceRegistry] = None) -> None:
        self._registry = registry

    def score(
        self, news: NormalizedNews, all_news: Optional[List[NormalizedNews]] = None
    ) -> Dict[str, float]:
        """
        신뢰도 + 품질 점수 산출.

        Returns:
            {"credibility_score", "quality_score", "evidence_score", "sensationalism_penalty"}
        """
        source_trust = self._source_trust_score(news)
        cross_bonus = self._cross_source_bonus(news, all_news or [])
        evidence = self._evidence_score(news)
        sensationalism = self._sensationalism_penalty(news)

        credibility = min(1.0, source_trust + cross_bonus)
        quality = max(0.0, min(1.0, evidence - sensationalism))

        return {
            "credibility_score": round(credibility, 3),
            "quality_score": round(quality, 3),
            "evidence_score": round(evidence, 3),
            "sensationalism_penalty": round(sensationalism, 3),
        }

    def _source_trust_score(self, news: NormalizedNews) -> float:
        """소스 Tier 기반 신뢰도 (0~1)."""
        tier_scores = {
            "whitelist": 0.95, "tier1": 0.85, "tier2": 0.65,
            "tier3": 0.40, "blacklist": 0.0,
        }
        base = tier_scores.get(news.source_tier, 0.5)

        # Registry에서 세부 점수 반영
        if self._registry:
            source = self._registry.get(news.source_id)
            if source:
                base = source.credibility_base_score / 100.0

        return base

    def _cross_source_bonus(
        self, news: NormalizedNews, all_news: List[NormalizedNews]
    ) -> float:
        """여러 소스에서 같은 뉴스 보도 시 보너스."""
        if not all_news:
            return 0.0

        title_words = set(news.title.lower().split())
        if len(title_words) < 3:
            return 0.0

        cross_count = 0
        for other in all_news:
            if other.source_id == news.source_id or other.id == news.id:
                continue
            other_words = set(other.title.lower().split())
            if not other_words:
                continue
            sim = len(title_words & other_words) / len(title_words | other_words)
            if sim >= 0.5:
                cross_count += 1

        if cross_count >= 3:
            return 0.15
        elif cross_count >= 1:
            return 0.05
        return 0.0

    def _evidence_score(self, news: NormalizedNews) -> float:
        """증거 기반 품질 점수 (0~1)."""
        if not news.body:
            return 0.3

        text = news.body
        match_count = 0
        for pattern in EVIDENCE_PATTERNS:
            if re.search(pattern, text):
                match_count += 1

        # 본문 길이 보너스
        length_bonus = min(0.2, len(text) / 5000)
        score = min(1.0, (match_count / len(EVIDENCE_PATTERNS)) + length_bonus)
        return score

    def _sensationalism_penalty(self, news: NormalizedNews) -> float:
        """선정성 감점 (0~1)."""
        penalty = 0.0
        title = (news.title or "").lower()

        word_count = sum(1 for w in SENSATIONAL_WORDS if w in title)
        penalty += min(0.5, word_count * 0.15)

        # 과도한 특수문자
        special_count = len(re.findall(r'[!?]{2,}|[ㅋㅎ]{2,}', news.title or ""))
        penalty += min(0.2, special_count * 0.1)

        return min(1.0, penalty)
