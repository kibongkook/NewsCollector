"""뉴스 포맷 선택기

뉴스의 특성(길이, 복잡도, 시각 자료 가능성 등)을 분석하여
가장 적합한 뉴스 포맷을 추천합니다.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Set

from news_collector.models.generated_news import (
    NewsFormat,
    FormatSpec,
    FORMAT_SPECS,
    FormatScore,
    FormatRecommendation,
)
from news_collector.models.analyzed_news import (
    EnrichedNews,
    AnalyzedNews,
    TextComplexity,
)
from news_collector.models.news import NewsWithScores
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 포맷 선택 규칙
# ============================================================

# 토픽별 선호 포맷
TOPIC_FORMAT_PREFERENCES: Dict[str, List[NewsFormat]] = {
    "정치": [NewsFormat.STRAIGHT, NewsFormat.ANALYSIS, NewsFormat.TIMELINE],
    "경제": [NewsFormat.ANALYSIS, NewsFormat.INFOGRAPHIC, NewsFormat.COMPARISON],
    "IT/과학": [NewsFormat.EXPLAINER, NewsFormat.FEATURE, NewsFormat.LISTICLE],
    "문화/연예": [NewsFormat.PHOTO_NEWS, NewsFormat.CARD_NEWS, NewsFormat.SOCIAL_POST],
    "스포츠": [NewsFormat.STRAIGHT, NewsFormat.PHOTO_NEWS, NewsFormat.BRIEF],
    "사회": [NewsFormat.STRAIGHT, NewsFormat.TIMELINE, NewsFormat.FEATURE],
    "국제": [NewsFormat.ANALYSIS, NewsFormat.EXPLAINER, NewsFormat.COMPARISON],
    "건강/의료": [NewsFormat.EXPLAINER, NewsFormat.QNA, NewsFormat.LISTICLE],
}

# 긴급도별 선호 포맷
URGENCY_FORMAT_PREFERENCES: Dict[str, List[NewsFormat]] = {
    "breaking": [NewsFormat.BRIEF, NewsFormat.STRAIGHT, NewsFormat.SOCIAL_POST],
    "daily": [NewsFormat.STRAIGHT, NewsFormat.ANALYSIS, NewsFormat.CARD_NEWS],
    "evergreen": [NewsFormat.FEATURE, NewsFormat.EXPLAINER, NewsFormat.LISTICLE],
}

# 통계/수치가 많은 경우 선호 포맷
STATISTICAL_FORMATS = [NewsFormat.INFOGRAPHIC, NewsFormat.COMPARISON, NewsFormat.LISTICLE]

# 인물/인터뷰 중심 포맷
INTERVIEW_FORMATS = [NewsFormat.FEATURE, NewsFormat.QNA, NewsFormat.STRAIGHT]


class FormatSelector:
    """
    뉴스 포맷 선택기.

    분석된 뉴스의 특성을 평가하여 가장 적합한 포맷을 추천합니다.

    사용법:
        selector = FormatSelector()

        # EnrichedNews로 추천
        recommendation = selector.recommend(enriched_news)

        # NewsWithScores + AnalyzedNews로 추천
        recommendation = selector.recommend_from_analysis(news, analysis)

        print(recommendation.recommendations[0].format)  # 최적 포맷
        print(recommendation.recommendations[0].score)   # 점수
    """

    def __init__(self):
        self.format_specs = FORMAT_SPECS
        self.topic_preferences = TOPIC_FORMAT_PREFERENCES
        self.urgency_preferences = URGENCY_FORMAT_PREFERENCES

    def recommend(self, enriched_news: EnrichedNews) -> FormatRecommendation:
        """
        EnrichedNews에서 포맷 추천.

        Args:
            enriched_news: 분석이 완료된 뉴스

        Returns:
            FormatRecommendation 추천 결과
        """
        return self.recommend_from_analysis(
            enriched_news.news,
            enriched_news.analysis,
        )

    def recommend_from_analysis(
        self,
        news: NewsWithScores,
        analysis: Optional[AnalyzedNews] = None,
    ) -> FormatRecommendation:
        """
        뉴스와 분석 결과에서 포맷 추천.

        Args:
            news: 뉴스 객체
            analysis: 분석 결과 (None이면 기본값 사용)

        Returns:
            FormatRecommendation 추천 결과
        """
        scores: Dict[NewsFormat, float] = {fmt: 0.0 for fmt in NewsFormat}

        # 콘텐츠 길이 분석
        content_length = self._analyze_content_length(news)

        # 복잡도 분석
        complexity_level = self._analyze_complexity(news, analysis)

        # 시각 자료 가능성
        visual_richness = self._analyze_visual_potential(news, analysis)

        # 시의성 분석
        time_sensitivity = self._analyze_time_sensitivity(news)

        # 타겟 독자층 추정
        target_audience = self._estimate_target_audience(news, analysis)

        # === 점수 계산 ===

        # 1. 콘텐츠 길이 기반
        scores = self._apply_length_scores(scores, content_length)

        # 2. 복잡도 기반
        scores = self._apply_complexity_scores(scores, complexity_level)

        # 3. 시각 자료 가능성 기반
        scores = self._apply_visual_scores(scores, visual_richness)

        # 4. 시의성 기반
        scores = self._apply_urgency_scores(scores, time_sensitivity)

        # 5. 토픽 기반
        if analysis and analysis.topics:
            main_topic = analysis.topics[0].topic
            scores = self._apply_topic_scores(scores, main_topic)

        # 6. 통계/수치 포함 여부
        if self._has_statistics(news):
            for fmt in STATISTICAL_FORMATS:
                scores[fmt] += 0.2

        # 7. 엔티티 수 기반 (인물이 많으면 인터뷰/피처)
        if analysis and len(analysis.entities) >= 3:
            for fmt in INTERVIEW_FORMATS:
                scores[fmt] += 0.1

        # 상위 3개 포맷 선택
        sorted_formats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        recommendations = []

        for fmt, score in sorted_formats[:5]:
            if score > 0:
                reason = self._generate_reason(fmt, content_length, complexity_level, time_sensitivity)
                recommendations.append(FormatScore(
                    format=fmt,
                    score=round(min(score, 1.0), 3),
                    reason=reason,
                ))

        # 필수/권장 요소 결정
        required_elements, optional_elements = self._determine_elements(
            recommendations[0].format if recommendations else NewsFormat.STRAIGHT
        )

        return FormatRecommendation(
            news_id=news.id,
            recommendations=recommendations,
            content_length=content_length,
            visual_richness=visual_richness,
            complexity_level=complexity_level,
            time_sensitivity=time_sensitivity,
            target_audience=target_audience,
            required_elements=required_elements,
            optional_elements=optional_elements,
        )

    def _analyze_content_length(self, news: NewsWithScores) -> str:
        """콘텐츠 길이 분석"""
        text_length = len(news.title) + len(news.body)

        if text_length < 200:
            return "short"
        elif text_length < 800:
            return "medium"
        else:
            return "long"

    def _analyze_complexity(
        self,
        news: NewsWithScores,
        analysis: Optional[AnalyzedNews],
    ) -> str:
        """복잡도 분석"""
        if analysis:
            if analysis.text_complexity == TextComplexity.COMPLEX:
                return "complex"
            elif analysis.text_complexity == TextComplexity.SIMPLE:
                return "simple"

        # 분석 없을 시 문장 길이로 추정
        text = news.body
        sentences = re.split(r'[.!?]\s*', text)
        avg_length = sum(len(s) for s in sentences) / max(len(sentences), 1)

        if avg_length > 50:
            return "complex"
        elif avg_length < 25:
            return "simple"
        return "moderate"

    def _analyze_visual_potential(
        self,
        news: NewsWithScores,
        analysis: Optional[AnalyzedNews],
    ) -> float:
        """시각 자료 활용 가능성"""
        score = 0.5

        # 숫자/통계 포함
        if self._has_statistics(news):
            score += 0.2

        # 장소/인물 엔티티 많음
        if analysis:
            loc_entities = sum(1 for e in analysis.entities if e.type.value == "LOC")
            person_entities = sum(1 for e in analysis.entities if e.type.value == "PERSON")

            if loc_entities >= 2:
                score += 0.1  # 지도/사진 가능
            if person_entities >= 2:
                score += 0.1  # 인물 사진 가능

        return min(score, 1.0)

    def _analyze_time_sensitivity(self, news: NewsWithScores) -> str:
        """시의성 분석"""
        title_lower = news.title.lower()
        body_lower = news.body.lower() if news.body else ""

        breaking_keywords = {"속보", "긴급", "단독", "breaking", "just in", "flash"}
        evergreen_keywords = {"방법", "가이드", "설명", "이해", "how to", "guide", "explained"}

        if any(kw in title_lower for kw in breaking_keywords):
            return "breaking"
        if any(kw in title_lower or kw in body_lower for kw in evergreen_keywords):
            return "evergreen"

        return "daily"

    def _estimate_target_audience(
        self,
        news: NewsWithScores,
        analysis: Optional[AnalyzedNews],
    ) -> str:
        """타겟 독자층 추정"""
        if analysis and analysis.text_complexity == TextComplexity.COMPLEX:
            return "expert"

        # 청소년 대상 키워드
        youth_keywords = {"학생", "청소년", "게임", "아이돌", "틱톡", "유튜브"}
        text = news.title + " " + (news.body or "")

        if any(kw in text for kw in youth_keywords):
            return "youth"

        return "general"

    def _has_statistics(self, news: NewsWithScores) -> bool:
        """통계/수치 포함 여부"""
        text = news.title + " " + (news.body or "")
        # 숫자 + 단위 패턴
        patterns = [
            r'\d+%',           # 퍼센트
            r'\d+억',          # 금액
            r'\d+만',          # 수량
            r'\d+조',          # 대규모 금액
            r'\d+배',          # 배수
            r'\d+위',          # 순위
        ]
        return any(re.search(p, text) for p in patterns)

    def _apply_length_scores(
        self,
        scores: Dict[NewsFormat, float],
        content_length: str,
    ) -> Dict[NewsFormat, float]:
        """길이 기반 점수"""
        if content_length == "short":
            scores[NewsFormat.BRIEF] += 0.4
            scores[NewsFormat.SOCIAL_POST] += 0.3
            scores[NewsFormat.CARD_NEWS] += 0.2
        elif content_length == "long":
            scores[NewsFormat.FEATURE] += 0.3
            scores[NewsFormat.ANALYSIS] += 0.3
            scores[NewsFormat.EXPLAINER] += 0.2
        else:
            scores[NewsFormat.STRAIGHT] += 0.3
            scores[NewsFormat.LISTICLE] += 0.2

        return scores

    def _apply_complexity_scores(
        self,
        scores: Dict[NewsFormat, float],
        complexity_level: str,
    ) -> Dict[NewsFormat, float]:
        """복잡도 기반 점수"""
        if complexity_level == "complex":
            scores[NewsFormat.ANALYSIS] += 0.3
            scores[NewsFormat.EXPLAINER] += 0.3
            scores[NewsFormat.FEATURE] += 0.2
        elif complexity_level == "simple":
            scores[NewsFormat.BRIEF] += 0.2
            scores[NewsFormat.STRAIGHT] += 0.2
            scores[NewsFormat.CARD_NEWS] += 0.2
        else:
            scores[NewsFormat.STRAIGHT] += 0.2

        return scores

    def _apply_visual_scores(
        self,
        scores: Dict[NewsFormat, float],
        visual_richness: float,
    ) -> Dict[NewsFormat, float]:
        """시각 자료 가능성 기반 점수"""
        if visual_richness > 0.7:
            scores[NewsFormat.PHOTO_NEWS] += 0.3
            scores[NewsFormat.CARD_NEWS] += 0.3
            scores[NewsFormat.INFOGRAPHIC] += 0.2
        elif visual_richness > 0.5:
            scores[NewsFormat.CARD_NEWS] += 0.1

        return scores

    def _apply_urgency_scores(
        self,
        scores: Dict[NewsFormat, float],
        time_sensitivity: str,
    ) -> Dict[NewsFormat, float]:
        """시의성 기반 점수"""
        preferred = self.urgency_preferences.get(time_sensitivity, [])
        for i, fmt in enumerate(preferred):
            scores[fmt] += 0.3 - (i * 0.1)

        return scores

    def _apply_topic_scores(
        self,
        scores: Dict[NewsFormat, float],
        topic: str,
    ) -> Dict[NewsFormat, float]:
        """토픽 기반 점수"""
        preferred = self.topic_preferences.get(topic, [])
        for i, fmt in enumerate(preferred):
            scores[fmt] += 0.2 - (i * 0.05)

        return scores

    def _generate_reason(
        self,
        fmt: NewsFormat,
        content_length: str,
        complexity_level: str,
        time_sensitivity: str,
    ) -> str:
        """추천 이유 생성"""
        reasons = []

        spec = self.format_specs.get(fmt)
        if spec:
            reasons.append(f"{spec.use_case}에 적합")

        if time_sensitivity == "breaking" and fmt in [NewsFormat.BRIEF, NewsFormat.STRAIGHT]:
            reasons.append("속보성 뉴스")
        if complexity_level == "complex" and fmt in [NewsFormat.ANALYSIS, NewsFormat.EXPLAINER]:
            reasons.append("복잡한 이슈 설명")
        if content_length == "long" and fmt == NewsFormat.FEATURE:
            reasons.append("충분한 콘텐츠 깊이")

        return ", ".join(reasons) if reasons else "기본 추천"

    def _determine_elements(self, fmt: NewsFormat) -> tuple:
        """필수/권장 요소 결정"""
        spec = self.format_specs.get(fmt)

        if spec:
            required = spec.structure.copy()
            optional = ["image", "quote", "background"]
        else:
            required = ["title", "body"]
            optional = []

        return required, optional


# 편의 함수
def select_format(
    news: NewsWithScores,
    analysis: Optional[AnalyzedNews] = None,
) -> FormatRecommendation:
    """
    뉴스 포맷 선택 (편의 함수).

    Args:
        news: 뉴스 객체
        analysis: 분석 결과

    Returns:
        FormatRecommendation 추천 결과
    """
    selector = FormatSelector()
    return selector.recommend_from_analysis(news, analysis)
