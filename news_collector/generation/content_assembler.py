"""콘텐츠 조립기

AI 없이 수집된 뉴스를 기반으로 새로운 콘텐츠를 조립합니다.
문장 분류, 중요도 평가, 중복 제거, 포맷별 섹션 구성을 담당합니다.

핵심 기능:
- 원본 URL에서 전체 본문 자동 스크래핑 (RSS 요약 → 전체 본문)
- 유사 뉴스 자동 병합 (본문이 짧을 때)
- 문장 역할 분류 및 중요도 평가
- 포맷별 섹션 구성
"""

import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
import yaml

from news_collector.models.news import NewsWithScores
from news_collector.models.generated_news import NewsFormat
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# 본문 확장 설정 (기본값 - 설정 파일로 오버라이드 가능)
DEFAULT_MIN_BODY_LENGTH_FOR_SCRAPE = 150  # 이 길이 미만이면 스크래핑 시도
DEFAULT_TARGET_BODY_LENGTH_FOR_MERGE = 500  # 이 길이 미만이면 유사 뉴스 병합


# ==============================================================================
# 뉴스 유형 (설정 기반)
# ==============================================================================

class NewsType:
    """뉴스 유형 상수"""
    STANDARD = "standard"  # 일반형 (80%)
    VISUAL = "visual"      # 비주얼형 (15%)
    DATA = "data"          # 데이터형 (5%)


# ============================================================
# 데이터 구조
# ============================================================

@dataclass
class ClassifiedSentence:
    """분류된 문장"""
    text: str
    role: str  # lead, fact, quote, background, outlook, implication, etc.
    importance: float  # 0.0 ~ 1.0
    source_news_id: str
    position: int  # 원문에서의 위치 (0-indexed)
    has_number: bool = False
    has_quote: bool = False
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class AssembledContent:
    """조립된 콘텐츠"""
    sections: Dict[str, str]  # 섹션명 -> 내용
    total_length: int
    sentence_count: int
    source_count: int
    sources: List[str]  # 출처 목록
    images: List[str] = field(default_factory=list)  # 이미지 URL 목록

    def to_dict(self) -> Dict[str, Any]:
        """템플릿 렌더링용 딕셔너리 변환"""
        return {
            **self.sections,
            "total_length": self.total_length,
            "sentence_count": self.sentence_count,
            "source_count": self.source_count,
            "sources": self.sources,
            "images": self.images,
        }

    def get_full_text(self) -> str:
        """전체 텍스트 반환"""
        return "\n\n".join(
            content for content in self.sections.values() if content
        )


# ============================================================
# 설정 로더
# ============================================================

class GenerationConfig:
    """생성 설정 로더"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config",
                "generation_config.yaml"
            )

        self.config: Dict[str, Any] = {}
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                logger.debug("생성 설정 로드 완료: %s", config_path)
        except Exception as e:
            logger.warning("설정 파일 로드 실패: %s - 기본값 사용", e)

    def get_format_spec(self, format_name: str) -> Dict[str, Any]:
        """포맷 스펙 조회"""
        formats = self.config.get("formats", {})
        return formats.get(format_name.lower(), {})

    def get_sentence_patterns(self) -> Dict[str, Any]:
        """문장 패턴 조회"""
        return self.config.get("sentence_patterns", {})

    def get_importance_weights(self) -> Dict[str, float]:
        """중요도 가중치 조회"""
        default_weights = {
            "keyword_match": 0.35,
            "entity_match": 0.25,
            "position_score": 0.20,
            "has_number": 0.10,
            "sentence_length": 0.10,
        }
        return self.config.get("importance_weights", default_weights)

    def get_dedup_threshold(self) -> float:
        """중복 제거 임계값"""
        return self.config.get("deduplication", {}).get("similarity_threshold", 0.7)


class FormatSpecLoader:
    """뉴스 포맷 명세 로더 (news_format_spec.yaml)"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config",
                "news_format_spec.yaml"
            )

        self.config: Dict[str, Any] = {}
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = yaml.safe_load(f) or {}
                logger.debug("뉴스 포맷 명세 로드 완료: %s", config_path)
        except Exception as e:
            logger.warning("포맷 명세 파일 로드 실패: %s - 기본값 사용", e)

    def get_type_detection_rules(self) -> Dict[str, Any]:
        """뉴스 유형 감지 규칙"""
        return self.config.get("type_detection", {})

    def get_news_type_spec(self, news_type: str) -> Dict[str, Any]:
        """뉴스 유형별 스펙 조회"""
        return self.config.get(news_type, {})

    def get_common_settings(self) -> Dict[str, Any]:
        """공통 설정"""
        return self.config.get("common", {})

    def get_sentence_roles(self) -> Dict[str, Any]:
        """문장 역할 정의"""
        return self.config.get("sentence_roles", {})

    def get_dedup_settings(self) -> Dict[str, Any]:
        """중복 제거 설정"""
        return self.config.get("deduplication", {})

    def get_incomplete_endings(self) -> List[str]:
        """불완전 문장 종료 패턴"""
        common = self.get_common_settings()
        return common.get("incomplete_endings", [])


