"""Module 9: Ranker & Policy Filter - 최종 점수 계산 및 랭킹"""

import re
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
        keywords: Optional[List[str]] = None,
    ) -> List[NewsWithScores]:
        """
        전체 파이프라인: 점수 산출 → 정책 필터 → 다양성 → 정렬 → Top-N.

        Args:
            news_list: 정규화된 뉴스 리스트.
            preset: 랭킹 프리셋 (quality/trending/credible/latest).
            limit: 반환 수.
            keywords: 검색 키워드 리스트 (관련성 점수 산출용).

        Returns:
            점수 포함된 정렬된 뉴스 리스트.
        """
        if not news_list:
            return []

        weights = RANKING_PRESETS.get(preset, DEFAULT_WEIGHTS)
        logger.info("랭킹 시작: %d건, 프리셋=%s", len(news_list), preset)

        # 1. 점수 산출
        scored = self._score_all(news_list, keywords=keywords)

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

    def _score_all(
        self,
        news_list: List[NormalizedNews],
        keywords: Optional[List[str]] = None,
    ) -> List[NewsWithScores]:
        """모든 뉴스에 Module 6/7/8 + 관련성 점수 산출."""
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

            # Relevance: 키워드 관련성 점수
            nws.relevance_score = self._calculate_relevance(news, keywords)

            scored.append(nws)

        return scored

    # 키워드 → 관련 용어 매핑 (검색어 확장, 영한 음역 + 한한 관련어)
    KEYWORD_SYNONYMS = {
        # 영→한 매핑
        "kpop": ["k-pop", "케이팝", "아이돌", "idol"],
        "ai": ["인공지능", "artificial intelligence", "머신러닝", "딥러닝"],
        "election": ["선거", "투표", "vote", "대선", "출마"],
        "nba": ["농구", "basketball"],
        "bts": ["방탄소년단", "방탄"],
        "nato": ["나토", "북대서양조약기구"],
        "un": ["유엔", "국제연합", "united nations"],
        "nasa": ["나사", "항공우주국"],
        "gdp": ["국내총생산", "성장률"],
        "inflation": ["인플레이션", "물가", "물가상승"],
        "trade": ["무역", "통상", "관세"],
        "congress": ["의회", "국회"],
        "president": ["대통령", "대선"],
        "olympics": ["올림픽"],
        "fifa": ["피파", "월드컵"],
        "climate": ["기후", "기후변화", "온난화"],
        "semiconductor": ["반도체", "칩"],
        "startup": ["스타트업", "창업"],
        # 한→영 + 한→한 관련어
        "반도체": ["semiconductor", "칩", "chip", "파운드리"],
        "경제": ["economy", "gdp", "성장률", "물가", "금리"],
        "축구": ["football", "soccer", "fifa", "월드컵"],
        "야구": ["baseball", "mlb", "프로야구", "타자", "투수"],
        "부동산": ["real estate", "아파트", "주택", "집값", "매매"],
        "주식": ["stock", "증시", "코스피", "나스닥", "주가"],
        "영화": ["movie", "film", "cinema", "극장", "감독", "배우", "오스카", "개봉"],
        "예술": ["art", "미술", "작품", "전시", "작가", "갤러리"],
        "외교": ["diplomacy", "diplomatic", "대사", "외무", "정상회담", "회담"],
        "선거": ["election", "투표", "vote", "대선", "출마", "당선", "후보"],
        "정치": ["politics", "정당", "국회", "의원", "여당", "야당"],
        "교육": ["education", "학교", "학생", "대학", "교사", "수업"],
        "범죄": ["crime", "사건", "수사", "검찰", "경찰", "체포"],
        "인공지능": ["ai", "머신러닝", "딥러닝", "chatgpt", "gpt"],
        "스포츠": ["sports", "경기", "선수", "대회", "리그"],
        "문화": ["culture", "예술", "공연", "전시", "축제"],
        "과학": ["science", "연구", "실험", "논문", "발견"],
        "우주": ["space", "nasa", "위성", "로켓", "발사"],
        "기후변화": ["climate change", "온난화", "탄소", "환경"],
        "드라마": ["drama", "시청률", "방영", "출연"],
        "음악": ["music", "가수", "앨범", "콘서트", "노래"],
        "올림픽": ["olympics", "메달", "금메달", "올림픽"],
        "물가": ["inflation", "소비자물가", "가격", "인상"],
        "인구": ["population", "출생률", "고령화", "인구감소"],
    }

    def _calculate_relevance(
        self,
        news: NormalizedNews,
        keywords: Optional[List[str]] = None,
    ) -> float:
        """
        키워드 기반 관련성 점수 (0~1).

        키워드가 없으면 카테고리/콘텐츠 기반 기본 점수 반환.
        키워드가 있으면 제목/본문 매칭도를 측정 (동의어 확장 포함).
        """
        if not keywords:
            base = 0.5
            if news.category:
                base += 0.2
            if news.tags:
                base += 0.1
            if news.body and len(news.body) > 100:
                base += 0.1
            return min(1.0, base)

        title = (news.title or "").lower()
        body = (news.body or "").lower()
        text = title + " " + body

        if not text.strip():
            return 0.0

        # 키워드별 매칭 점수
        total_score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            # 동의어 확장
            search_terms = [kw_lower]
            synonyms = self.KEYWORD_SYNONYMS.get(kw_lower, [])
            search_terms.extend(s.lower() for s in synonyms)

            # 가장 높은 매칭 점수 사용
            best_kw_score = 0.0
            for term in search_terms:
                title_match = 1.0 if term in title else 0.0
                body_match = 1.0 if term in body else 0.0
                body_count = body.count(term)
                freq_bonus = min(0.3, body_count * 0.05)
                kw_score = title_match * 0.6 + body_match * 0.3 + freq_bonus
                best_kw_score = max(best_kw_score, kw_score)

            total_score += best_kw_score

        # 키워드 수로 정규화
        relevance = total_score / len(keywords)

        # 카테고리 매칭 보너스
        if news.category:
            cat_lower = news.category.lower()
            for kw in keywords:
                if kw.lower() in cat_lower or cat_lower in kw.lower():
                    relevance = min(1.0, relevance + 0.1)
                    break

        return min(1.0, relevance)

    def _calculate_final_score(self, news: NewsWithScores, weights: Dict[str, float]) -> float:
        """가중 평균으로 최종 점수 (0~100) 계산."""
        raw = (
            news.popularity_score * weights.get("popularity", 0.25)
            + news.relevance_score * weights.get("relevance", 0.25)
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
