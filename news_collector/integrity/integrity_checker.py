"""Module 6: Content Integrity QA - 콘텐츠 무결성 검증"""

import hashlib
import re
from typing import Dict, List, Tuple

from news_collector.models.news import NormalizedNews
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# 스팸/광고 키워드
AD_KEYWORDS = [
    "클릭", "지금구매", "할인", "특가", "무료배송", "광고", "sponsored",
    "click here", "buy now", "limited offer", "free shipping", "promoted",
]
ILLEGAL_KEYWORDS = [
    "도박", "카지노", "성인", "음란", "gambling", "casino",
]
SENSATIONAL_PATTERNS = [
    r".*\[충격\].*", r".*\[경악\].*", r".*놀라운\s(발표|비밀|진실).*",
    r".*\d+번\s(이것|저것).*", r".*이\s사실일\s리\s없다.*",
]
FUNCTION_WORDS = {"의", "이", "가", "을", "를", "에", "에서", "로", "과", "그리고", "또는", "있다", "하다", "되다"}


class ContentIntegrityChecker:
    """
    Module 6: 뉴스 콘텐츠 무결성 검증 (규칙 기반).

    - 제목-본문 일치도
    - 다중 토픽 오염 탐지
    - 보일러플레이트/스팸 탐지
    """

    def assess(self, news: NormalizedNews) -> Tuple[float, Dict]:
        """
        종합 무결성 평가.

        Returns:
            (integrity_score 0~1, details dict)
        """
        consistency = self._check_title_body_consistency(news)
        contamination, cont_flags = self._check_contamination(news)
        spam, spam_flags = self._check_spam(news)

        integrity_score = (
            consistency * 0.4
            + (1 - contamination) * 0.3
            + (1 - spam) * 0.3
        )
        integrity_score = max(0.0, min(1.0, integrity_score))

        details = {
            "title_body_consistency": round(consistency, 3),
            "contamination_score": round(contamination, 3),
            "contamination_flags": cont_flags,
            "spam_score": round(spam, 3),
            "spam_flags": spam_flags,
        }

        logger.debug("무결성 평가: %s → %.3f", news.title[:30], integrity_score)
        return integrity_score, details

    def _check_title_body_consistency(self, news: NormalizedNews) -> float:
        """제목-본문 일치도 (0~1)."""
        if not news.body or not news.title:
            return 0.5

        title_entities = self._extract_entities(news.title)
        if not title_entities:
            return 1.0

        body_lower = news.body.lower()
        coverage = sum(1 for e in title_entities if e.lower() in body_lower)
        coverage_ratio = coverage / len(title_entities)

        # 키워드 분산도
        title_words = {w for w in news.title.lower().split() if len(w) > 2}
        paragraphs = [p for p in news.body.split("\n") if p.strip()][:5]
        if not paragraphs or not title_words:
            return coverage_ratio

        word_dist = []
        for para in paragraphs:
            para_lower = para.lower()
            count = sum(1 for w in title_words if w in para_lower)
            word_dist.append(count)

        total = sum(word_dist)
        if total == 0:
            return coverage_ratio * 0.5

        max_conc = max(word_dist) / max(1, total)
        return min(1.0, coverage_ratio * (1 - max_conc * 0.2))

    def _check_contamination(self, news: NormalizedNews) -> Tuple[float, List[str]]:
        """다중 토픽 오염 탐지 (0~1, flags)."""
        flags = []
        if not news.body:
            return 0.0, flags

        paragraphs = [p.strip() for p in news.body.split("\n") if p.strip()]
        if len(paragraphs) < 2:
            return 0.0, flags

        para_keywords = [set(self._extract_keywords(p)) for p in paragraphs[:10]]
        similarities = []
        for i in range(len(para_keywords) - 1):
            union = len(para_keywords[i] | para_keywords[i + 1])
            if union == 0:
                continue
            sim = len(para_keywords[i] & para_keywords[i + 1]) / union
            similarities.append(sim)

        if not similarities:
            return 0.0, flags

        avg_sim = sum(similarities) / len(similarities)
        low_count = sum(1 for s in similarities if s < 0.2)
        score = 0.0

        if avg_sim < 0.3:
            score = 0.7
            flags.append("unrelated_topics")
        elif low_count > len(similarities) * 0.5:
            score = 0.5
            flags.append("inconsistent_topics")

        return min(1.0, score), flags

    def _check_spam(self, news: NormalizedNews) -> Tuple[float, List[str]]:
        """스팸/광고/보일러플레이트 탐지 (0~1, flags)."""
        flags = []
        score = 0.0
        text = (news.body or "") + " " + (news.title or "")
        text_lower = text.lower()

        # 반복 문장
        if self._has_repetitive(news.body or ""):
            score += 0.3
            flags.append("repetitive_content")

        # 광고 키워드
        if any(kw in text_lower for kw in AD_KEYWORDS):
            score += 0.3
            flags.append("ad_content")

        # 불법 키워드
        if any(kw in text_lower for kw in ILLEGAL_KEYWORDS):
            score += 0.5
            flags.append("illegal_content")

        # Lexical density
        words = text_lower.split()
        if words:
            meaningful = [w for w in words if w not in FUNCTION_WORDS and len(w) > 1]
            density = len(meaningful) / len(words)
            if density < 0.4:
                score += 0.2
                flags.append("low_content_quality")

        # 선정적 제목
        for pattern in SENSATIONAL_PATTERNS:
            if re.search(pattern, news.title or ""):
                score += 0.1
                flags.append("sensational_title")
                break

        return min(1.0, score), flags

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        """제목에서 엔티티 추출 (간단한 패턴)."""
        entities = re.findall(r'[가-힣]{2,}', text)
        entities += re.findall(r'\b[A-Z][a-zA-Z]+\b', text)
        return list(set(entities))

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """키워드 추출."""
        stopwords = {"의", "이", "그", "저", "것", "수", "등", "같은", "있다", "하다", "and", "the", "is"}
        words = text.lower().split()
        return [w for w in words if len(w) > 2 and w not in stopwords]

    @staticmethod
    def _has_repetitive(text: str) -> bool:
        """반복 문장 탐지."""
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) < 3:
            return False
        hashes = [hashlib.md5(s.encode()).hexdigest() for s in sentences]
        unique = len(set(hashes))
        return (1 - unique / len(hashes)) > 0.3