class NewsTypeDetector:
    """뉴스 유형 자동 감지기 (설정 기반)"""

    def __init__(self, format_spec: Optional[FormatSpecLoader] = None):
        self.format_spec = format_spec or FormatSpecLoader()
        self.rules = self.format_spec.get_type_detection_rules()

    def detect(
        self,
        text: str,
        title: str = "",
        image_count: int = 0,
    ) -> str:
        """
        뉴스 유형 감지.

        Args:
            text: 본문 텍스트
            title: 제목
            image_count: 이미지 개수

        Returns:
            뉴스 유형 (standard, visual, data)
        """
        combined_text = f"{title} {text}"

        # 우선순위대로 검사 (설정 파일의 priority 순)
        type_checks = [
            (NewsType.VISUAL, self.rules.get("visual", {})),
            (NewsType.DATA, self.rules.get("data", {})),
        ]

        # priority 순 정렬
        type_checks.sort(key=lambda x: x[1].get("priority", 99))

        for news_type, conditions in type_checks:
            if self._check_conditions(
                news_type, conditions, combined_text, image_count
            ):
                return news_type

        return NewsType.STANDARD

    def _check_conditions(
        self,
        news_type: str,
        conditions: Dict[str, Any],
        text: str,
        image_count: int,
    ) -> bool:
        """조건 체크"""
        conds = conditions.get("conditions", {})

        if news_type == NewsType.VISUAL:
            # 이미지 수 체크
            min_images = conds.get("image_count_min", 2)
            if image_count >= min_images:
                return True

            # 키워드 체크
            keywords = conds.get("keywords", [])
            threshold = conds.get("keyword_match_threshold", 1)
            matched = sum(1 for kw in keywords if kw in text)
            if matched >= threshold:
                return True

        elif news_type == NewsType.DATA:
            # 숫자 밀도 체크
            numeric_chars = sum(1 for c in text if c.isdigit())
            total_chars = len(text) or 1
            density = numeric_chars / total_chars
            min_density = conds.get("numeric_density_min", 0.03)

            if density >= min_density:
                # 추가 패턴 체크
                patterns = conds.get("number_patterns", [])
                threshold = conds.get("pattern_match_threshold", 2)
                matched = sum(1 for p in patterns if re.search(p, text))
                if matched >= threshold:
                    return True

            # 키워드만으로도 데이터형 가능
            keywords = conds.get("keywords", [])
            matched_kw = sum(1 for kw in keywords if kw in text)
            if matched_kw >= 2:
                return True

        return False


# ============================================================
# 문장 분류기
# ============================================================

class SentenceClassifier:
    """문장 역할 분류기"""

    # 한국어 조사/어미 패턴 (단어 경계 판단용)
    KOREAN_WORD_BOUNDARIES = r'(?:[이가은는을를에의로서와도만까지부터]|했다|이다|한다|합니다|였다|입니다|에서|으로|처럼|같이|조차|마저|\s|[,.\?!;:\"\']|$)'

    # 기본 패턴 (설정 파일 없을 때 사용)
    DEFAULT_PATTERNS = {
        "lead": {
            "endings": ["했다", "밝혔다", "전했다", "발표했다", "보도했다", "됐다", "나타났다"],
            "keywords": [],
        },
        "fact": {
            "endings": ["이다", "였다", "됐다", "있다"],
            "keywords": ["확인", "발표", "공개", "조사", "결과"],
        },
        "quote": {
            "patterns": ['"', "'", "라고 말했다", "라고 밝혔다", "라며", "라고 전했다"],
        },
        "background": {
            "keywords": ["때문", "이유로", "배경", "원인", "이전", "과거", "앞서"],
        },
        "outlook": {
            "keywords": ["전망", "예상", "예측", "향후", "앞으로", "계획"],
            "endings": ["될 것", "할 예정", "보인다", "관측"],
        },
        "implication": {
            "keywords": ["영향", "의미", "시사점", "결과", "파급", "중요"],
        },
        "statistic": {
            "patterns": [r"\d+%", r"\d+억", r"\d+만", r"\d+조", r"\d+배"],
        },
    }

    def __init__(self, config: Optional[GenerationConfig] = None):
        self.config = config or GenerationConfig()
        self.patterns = self.config.get_sentence_patterns() or self.DEFAULT_PATTERNS

    def _keyword_match(self, keyword: str, sentence: str) -> bool:
        """
        키워드 매칭 - 단어 경계 확인.

        한국어에서 '예상'이 '예상치'의 일부로 매칭되는 것을 방지합니다.
        키워드 뒤에 조사, 어미, 공백, 구두점이 오는 경우만 매칭합니다.
        """
        if not keyword or not sentence:
            return False
        # 키워드 + 단어 경계 패턴
        pattern = re.escape(keyword) + self.KOREAN_WORD_BOUNDARIES
        return bool(re.search(pattern, sentence))

    def classify(self, sentence: str) -> str:
        """문장 역할 분류"""
        sentence = sentence.strip()
        if not sentence:
            return "other"

        # 인용문 체크 (높은 우선순위)
        quote_patterns = self.patterns.get("quote", {}).get("patterns", ['"', "'"])
        for pattern in quote_patterns:
            if pattern in sentence:
                return "quote"

        # 통계/수치 체크
        stat_patterns = self.patterns.get("statistic", {}).get("patterns", [])
        for pattern in stat_patterns:
            if re.search(pattern, sentence):
                return "statistic"

        # 키워드 기반 역할 체크 (어미보다 우선, 단어 경계 매칭)
        keyword_roles = ["background", "outlook", "implication"]
        for role in keyword_roles:
            specs = self.patterns.get(role, {})
            keywords = specs.get("keywords", [])
            for keyword in keywords:
                if self._keyword_match(keyword, sentence):
                    return role

        # 어미 기반 역할 체크
        for role, specs in self.patterns.items():
            if role in ("quote", "statistic", "background", "outlook", "implication"):
                continue

            endings = specs.get("endings", [])
            for ending in endings:
                if sentence.endswith(ending):
                    return role

        # 기본값
        return "fact"

    def has_number(self, sentence: str) -> bool:
        """숫자/통계 포함 여부"""
        return bool(re.search(r'\d+[%억만조원달러명개건]', sentence))

    def has_quote(self, sentence: str) -> bool:
        """인용문 포함 여부"""
        return '"' in sentence or "'" in sentence or "라고 " in sentence


# ============================================================
# 콘텐츠 조립기
# ============================================================

class ContentAssembler:
    """
    AI 없이 뉴스 콘텐츠를 조립하는 엔진.

    수집된 여러 뉴스에서 문장을 추출하고, 역할별로 분류한 후,
    포맷별 구조에 맞게 조립합니다.

    핵심 기능:
    - 본문이 짧으면 원본 URL에서 자동 스크래핑
    - 유사 뉴스 자동 병합 (더 풍부한 콘텐츠)
    - 문장 역할 분류 및 중요도 평가
    - 뉴스 유형 자동 감지 (일반형/비주얼형/데이터형)
    """

    def __init__(
        self,
        config: Optional[GenerationConfig] = None,
        format_spec: Optional[FormatSpecLoader] = None,
        enable_scraping: bool = True,
        enable_merging: bool = True,
    ):
        """
        Args:
            config: 생성 설정
            format_spec: 뉴스 포맷 명세 로더
            enable_scraping: URL에서 본문 스크래핑 활성화
            enable_merging: 유사 뉴스 병합 활성화
        """
        self.config = config or GenerationConfig()
        self.format_spec = format_spec or FormatSpecLoader()
        self.classifier = SentenceClassifier(self.config)
        self.type_detector = NewsTypeDetector(self.format_spec)
        self.enable_scraping = enable_scraping
        self.enable_merging = enable_merging

        # 설정에서 임계값 로드
        dedup_settings = self.format_spec.get_dedup_settings()
        self.min_body_length_for_scrape = DEFAULT_MIN_BODY_LENGTH_FOR_SCRAPE
        self.target_body_length_for_merge = DEFAULT_TARGET_BODY_LENGTH_FOR_MERGE
        self.substring_min_overlap = dedup_settings.get("substring_min_length", 15)

        # 불완전 문장 종료 패턴 (설정 기반)
        self.incomplete_endings = self.format_spec.get_incomplete_endings() or [
            "지만", "하면", "하고", "하며", "라면", "니까", "므로",
            "면서", "듯이", "처럼", "때문", "인데", "는데", "은데",
            "다가", "고서", "어서", "아서", "다면", "자면", "해서", "..."
        ]

        # 스크래퍼/병합기는 필요할 때 lazy 초기화
        self._scraper = None
        self._merger = None

    def _get_scraper(self):
        """ContentScraper lazy 초기화"""
        if self._scraper is None:
            try:
                from news_collector.ingestion.content_scraper import ContentScraper
                self._scraper = ContentScraper()
            except ImportError:
                self._scraper = False  # 사용 불가 표시
        return self._scraper if self._scraper else None

    def _get_merger(self):
        """NewsMerger lazy 초기화"""
        if self._merger is None:
            try:
                from news_collector.ingestion.content_scraper import NewsMerger
                self._merger = NewsMerger()
            except ImportError:
                self._merger = False
        return self._merger if self._merger else None

    def detect_news_type(
        self,
        source_news: List[NewsWithScores],
    ) -> str:
        """
        뉴스 유형 감지.

        Args:
            source_news: 원본 뉴스 리스트

        Returns:
            뉴스 유형 (standard, visual, data)
        """
        if not source_news:
            return NewsType.STANDARD

        # 대표 뉴스의 제목/본문/이미지로 판단
        primary = source_news[0]
        combined_text = " ".join(n.body or "" for n in source_news[:3])
        combined_title = " ".join(n.title or "" for n in source_news[:3])
        total_images = sum(len(n.image_urls or []) for n in source_news)

        return self.type_detector.detect(
            text=combined_text,
            title=combined_title,
            image_count=total_images,
        )

    def assemble(
        self,
        source_news: List[NewsWithScores],
        format: NewsFormat,
        search_keywords: Optional[List[str]] = None,
        enrich_content: bool = True,
        news_type: Optional[str] = None,
    ) -> AssembledContent:
        """
        콘텐츠 조립.

        Args:
            source_news: 원본 뉴스 리스트
            format: 목표 포맷
            search_keywords: 검색 키워드 (중요도 계산용)
            enrich_content: 본문 확장 활성화 (스크래핑 + 병합)
            news_type: 뉴스 유형 (None이면 자동 감지)

        Returns:
            AssembledContent 객체
        """
        if not source_news:
            return self._empty_content()

        # 본문 확장이 필요한지 확인
        total_body_length = sum(len(n.body or "") for n in source_news)
        avg_body_length = total_body_length / len(source_news) if source_news else 0

        if enrich_content and avg_body_length < self.min_body_length_for_scrape:
            source_news = self._enrich_news_content(source_news)

        # 뉴스 유형 감지 (자동 또는 지정)
        detected_type = news_type or self.detect_news_type(source_news)
        logger.debug("뉴스 유형: %s", detected_type)

        # 1. 모든 문장 추출 및 분류
        all_sentences = self._extract_and_classify(source_news, search_keywords)

        # 2. 중복 제거
        unique_sentences = self._deduplicate(all_sentences)

        # 3. 중요도순 정렬
        sorted_sentences = sorted(
            unique_sentences, key=lambda s: s.importance, reverse=True
        )

        # 4. 포맷별 섹션 구성
        sections = self._build_sections(sorted_sentences, format)

        # 5. 출처 정리
        sources = list(set(
            news.source_name for news in source_news if news.source_name
        ))

        # 6. 이미지 수집 (enriched news에서)
        all_images: List[str] = []
        for news in source_news:
            for img in (news.image_urls or []):
                if img and img not in all_images:
                    all_images.append(img)

        # 이미지 최대 개수 (설정 기반)
        type_spec = self.format_spec.get_news_type_spec(detected_type)
        max_images = 5  # 기본값
        if detected_type == NewsType.VISUAL:
            gallery_spec = type_spec.get("sections", {}).get("gallery", {})
            max_images = gallery_spec.get("count", {}).get("max", 10)
        images = all_images[:max_images]

        total_text = "\n".join(sections.values())

        return AssembledContent(
            sections=sections,
            total_length=len(total_text),
            sentence_count=len(unique_sentences),
            source_count=len(sources),
            sources=sources,
            images=images,
        )

    def _enrich_news_content(
        self,
        news_list: List[NewsWithScores],
    ) -> List[NewsWithScores]:
        """
        뉴스 본문 확장.

        1. 본문이 짧은 뉴스는 원본 URL에서 스크래핑
        2. 여전히 짧으면 유사 뉴스 병합
        """
        from dataclasses import replace

        # 1단계: URL 스크래핑
        if self.enable_scraping:
            scraper = self._get_scraper()
            if scraper:
                enriched = []
                for news in news_list:
                    body_len = len(news.body or "")

                    if body_len < self.min_body_length_for_scrape and news.url:
                        scraped = scraper.scrape(news.url)
                        if scraped.success and len(scraped.full_body) > body_len:
                            # 본문 + 이미지 업데이트
                            new_images = list(news.image_urls or [])
                            for img in scraped.images:
                                if img not in new_images:
                                    new_images.append(img)
                            news = replace(
                                news,
                                body=scraped.full_body,
                                image_urls=new_images[:5],  # 최대 5개
                            )
                            logger.debug(
                                "스크래핑으로 본문 확장: %s (%d -> %d자, 이미지 %d개)",
                                (news.title or "")[:30],
                                body_len,
                                len(scraped.full_body),
                                len(new_images),
                            )
                    enriched.append(news)
                news_list = enriched

        # 2단계: 유사 뉴스 병합
        total_body_length = sum(len(n.body or "") for n in news_list)
        avg_body_length = total_body_length / len(news_list) if news_list else 0

        if self.enable_merging and avg_body_length < self.target_body_length_for_merge:
            merger = self._get_merger()
            if merger and len(news_list) >= 2:
                news_list = merger.merge_similar_news(
                    news_list,
                    target_body_length=self.target_body_length_for_merge,
                )
                logger.debug(
                    "유사 뉴스 병합 완료: %d건",
                    len(news_list),
                )

        return news_list

    def _extract_and_classify(
        self,
        news_list: List[NewsWithScores],
        keywords: Optional[List[str]] = None,
    ) -> List[ClassifiedSentence]:
        """문장 추출 및 분류"""
        all_sentences: List[ClassifiedSentence] = []
        keywords = keywords or []

        for news in news_list:
            body = news.body or ""
            # 문장 분리
            raw_sentences = self._split_sentences(body)

            for idx, sent in enumerate(raw_sentences):
                sent = sent.strip()
                if len(sent) < 10:  # 너무 짧은 문장 제외
                    continue

                # 불완전한 문장 필터링 (접속어미로 끝나는 문장)
                if self._is_incomplete_sentence(sent):
                    continue

                role = self.classifier.classify(sent)
                has_num = self.classifier.has_number(sent)
                has_quote = self.classifier.has_quote(sent)

                # 키워드 매칭
                matched = [k for k in keywords if k.lower() in sent.lower()]

                # 중요도 계산
                importance = self._calculate_importance(
                    sentence=sent,
                    position=idx,
                    total_sentences=len(raw_sentences),
                    has_number=has_num,
                    matched_keywords=matched,
                    role=role,
                )

                all_sentences.append(ClassifiedSentence(
                    text=sent,
                    role=role,
                    importance=importance,
                    source_news_id=news.id,
                    position=idx,
                    has_number=has_num,
                    has_quote=has_quote,
                    matched_keywords=matched,
                ))

        return all_sentences

    def _split_sentences(self, text: str) -> List[str]:
        """문장 분리"""
        # 마침표, 물음표, 느낌표로 분리
        sentences = re.split(r'(?<=[.!?])\s+', text)
        result = []
        for sent in sentences:
            sent = sent.strip()
            if sent:
                # 끝에 구두점이 없으면 추가
                if not sent.endswith(('.', '!', '?')):
                    sent += '.'
                result.append(sent)
        return result

    def _calculate_importance(
        self,
        sentence: str,
        position: int,
        total_sentences: int,
        has_number: bool,
        matched_keywords: List[str],
        role: str,
    ) -> float:
        """문장 중요도 계산"""
        weights = self.config.get_importance_weights()

        # 1. 키워드 매칭 점수
        keyword_score = min(len(matched_keywords) * 0.3, 1.0)

        # 2. 위치 점수 (첫 문장이 가장 중요)
        if position == 0:
            position_score = 1.0
        elif position < 3:
            position_score = 0.8
        elif total_sentences > 0 and position >= total_sentences - 2:
            position_score = 0.6
        else:
            position_score = 0.5

        # 3. 숫자/통계 점수
        number_score = 1.0 if has_number else 0.0

        # 4. 문장 길이 점수 (20-60자가 이상적)
        length = len(sentence)
        if 20 <= length <= 60:
            length_score = 1.0
        elif 15 <= length <= 80:
            length_score = 0.7
        else:
            length_score = 0.4

        # 5. 역할 가중치
        role_weights = {
            "lead": 1.0,
            "fact": 0.9,
            "statistic": 0.85,
            "quote": 0.8,
            "outlook": 0.75,
            "background": 0.7,
            "implication": 0.7,
            "detail": 0.6,
            "other": 0.5,
        }
        role_score = role_weights.get(role, 0.5)

        # 가중 평균
        importance = (
            keyword_score * weights.get("keyword_match", 0.35) +
            position_score * weights.get("position_score", 0.20) +
            number_score * weights.get("has_number", 0.10) +
            length_score * weights.get("sentence_length", 0.10) +
            role_score * 0.25  # 역할 가중치는 별도
        )

        return min(importance, 1.0)

    def _deduplicate(
        self,
        sentences: List[ClassifiedSentence],
    ) -> List[ClassifiedSentence]:
        """중복 문장 제거"""
        threshold = self.config.get_dedup_threshold()
        result: List[ClassifiedSentence] = []
        seen_texts: Set[str] = set()

        for sent in sentences:
            # 정규화된 텍스트
            normalized = self._normalize_for_dedup(sent.text)

            # 완전 중복 체크
            if normalized in seen_texts:
                continue

            # 유사도 체크
            is_duplicate = False
            for seen in seen_texts:
                if self._jaccard_similarity(normalized, seen) >= threshold:
                    is_duplicate = True
                    break
                # 부분 문자열 중복 체크 (15자 이상 공통 부분)
                if self._has_significant_overlap(normalized, seen, min_overlap=15):
                    is_duplicate = True
                    break

            if not is_duplicate:
                result.append(sent)
                seen_texts.add(normalized)

        return result

    def _has_significant_overlap(self, text1: str, text2: str, min_overlap: Optional[int] = None) -> bool:
        """두 텍스트 간 유의미한 중복 부분이 있는지 확인"""
        # 설정 기반 최소 중복 길이
        min_overlap = min_overlap or self.substring_min_overlap

        # 짧은 텍스트 기준으로 체크
        shorter = text1 if len(text1) <= len(text2) else text2
        longer = text2 if len(text1) <= len(text2) else text1

        # 슬라이딩 윈도우로 중복 부분 찾기
        for i in range(len(shorter) - min_overlap + 1):
            substring = shorter[i:i + min_overlap]
            if substring in longer:
                return True
        return False

    def _normalize_for_dedup(self, text: str) -> str:
        """중복 제거용 정규화"""
        # 공백 정규화, 소문자, 특수문자 제거
        text = re.sub(r'\s+', ' ', text.lower())
        text = re.sub(r'[^\w\s가-힣]', '', text)
        return text.strip()

    def _is_incomplete_sentence(self, sentence: str) -> bool:
        """불완전한 문장인지 확인 (접속어미로 끝나는 문장 등)"""
        # 접속어미/종속 접속어로 끝나는 경우 (설정 기반)
        sentence_stripped = sentence.rstrip(".")
        for ending in self.incomplete_endings:
            if sentence_stripped.endswith(ending):
                return True

        # 괄호/따옴표가 열리고 닫히지 않은 경우
        if sentence.count("(") > sentence.count(")"):
            return True
        if sentence.count('"') % 2 != 0:
            return True
        if sentence.count("'") % 2 != 0:
            return True

        return False

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Jaccard 유사도 계산"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0

    def _add_connectors(self, text: str, section: str = "body") -> str:
        """
        문장 사이에 연결어 추가.

        문장 흐름을 자연스럽게 만들기 위해 적절한 연결어를 삽입합니다.
        """
        if not text:
            return text

        # 연결어 목록 (설정 기반, 섹션별)
        common = self.format_spec.get_common_settings()
        config_connectors = common.get("connectors", {})
        connectors = {
            "body": config_connectors.get("body_internal", ["한편", "또한", "이어", "특히", "아울러", "이와 함께"]),
            "closing": config_connectors.get("body_to_closing", ["향후", "앞으로", "이에 따라"]),
        }

        # 문장 분리
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 1:
            return text

        result = [sentences[0]]
        connector_list = connectors.get(section, connectors["body"])
        connector_idx = 0

        for i, sent in enumerate(sentences[1:], 1):
            sent = sent.strip()
            if not sent:
                continue

            # 이미 연결어/접속어로 시작하면 스킵 (대조 접속어 포함)
            skip_prefixes = [
                "한편", "또한", "이어", "특히", "아울러", "이와", "향후", "앞으로", "이에",
                "반면", "그러나", "하지만", "다만", "그런데", "그래서", "따라서", "결국",
                "이처럼", "이렇게", "이같이", "이로써", "한편으로", "반면에", "게다가",
            ]
            starts_with_connector = any(sent.startswith(c) for c in skip_prefixes)

            # 3번째 문장마다 연결어 추가 (너무 자주 추가하면 부자연스러움)
            if not starts_with_connector and i % 2 == 0 and connector_idx < len(connector_list):
                connector = connector_list[connector_idx % len(connector_list)]
                sent = f"{connector} {sent[0].lower() if sent[0].isupper() else sent[0]}{sent[1:]}" if sent else sent
                # 첫 글자가 한글이면 그대로, 영어면 소문자로
                if sent and sent[0].isalpha():
                    pass  # 그대로 유지
                connector_idx += 1

            result.append(sent)

        return " ".join(result)

    def _build_sections(
        self,
        sentences: List[ClassifiedSentence],
        format: NewsFormat,
    ) -> Dict[str, str]:
        """포맷별 섹션 구성"""
        format_name = format.value.lower()
        spec = self.config.get_format_spec(format_name)

        if format == NewsFormat.STRAIGHT:
            return self._build_straight(sentences, spec)
        elif format == NewsFormat.BRIEF:
            return self._build_brief(sentences, spec)
        elif format == NewsFormat.ANALYSIS:
            return self._build_analysis(sentences, spec)
        elif format == NewsFormat.CARD_NEWS:
            return self._build_card_news(sentences, spec)
        elif format == NewsFormat.SOCIAL_POST:
            return self._build_social_post(sentences, spec)
        elif format == NewsFormat.FEATURE:
            return self._build_feature(sentences, spec)
        elif format == NewsFormat.NEWSLETTER:
            return self._build_newsletter(sentences, spec)
        else:
            # 기본: 스트레이트
            return self._build_straight(sentences, spec)

    def _build_straight(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """스트레이트 뉴스 구성 (400-800자)"""
        min_length = spec.get("min_length", 400)
        max_length = spec.get("max_length", 800)
        sections_spec = spec.get("sections", {})

        # 섹션별 설정 조회
        lead_spec = sections_spec.get("lead", {})
        body_spec = sections_spec.get("body", {})
        closing_spec = sections_spec.get("closing", {})

        # 섹션별 문장 수 제한
        lead_min = lead_spec.get("min_sentences", 1)
        lead_max = lead_spec.get("max_sentences", 2)
        body_min = body_spec.get("min_sentences", 3)
        body_max = body_spec.get("max_sentences", 6)
        closing_min = closing_spec.get("min_sentences", 1)
        closing_max = closing_spec.get("max_sentences", 2)

        # 섹션별 우선 역할
        lead_roles = tuple(lead_spec.get("priority_roles", ["lead", "fact"]))
        body_roles = tuple(body_spec.get("priority_roles", ["background", "detail", "quote"]))
        closing_roles = tuple(closing_spec.get("priority_roles", ["outlook", "implication"]))

        used_texts: Set[str] = set()

        # 리드: 우선 역할 문장 선택
        lead_sentences = [s for s in sentences if s.role in lead_roles][:lead_max]
        # 최소 문장 수 확보
        if len(lead_sentences) < lead_min:
            additional = [s for s in sentences if s.text not in {ls.text for ls in lead_sentences}]
            lead_sentences.extend(additional[:lead_min - len(lead_sentences)])
        lead = " ".join(s.text for s in lead_sentences) if lead_sentences else ""
        if not lead and sentences:
            lead = sentences[0].text
            used_texts.add(sentences[0].text)
        used_texts.update(s.text for s in lead_sentences)

        # 본문: 우선 역할 문장 선택
        body_sentences = [
            s for s in sentences
            if s.role in body_roles and s.text not in used_texts
        ][:body_max]
        # 최소 문장 수 확보
        if len(body_sentences) < body_min:
            additional = [
                s for s in sentences
                if s.text not in used_texts and s.text not in {bs.text for bs in body_sentences}
            ]
            body_sentences.extend(additional[:body_min - len(body_sentences)])
        body = " ".join(s.text for s in body_sentences)
        used_texts.update(s.text for s in body_sentences)

        # 마무리: 우선 역할 문장 선택
        closing_sentences = [
            s for s in sentences
            if s.role in closing_roles and s.text not in used_texts
        ][:closing_max]
        # 최소 문장 수 확보
        if len(closing_sentences) < closing_min:
            additional = [
                s for s in sentences
                if s.text not in used_texts and s.text not in {cs.text for cs in closing_sentences}
            ]
            closing_sentences.extend(additional[:closing_min - len(closing_sentences)])
        closing = " ".join(s.text for s in closing_sentences)
        used_texts.update(s.text for s in closing_sentences)

        # 전체 최소 길이 충족 확인 - 부족하면 본문에 문장 추가
        current_text = f"{lead} {body} {closing}".strip()
        if len(current_text) < min_length:
            remaining = [s for s in sentences if s.text not in used_texts]
            for sent in remaining:
                if len(current_text) >= min_length:
                    break
                body += " " + sent.text
                current_text = f"{lead} {body} {closing}".strip()

        # 최대 길이 초과 시 본문 축소 (마지막 문장부터 제거)
        if len(current_text) > max_length:
            body_parts = body.split(". ")
            while len(current_text) > max_length and len(body_parts) > body_min:
                body_parts.pop()
                body = ". ".join(body_parts)
                if body and not body.endswith("."):
                    body += "."
                current_text = f"{lead} {body} {closing}".strip()

        # 연결어 추가 (본문만)
        body_with_connectors = self._add_connectors(body.strip(), "body")

        return {
            "lead": lead.strip(),
            "body": body_with_connectors,
            "closing": closing.strip(),
        }

    def _build_brief(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """속보/간략 뉴스 (50-150자)"""
        max_length = spec.get("max_length", 150)

        # 가장 중요한 문장 1-2개
        headline = ""
        for sent in sentences[:3]:
            if len(headline) + len(sent.text) <= max_length:
                headline += " " + sent.text if headline else sent.text
            else:
                break

        return {"headline": headline.strip()}

    def _build_analysis(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """분석 기사 (1500-3000자)"""
        used_texts: Set[str] = set()

        # 현황 섹션
        current_sentences = [
            s for s in sentences if s.role in ("lead", "fact", "statistic")
        ][:5]
        current_situation = " ".join(s.text for s in current_sentences)
        used_texts.update(s.text for s in current_sentences)

        # 배경 섹션
        background_sentences = [
            s for s in sentences
            if s.role == "background" and s.text not in used_texts
        ][:5]
        # 배경이 부족하면 다른 문장 추가
        if len(background_sentences) < 3:
            additional = [
                s for s in sentences
                if s.text not in used_texts and s not in background_sentences
            ][:5 - len(background_sentences)]
            background_sentences.extend(additional)
        background = " ".join(s.text for s in background_sentences)
        used_texts.update(s.text for s in background_sentences)

        # 전망 섹션
        outlook_sentences = [
            s for s in sentences
            if s.role == "outlook" and s.text not in used_texts
        ][:4]
        if len(outlook_sentences) < 3:
            additional = [
                s for s in sentences
                if s.text not in used_texts and s not in outlook_sentences
            ][:4 - len(outlook_sentences)]
            outlook_sentences.extend(additional)
        outlook = " ".join(s.text for s in outlook_sentences)
        used_texts.update(s.text for s in outlook_sentences)

        # 시사점 섹션
        implication_sentences = [
            s for s in sentences
            if s.role == "implication" and s.text not in used_texts
        ][:3]
        if len(implication_sentences) < 2:
            additional = [
                s for s in sentences
                if s.text not in used_texts and s not in implication_sentences
            ][:3 - len(implication_sentences)]
            implication_sentences.extend(additional)
        implications = " ".join(s.text for s in implication_sentences)

        return {
            "current_situation": current_situation,
            "background": background,
            "outlook": outlook,
            "implications": implications,
        }

    def _build_card_news(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """카드뉴스 (5-10장)"""
        min_cards = spec.get("min_cards", 5)
        max_cards = spec.get("max_cards", 10)
        card_max_length = spec.get("card_length", {}).get("max", 200)

        cards = {}
        used_count = 0

        # 제목 카드
        if sentences:
            cards["card_1"] = sentences[0].text[:card_max_length]
            used_count = 1

        # 콘텐츠 카드
        for i, sent in enumerate(sentences[1:max_cards], start=2):
            if used_count >= max_cards:
                break
            cards[f"card_{i}"] = sent.text[:card_max_length]
            used_count += 1

        # 최소 카드 수 보장
        while used_count < min_cards and sentences:
            # 이미 사용한 문장을 다시 사용 (짧게)
            idx = used_count % len(sentences)
            cards[f"card_{used_count + 1}"] = sentences[idx].text[:100]
            used_count += 1

        return cards

    def _build_social_post(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """SNS 포스트 (100-280자)"""
        max_length = spec.get("max_length", 280)

        hook = ""
        core = ""
        hashtags = ""

        if sentences:
            # 훅: 첫 문장 (50자 이내)
            hook = sentences[0].text[:50]

            # 코어: 2-3번째 문장
            core_texts = [s.text for s in sentences[1:3]]
            core = " ".join(core_texts)[:150]

            # 해시태그: 키워드에서 추출
            all_keywords = []
            for sent in sentences:
                all_keywords.extend(sent.matched_keywords)
            unique_keywords = list(dict.fromkeys(all_keywords))[:5]
            if unique_keywords:
                hashtags = " ".join(f"#{k}" for k in unique_keywords)

        return {
            "hook": hook,
            "core": core,
            "hashtags": hashtags,
        }

    def _build_feature(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """기획 기사 (2000-4000자)"""
        used_texts: Set[str] = set()

        # 도입부 (2-3 문장)
        intro_sentences = sentences[:3]
        intro = " ".join(s.text for s in intro_sentences)
        used_texts.update(s.text for s in intro_sentences)

        # 본문 (많은 문장)
        main_sentences = [
            s for s in sentences if s.text not in used_texts
        ][:15]
        main_body = " ".join(s.text for s in main_sentences)
        used_texts.update(s.text for s in main_sentences)

        # 결론 (전망/시사점)
        conclusion_sentences = [
            s for s in sentences
            if s.role in ("outlook", "implication") and s.text not in used_texts
        ][:4]
        if not conclusion_sentences:
            conclusion_sentences = sentences[-3:]
        conclusion = " ".join(s.text for s in conclusion_sentences)

        return {
            "intro": intro,
            "main_body": main_body,
            "conclusion": conclusion,
        }

    def _build_newsletter(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """뉴스레터 (800-1500자)"""
        used_texts: Set[str] = set()

        # 인사말
        greeting = "오늘의 주요 뉴스를 전해드립니다."

        # 하이라이트 (핵심 뉴스 요약)
        highlight_sentences = sentences[:5]
        highlights = " ".join(s.text for s in highlight_sentences)
        used_texts.update(s.text for s in highlight_sentences)

        # 심층 분석
        deep_sentences = [
            s for s in sentences
            if s.text not in used_texts and s.role in ("background", "outlook")
        ][:4]
        deep_dive = " ".join(s.text for s in deep_sentences)

        # 마무리
        closing = "더 자세한 내용은 원문에서 확인해주세요."

        return {
            "greeting": greeting,
            "highlights": highlights,
            "deep_dive": deep_dive,
            "closing": closing,
        }

    def _empty_content(self) -> AssembledContent:
        """빈 콘텐츠 반환"""
        return AssembledContent(
            sections={},
            total_length=0,
            sentence_count=0,
            source_count=0,
            sources=[],
        )
