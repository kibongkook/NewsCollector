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
import requests
from io import BytesIO

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
    news_type: str = "standard"  # 뉴스 유형 (standard/visual/data)
    primary_source_id: Optional[str] = None  # Primary source 기사 ID (제목-본문 일치용)

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
            # 이미지 수 체크 (강한 신호)
            min_images = conds.get("image_count_min", 3)
            if image_count >= min_images:
                return True

            # 고확신 키워드 체크 (명백한 비주얼 콘텐츠)
            high_keywords = conds.get("high_confidence_keywords", [])
            high_threshold = conds.get("high_confidence_threshold", 1)
            high_matched = sum(1 for kw in high_keywords if kw in text)
            if high_matched >= high_threshold:
                return True

            # 저확신 키워드 체크 (일반적 단어 - 여러 개 매칭 필요)
            low_keywords = conds.get("low_confidence_keywords", [])
            low_threshold = conds.get("low_confidence_threshold", 3)
            low_matched = sum(1 for kw in low_keywords if kw in text)
            if low_matched >= low_threshold:
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

            # 키워드만으로도 데이터형 가능 (threshold 설정 기반)
            keywords = conds.get("keywords", [])
            kw_threshold = conds.get("keyword_threshold", 3)
            matched_kw = sum(1 for kw in keywords if kw in text)
            if matched_kw >= kw_threshold:
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

    # 안전장치: 극단적 케이스 방지 (무한 루프/메모리)
    MAX_TOTAL_SENTENCES = 30

    # 주요 기업/기관 공식 뉴스룸 (워터마크 없는 원본 이미지 확보용)
    OFFICIAL_NEWSROOMS = {
        # 대기업
        "삼성전자": "https://news.samsung.com/kr",
        "삼성": "https://news.samsung.com/kr",
        "현대자동차": "https://www.hyundai.com/kr/newsroom",
        "현대차": "https://www.hyundai.com/kr/newsroom",
        "기아": "https://www.kia.com/kr/newsroom",
        "LG전자": "https://www.lge.co.kr/kr/newsroom",
        "LG": "https://www.lge.co.kr/kr/newsroom",
        "SK하이닉스": "https://news.skhynix.com",
        "SK": "https://www.sk.com/press",
        "네이버": "https://www.navercorp.com/naver/newsroom",
        "카카오": "https://www.kakaocorp.com/page/newsroom",
        "포스코": "https://newsroom.posco.com",
        # 정부/공공기관
        "청와대": "https://www.president.go.kr/newsroom",
        "국회": "https://www.assembly.go.kr/portal/bbs/B0000011/list.do",
        "정부": "https://www.korea.kr/news/pressReleaseList.do",
        "산업통상자원부": "https://www.motie.go.kr/motie/ne/presse/press2/bbs/bbsList.do",
        "국토교통부": "https://www.molit.go.kr/USR/NEWS/m_71/lst.jsp",
        "문화체육관광부": "https://www.mcst.go.kr/kor/s_notice/press/pressView.jsp",
        "고용노동부": "https://www.moel.go.kr/news/enews/report/enewsView.do",
        # 금융
        "한국은행": "https://www.bok.or.kr/portal/bbs/B0000245/list.do",
        "금융위원회": "https://www.fsc.go.kr/no010101",
    }

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
        combined_text = " ".join(n.body or "" for n in source_news[:3])
        combined_title = " ".join(n.title or "" for n in source_news[:3])
        # 기사당 평균 이미지 수 사용 (합계 사용 시 다중 기사에서 항상 visual 감지됨)
        total_images = sum(len(n.image_urls or []) for n in source_news)
        avg_images = total_images / len(source_news) if source_news else 0

        return self.type_detector.detect(
            text=combined_text,
            title=combined_title,
            image_count=int(avg_images),
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

        # 토픽 필터링: 검색 키워드와 관련 없는 기사 제거 (토픽 혼합 방지)
        source_news = self._filter_relevant_articles(source_news, search_keywords)

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

        # 2.5. Primary source 식별 (제목-본문 일치용)
        primary_source_id = self._get_primary_source(unique_sentences)

        # 2.6. Primary source 문장 부스트 (본문 일관성 강화)
        # 비-primary 소스에서 키워드가 없는 문장은 중요도를 낮춤
        if primary_source_id and search_keywords:
            for sent in unique_sentences:
                if sent.source_news_id == primary_source_id:
                    # Primary source 문장은 부스트
                    sent.importance = min(sent.importance * 1.3, 1.0)
                elif not sent.matched_keywords:
                    # 비-primary, 키워드 없음 → 중요도 대폭 감소
                    sent.importance *= 0.3

        # 3. 중요도순 정렬
        sorted_sentences = sorted(
            unique_sentences, key=lambda s: s.importance, reverse=True
        )

        # 4. 포맷별 섹션 구성 (뉴스 유형 반영)
        sections = self._build_sections(sorted_sentences, format, detected_type)

        # 5. 출처 정리
        sources = list(set(
            news.source_name for news in source_news if news.source_name
        ))

        # 6. 이미지 수집 (enriched news에서) + 필터링 + 워터마크 처리
        all_images: List[str] = []
        seen_normalized_urls: Set[str] = set()  # 정규화된 URL로 중복 체크

        for news in source_news:
            article_text = news.body or news.summary or ""
            article_keywords = search_keywords or []
            news_url = news.url or ""

            for img in (news.image_urls or []):
                if not img:
                    continue

                # Phase 2: ImageInfo 타입 체크 및 메타데이터 활용
                img_url = img
                img_info = None

                if not isinstance(img, str):
                    # ImageInfo 객체가 온 경우 메타데이터 활용
                    from news_collector.ingestion.content_scraper import ImageInfo
                    if isinstance(img, ImageInfo):
                        img_url = img.url
                        img_info = img  # 메타데이터 보존
                        logger.debug(f"ImageInfo 활용: alt={img.alt}, position={img.position}")
                    else:
                        logger.error(f"알 수 없는 이미지 타입: {type(img)}")
                        continue

                # URL 정규화 (쿼리 파라미터 제거)
                normalized_url = self._normalize_image_url(img_url)

                # 정규화된 URL로 중복 체크
                if normalized_url in seen_normalized_urls:
                    continue

                # 기본 유효성 체크
                if not self._is_valid_news_image(img_url):
                    continue

                # 워터마크 처리 (원본 찾기 또는 스크린샷) + 관련성 검사
                clean_img = self._get_clean_image(
                    article_text,
                    article_keywords,
                    img_url,
                    news_url,
                    img_info  # ImageInfo 전달
                )

                if clean_img:
                    # 정제된 이미지도 정규화하여 중복 체크
                    clean_normalized = self._normalize_image_url(clean_img)
                    if clean_normalized not in seen_normalized_urls:
                        all_images.append(clean_img)
                        seen_normalized_urls.add(clean_normalized)

        # Phase 1: 타입별 이미지 개수 제한 (순서 기반 우선순위)
        # - 이미지는 이미 등장 순서대로 정렬되어 있음 (먼저 나온 이미지 = 더 관련성 높음)
        # - 상위 N개만 선택
        if detected_type == NewsType.STANDARD:
            max_images = 5  # Standard: 3-5장 권장, 최대 5장
        elif detected_type == NewsType.VISUAL:
            max_images = 8  # Visual: 5-8장 권장, 최대 8장
        elif detected_type == NewsType.DATA:
            max_images = 3  # Data: 1-3장 권장, 최대 3장
        else:
            max_images = 5  # 기본값

        images = all_images[:max_images]

        total_text = "\n".join(sections.values())

        return AssembledContent(
            sections=sections,
            total_length=len(total_text),
            sentence_count=len(unique_sentences),
            source_count=len(sources),
            sources=sources,
            images=images,
            news_type=detected_type,
            primary_source_id=primary_source_id,
        )

    # 다의어/동음이의어 구분용 패턴 (키워드 → 제외 컨텍스트)
    _AMBIGUOUS_KEYWORD_EXCLUSIONS = {
        'ai': [
            re.compile(r'고병원성\s*AI', re.IGNORECASE),
            re.compile(r'조류\s*인플루엔자', re.IGNORECASE),
            re.compile(r'조류\s*독감', re.IGNORECASE),
            re.compile(r'AI\s*발생.*방역', re.IGNORECASE),
            re.compile(r'AI\s*발생.*살처분', re.IGNORECASE),
        ],
    }

    def _filter_relevant_articles(
        self,
        news_list: List[NewsWithScores],
        search_keywords: Optional[List[str]] = None,
    ) -> List[NewsWithScores]:
        """검색 키워드 기반 관련 기사만 필터링 (토픽 혼합 방지).

        예: 'AI' 검색 시 인공지능 AI 기사만 유지, 조류독감(AI) 기사 제외.
        각 기사의 제목과 본문 앞부분에서 키워드 관련성을 평가하여
        관련 없는 기사를 필터링합니다.
        """
        if not search_keywords or len(news_list) <= 1:
            return news_list

        scored_articles = []
        for news in news_list:
            title = news.title or ""
            title_lower = title.lower()
            body_prefix = (news.body or "")[:300]
            combined = title + " " + body_prefix

            # 1. 영어 기사 필터 (한국어 뉴스 생성이므로 영문 기사 제외)
            korean_chars = sum(1 for c in title if '\uac00' <= c <= '\ud7a3')
            if len(title) > 10 and korean_chars < len(title) * 0.2:
                logger.debug("영어 기사 필터링: %s", title[:50])
                scored_articles.append((news, -1))  # -1 = 제외
                continue

            # 2. 다의어 구분 (예: AI = 조류독감 vs 인공지능)
            is_excluded = False
            for kw in search_keywords:
                kw_lower = kw.lower()
                exclusion_patterns = self._AMBIGUOUS_KEYWORD_EXCLUSIONS.get(kw_lower, [])
                for pattern in exclusion_patterns:
                    if pattern.search(combined):
                        logger.debug("다의어 필터링 (%s): %s", kw, title[:50])
                        is_excluded = True
                        break
                if is_excluded:
                    break

            if is_excluded:
                scored_articles.append((news, -1))  # -1 = 제외
                continue

            # 3. 키워드 관련도 점수 계산
            relevance = 0
            for kw in search_keywords:
                kw_lower = kw.lower()
                if kw_lower in title_lower:
                    relevance += 3
                if kw_lower in body_prefix.lower():
                    relevance += 1

            scored_articles.append((news, relevance))

        # 제외(-1) 기사를 빼고 관련 기사만 유지
        relevant = [news for news, score in scored_articles if score > 0]

        if relevant:
            max_score = max(score for _, score in scored_articles if score > 0)
            if max_score > 3:
                strongly_relevant = [
                    news for news, score in scored_articles
                    if score >= max_score * 0.4
                ]
                if strongly_relevant:
                    logger.debug(
                        "토픽 필터링: %d -> %d 기사 (키워드: %s)",
                        len(news_list), len(strongly_relevant), search_keywords
                    )
                    return strongly_relevant

            logger.debug(
                "토픽 필터링: %d -> %d 기사 (키워드: %s)",
                len(news_list), len(relevant), search_keywords
            )
            return relevant

        # 관련 기사가 하나도 없으면 원본 반환 (제외 기사 빼고)
        non_excluded = [news for news, score in scored_articles if score >= 0]
        return non_excluded if non_excluded else news_list

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
                            # Phase 2: scraped.images는 List[ImageInfo]이므로 .url로 접근
                            for img_info in scraped.images:
                                if img_info.url not in new_images:
                                    new_images.append(img_info.url)
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
        """문장 추출 및 분류 (오피니언/칼럼 기사 제외)"""
        all_sentences: List[ClassifiedSentence] = []
        keywords = keywords or []

        for news in news_list:
            # 오피니언/칼럼 기사는 중요도를 대폭 낮춤 (완전 제외 대신 가중치 감소)
            is_opinion = self._is_opinion_article(news)
            if is_opinion:
                logger.debug("오피니언/칼럼 기사 감지 (중요도 감소): %s", (news.title or "")[:40])

            body = news.body or ""
            # 문장 분리
            raw_sentences = self._split_sentences(body)

            for idx, sent in enumerate(raw_sentences):
                sent = sent.strip()
                # 원문 불릿/기호 접두어 제거
                sent = re.sub(r'^[○●◎▶▷►◆◇■□★☆·•※→\-]\s*', '', sent).strip()
                if len(sent) < 10:  # 너무 짧은 문장 제외
                    continue

                # 저작권/면책/광고 문장 필터링
                if self._is_boilerplate_sentence(sent):
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

                # 오피니언/칼럼 기사의 문장은 중요도 대폭 감소
                if is_opinion:
                    importance *= 0.2

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
        """문장 분리 (줄바꿈 + 구두점 기반)"""
        # 1단계: 줄바꿈으로 먼저 분리 (방송 뉴스 마커/자막 분리)
        lines = text.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 2단계: 구두점으로 추가 분리
            parts = re.split(r'(?<=[.!?])\s+', line)
            for sent in parts:
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

        # 6. 뉴스가치 키워드 보너스 (중요한 사건에 가중치)
        newsworthy_keywords = [
            '하한가', '상한가', '급등', '급락', '폭락', '폭등',
            '사상최고', '사상최대', '사상최저', '역대최', '신기록',
            '긴급', '속보', '비상', '파산', '부도', '서킷브레이커',
            '대폭', '전면', '중단', '재개', '철수', '파업',
        ]
        newsworthy_bonus = 0.0
        for nw in newsworthy_keywords:
            if nw in sentence:
                newsworthy_bonus = 0.15
                break

        # 가중 평균
        importance = (
            keyword_score * weights.get("keyword_match", 0.35) +
            position_score * weights.get("position_score", 0.20) +
            number_score * weights.get("has_number", 0.10) +
            length_score * weights.get("sentence_length", 0.10) +
            role_score * 0.25 +  # 역할 가중치는 별도
            newsworthy_bonus  # 뉴스가치 보너스
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

    # 매체명 목록 (인라인 필터링용)
    _MEDIA_NAMES = (
        '뉴스1', '연합뉴스', '조선일보', '중앙일보', '한국일보', '경향신문',
        '동아일보', '매일경제', '한국경제', '머니투데이', '뉴시스', 'YTN',
        'KBS', 'MBC', 'SBS', 'JTBC', '이데일리', '파이낸셜뉴스', '서울신문',
        '세계일보', '문화일보', '아시아경제', '헤럴드경제', '디지털타임스',
        '전자신문', '한겨레', 'CBS', 'TV조선', '채널A', 'MBN', '아주경제',
    )

    # 저작권/면책/광고/바이라인 문장 판별용 패턴
    _BOILERPLATE_PATTERNS = [
        # 저작권/면책
        re.compile(r'저작권자?\s*[\(（]?[cC©ⓒ][\)）]?'),
        re.compile(r'무단\s*(전재|복제|배포)'),
        re.compile(r'Copyright\s*[©ⓒ]', re.IGNORECASE),
        re.compile(r'All\s*[Rr]ights\s*[Rr]eserved'),
        re.compile(r'<저작권자'),
        re.compile(r'\[ⓒ\s'),
        re.compile(r'재배포\s*금지'),
        re.compile(r'기사\s*제공\s*[:：]'),
        re.compile(r'출처\s*[:：]\s*\S+\s*$'),
        # 기자 바이라인 (문장 시작 또는 문장 끝)
        re.compile(r'^\[.{2,20}(기자|특파원|팀)\]'),
        re.compile(r'^\[.{2,10}=.{2,10}\]\s*.{2,10}\s*(기자|특파원)'),
        re.compile(r'^\(.{2,10}=.{2,20}\)\s*.{2,20}\s*(기자|특파원|기자\s*=)'),
        re.compile(r'.{2,20}[=＝].{2,20}(기자|특파원)'),
        re.compile(r'(기자|특파원|앵커|리포터|진행자)\s*[:：]'),
        # 사진 캡션 (파이프 구분자 또는 [사진=출처])
        re.compile(r'^\|.*\|$'),
        re.compile(r'\[사진[=:].{2,30}\]'),
        # 광고/구독 유도
        re.compile(r'(구독|좋아요|공유).*(눌러|클릭|해주)'),
        # 관련 기사 헤드라인 (언론사 이름으로 끝남)
        re.compile(r'.{10,}(뉴스1|연합뉴스|조선일보|중앙일보|한국일보|경향신문|동아일보|매일경제|한국경제|머니투데이|뉴시스|YTN|KBS|MBC|SBS|JTBC|이데일리|파이낸셜뉴스|서울신문|세계일보|문화일보|아시아경제|헤럴드경제|디지털타임스|전자신문)$'),
        # 도메인 포함 문장 (관련 링크)
        re.compile(r'\w+\.(com|co\.kr|net|or\.kr|go\.kr)'),
        # 타임스탬프 (입력/수정 날짜시간)
        re.compile(r'(입력|수정|작성|게재|발행)\s*[:：]?\s*\d{4}[-./]\d{1,2}[-./]\d{1,2}'),
        # 연락처 (전화/팩스/이메일)
        re.compile(r'(전화|팩스|이메일|메일|Tel|Fax|Email)\s*[:：]?\s*[\d\-\(\)]+'),
        # 저작권 심볼
        re.compile(r'[ⓒⒸ©]\s*.{2,20}(닷컴|뉴스|일보|미디어|방송)'),
        # 방송 프로그램 마커
        re.compile(r'^[◀◁◀◀▶▷]\s*(앵커|기자|리포터|리포트|진행|출연)'),
        # 프로그램 이름 + 기자/앵커 이름
        re.compile(r'(뉴스투데이|뉴스9|뉴스데스크|아침뉴스|저녁뉴스)\s+.{2,10}$'),
        # 플레이스홀더 (CMS 템플릿 변수)
        re.compile(r'\[%%\w+%%\]'),
        # 기사 제목 + 날짜/출처 (parentheses에 언론사+날짜)
        re.compile(r'.*[\(（]\d{1,2}월\s*\d{1,2}일\s+.{2,15}[\)）]'),
        # 칼럼명 (대괄호 안에 저자명이나 칼럼명)
        re.compile(r'\[.{2,30}(의|이)\s+.{2,20}\]'),
        # 제작진 정보
        re.compile(r'(기획|출연|연출|편집|촬영|제작)[:：·]\s*.{2,10}\s*(논설위원|기자|피디|PD|작가|연출가)'),
        # 기자 보도 서명
        re.compile(r'.{2,10}\s*(기자|특파원|앵커|리포터)(의|가)?\s*(보도|리포트|전합니다|입니다)'),
        # 시청자 참여 유도
        re.compile(r'(제보|의견|문의).*(기다립니다|보내주세요|문의하세요)'),
        # 방송 프로그램 마무리 멘트
        re.compile(r'(시청|구독|좋아요|알림 설정).*(부탁|감사)'),
        # 대괄호 안 인물명 (캡션 스타일)
        re.compile(r'\[.{2,10}\s+(대통령|장관|의원|CEO|대표|국장|본부장)\]'),
        # ── 추가 패턴: 매체명 인라인 필터링 ──
        # 문장 끝에 매체명만 남은 경우 (예: "전기차 일제 급등(종합) 뉴스1")
        re.compile(r'\(종합\d*보?\)\s*(뉴스1|연합뉴스|뉴시스)'),
        # 원본 헤드라인이 그대로 삽입된 경우 (마침표 없이 끝나는 짧은 문장 + 매체명)
        re.compile(r'^.{5,60}\s+(뉴스1|연합뉴스|조선일보|중앙일보|한국일보|경향신문|동아일보|매일경제|한국경제|뉴시스)$'),
        # ── 추가 패턴: 오피니언/칼럼 특유 표현 ──
        # 의문형 도발 ("~것 아닙니까?", "~한다는 거죠?")
        re.compile(r'(것|거)\s*(아닙니까|아니겠습니까|아닌가요)\s*\??'),
        # 칼럼 특유 서술 ("~째가라면 서러워할", "~의 원톱은")
        re.compile(r'(째가라면\s*서러워|원톱은|투톱답)'),
        # 오적/n적 표현 (논썰 등)
        re.compile(r'.{2,6}오적'),
        # ── 추가 패턴: 원본 헤드라인 삽입 감지 ──
        # 마침표 없이 끝나는 헤드라인 스타일 (제목형 문장)
        re.compile(r'^.{5,50}…[가-힣]+\s*(터지나|주목|대응|전망|관측|논란)$'),
        # 브라우저 안내 메시지
        re.compile(r'(읽어주기|브라우저에서만)'),
        # 광고 마커 (AD)
        re.compile(r'^AD$'),
        # ── 방송 뉴스 아티팩트 ──
        # 방송 리포트/앵커/기자 태그 (문장 시작)
        re.compile(r'^\[리포트\]'),
        re.compile(r'^\[앵커\]'),
        re.compile(r'^\[기자\]'),
        re.compile(r'^\[인터뷰\]'),
        re.compile(r'^\[현장음\]'),
        re.compile(r'^\[녹취\]'),
        re.compile(r'^\[영상\]'),
        # 방송 인용: [이름/소속 : "인용문"] 또는 [이름/소속]
        re.compile(r'\[.{2,15}\s*/\s*[^]]{2,20}\s*:'),
        re.compile(r'\[.{2,10}\s*/\s*[^]]{2,20}\]'),
        # 방송 앵커/기자 이름 마커
        re.compile(r'^\[.{2,8}\s+(기자|앵커|특파원|리포터)\]'),
        # 방송 프로그램 큐시트 마커
        re.compile(r'^(앵커|기자|리포터)\s*[:>]\s*'),
    ]

    # 오피니언/칼럼 감지 패턴 (기사 전체 레벨에서 필터)
    _OPINION_INDICATORS = [
        re.compile(r'\[논썰\]'),
        re.compile(r'\[칼럼\]'),
        re.compile(r'\[사설\]'),
        re.compile(r'\[시론\]'),
        re.compile(r'\[기고\]'),
        re.compile(r'\[논단\]'),
        re.compile(r'\[이슈\+\]'),
        re.compile(r'\[오피니언\]'),
        re.compile(r'\[만평\]'),
        re.compile(r'\[커버스토리\]'),
    ]

    def _is_boilerplate_sentence(self, sentence: str) -> bool:
        """저작권/면책/광고/인라인 매체명/영어 문장인지 확인"""
        for pattern in self._BOILERPLATE_PATTERNS:
            if pattern.search(sentence):
                return True

        # 영어 문장 필터 (한국어 뉴스에 영문이 섞인 경우)
        # 한글 비율이 20% 미만이면 영어 문장으로 판단하여 제외
        if len(sentence) > 15:
            korean_chars = sum(1 for c in sentence if '\uac00' <= c <= '\ud7a3')
            total_alpha = sum(1 for c in sentence if c.isalpha())
            if total_alpha > 0 and korean_chars / total_alpha < 0.2:
                return True

        # 추가: 문장 끝에 매체명이 단독으로 붙어있는 경우 필터링
        # 예: "기술주 랠리에 테슬라도 3.50% 급등 뉴스1"
        stripped = sentence.rstrip('.!?').strip()
        for media in self._MEDIA_NAMES:
            if stripped.endswith(f' {media}') or stripped.endswith(f'\t{media}'):
                # 매체명을 제외한 부분이 온전한 문장인지 확인
                without_media = stripped[:-(len(media))].strip()
                # 60자 미만이면 관련 기사 헤드라인일 가능성이 높음
                if len(without_media) < 60:
                    return True

        return False

    def _is_opinion_article(self, news: 'NewsWithScores') -> bool:
        """오피니언/칼럼 기사인지 확인"""
        title = news.title or ""
        for pattern in self._OPINION_INDICATORS:
            if pattern.search(title):
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

    def _get_primary_source(self, sentences: List[ClassifiedSentence]) -> Optional[str]:
        """가장 관련도 높은 소스 기사 ID 반환 (교차 기사 혼합 방지)

        키워드 매칭과 중요도를 합산하여 가장 관련성 높은 소스를 식별합니다.
        이를 통해 본문에서 무관한 기사의 문장이 섞이는 것을 방지합니다.
        """
        if not sentences:
            return None

        source_scores: Dict[str, float] = {}
        for s in sentences:
            sid = s.source_news_id
            score = s.importance + len(s.matched_keywords) * 0.3
            source_scores[sid] = source_scores.get(sid, 0.0) + score

        if source_scores:
            return max(source_scores, key=lambda x: source_scores[x])
        return None

    def _create_paragraphs(self, sentences: List[ClassifiedSentence]) -> str:
        """지능형 문단 구분: 역할과 의미적 연결성 기반 자동 그룹핑

        문장을 역할(role)과 의미적 유사도를 기반으로 자동으로 문단으로 그룹핑합니다.
        - 역할이 변경되면 새 문단 시작
        - 문단 길이가 너무 길거나 짧으면 조정
        - 최소 문단 길이: 50자, 최대 문단 길이: 400자
        """
        if not sentences:
            return ""

        paragraphs = []
        current_paragraph = []
        current_role = None
        current_length = 0

        MIN_PARAGRAPH_LENGTH = 50  # 최소 문단 길이
        MAX_PARAGRAPH_LENGTH = 400  # 최대 문단 길이
        TARGET_PARAGRAPH_LENGTH = 200  # 목표 문단 길이

        for sentence in sentences:
            sentence_length = len(sentence.text)

            # 역할 변경 감지
            role_changed = current_role is not None and sentence.role != current_role

            # 문단을 나눌 조건:
            # 1. 역할이 변경되고 현재 문단이 최소 길이 이상
            # 2. 현재 문단이 최대 길이 초과
            should_break = False

            if role_changed and current_length >= MIN_PARAGRAPH_LENGTH:
                should_break = True
            elif current_length + sentence_length > MAX_PARAGRAPH_LENGTH and current_length >= MIN_PARAGRAPH_LENGTH:
                should_break = True

            if should_break and current_paragraph:
                # 현재 문단 완성
                paragraphs.append(" ".join(s.text for s in current_paragraph))
                current_paragraph = []
                current_length = 0

            # 문장 추가
            current_paragraph.append(sentence)
            current_length += sentence_length
            current_role = sentence.role

        # 마지막 문단 추가
        if current_paragraph:
            paragraphs.append(" ".join(s.text for s in current_paragraph))

        # 너무 짧은 문단은 이전 문단과 병합
        merged_paragraphs = []
        for i, para in enumerate(paragraphs):
            if len(para) < MIN_PARAGRAPH_LENGTH and merged_paragraphs:
                # 이전 문단과 병합
                merged_paragraphs[-1] += " " + para
            else:
                merged_paragraphs.append(para)

        return "\n\n".join(merged_paragraphs)

    def _source_preferred_select(
        self,
        candidates: List[ClassifiedSentence],
        primary_source: Optional[str],
        max_count: int,
        strict: bool = True,
    ) -> List[ClassifiedSentence]:
        """Primary source 문장 우선 선택 (교차 기사 혼합 방지)

        strict=True (기본값): primary source 문장만 사용, 부족해도 secondary 사용 안 함
        strict=False: primary source 부족 시 secondary source에서 보충
        """
        if not primary_source or not candidates:
            return candidates[:max_count]

        primary = [s for s in candidates if s.source_news_id == primary_source]

        if strict:
            # 엄격 모드: primary source만 사용 (교차 혼합 최소화)
            return primary[:max_count]
        else:
            # 관대 모드: 부족 시 secondary 보충
            secondary = [s for s in candidates if s.source_news_id != primary_source]
            result = primary[:max_count]
            remaining = max_count - len(result)
            if remaining > 0:
                result.extend(secondary[:remaining])
            return result

    def _build_sections(
        self,
        sentences: List[ClassifiedSentence],
        format: NewsFormat,
        news_type: Optional[str] = None,
    ) -> Dict[str, str]:
        """포맷별 섹션 구성 (뉴스 유형 반영)"""
        format_name = format.value.lower()
        spec = self.config.get_format_spec(format_name)

        if format == NewsFormat.STRAIGHT:
            # 뉴스 유형별 빌더 분기
            if news_type == NewsType.VISUAL:
                return self._build_visual_straight(sentences, spec)
            elif news_type == NewsType.DATA:
                return self._build_data_straight(sentences, spec)
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
        """스트레이트 뉴스 구성 (제한 없음, 원본 기사의 자연스러운 구조 존중)"""
        sections_spec = spec.get("sections", {})

        # 섹션별 설정 조회 (우선 역할만 사용)
        lead_spec = sections_spec.get("lead", {})
        body_spec = sections_spec.get("body", {})
        closing_spec = sections_spec.get("closing", {})

        # 섹션별 우선 역할
        lead_roles = tuple(lead_spec.get("priority_roles", ["lead", "fact"]))
        body_roles = tuple(body_spec.get("priority_roles", ["background", "detail", "quote"]))
        closing_roles = tuple(closing_spec.get("priority_roles", ["outlook", "implication"]))

        used_texts: Set[str] = set()

        # ★ Primary source 식별 (교차 기사 혼합 방지)
        primary_source = self._get_primary_source(sentences)

        # 안전장치: 최대 문장 수 제한 (극단적 케이스만)
        sentences = sentences[:self.MAX_TOTAL_SENTENCES]

        # 리드: Primary source의 모든 lead 역할 문장
        lead_candidates = [
            s for s in sentences
            if s.role in lead_roles and s.source_news_id == primary_source
        ]
        lead_sentences = lead_candidates if lead_candidates else sentences[:1]
        lead = " ".join(s.text for s in lead_sentences)
        used_texts.update(s.text for s in lead_sentences)

        # 본문: Primary source의 모든 body 역할 문장 (지능형 문단 구분)
        body_candidates = [
            s for s in sentences
            if s.role in body_roles
            and s.source_news_id == primary_source
            and s.text not in used_texts
        ]
        body_sentences = body_candidates

        # 지능형 문단 구분: 역할 기반 자동 그룹핑
        body = self._create_paragraphs(body_sentences)
        used_texts.update(s.text for s in body_sentences)

        # 마무리: Primary source의 모든 closing 역할 문장
        closing_candidates = [
            s for s in sentences
            if s.role in closing_roles
            and s.source_news_id == primary_source
            and s.text not in used_texts
        ]
        closing_sentences = closing_candidates
        closing = " ".join(s.text for s in closing_sentences)

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
        """분석 기사 (1500-3000자) - 다중 소스 통합 (primary source 제한 해제)"""
        used_texts: Set[str] = set()

        # 분석 기사는 다중 소스 통합이 핵심이므로 primary source 제한을 두지 않음
        # 현황 섹션 (모든 소스에서 가장 중요한 팩트)
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

    def _build_visual_straight(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """비주얼 뉴스 구성 (이미지 중심, 제한 없음)

        news_format_spec.yaml의 visual 섹션 규격 적용:
        - 제한 없음 (원본 기사의 자연스러운 구조)
        - 리드: 상황 설명 (누가/어디서/언제)
        - 본문: 장면/내용 묘사
        - 마무리: 전망/마무리
        """
        primary_source = self._get_primary_source(sentences)
        used_texts: Set[str] = set()

        # 안전장치
        sentences = sentences[:self.MAX_TOTAL_SENTENCES]

        # 리드: Primary source의 모든 lead/fact/background 문장
        lead_candidates = [
            s for s in sentences
            if s.role in ("lead", "fact", "background")
            and s.source_news_id == primary_source
        ]
        lead_sentences = lead_candidates if lead_candidates else sentences[:1]
        lead = " ".join(s.text for s in lead_sentences)
        used_texts.update(s.text for s in lead_sentences)

        # 본문: Primary source의 나머지 문장 (closing 제외)
        body_candidates = [
            s for s in sentences
            if s.text not in used_texts
            and s.source_news_id == primary_source
            and s.role not in ("outlook", "implication")
        ]
        body_sentences = body_candidates
        body = " ".join(s.text for s in body_sentences)
        used_texts.update(s.text for s in body_sentences)

        # 마무리: Primary source의 outlook/implication 문장
        closing_candidates = [
            s for s in sentences
            if s.role in ("outlook", "implication")
            and s.source_news_id == primary_source
            and s.text not in used_texts
        ]
        closing = " ".join(s.text for s in closing_candidates)

        return {
            "lead": lead.strip(),
            "body": self._add_connectors(body.strip(), "body"),
            "closing": closing.strip(),
        }

    def _build_data_straight(
        self,
        sentences: List[ClassifiedSentence],
        spec: Dict[str, Any],
    ) -> Dict[str, str]:
        """데이터 뉴스 구성 (수치/통계 중심, 제한 없음)

        news_format_spec.yaml의 data 섹션 규격 적용:
        - 제한 없음 (원본 기사의 자연스러운 구조)
        - 리드: 핵심 수치 포함 문장 우선
        - 본문: 분석/배경, 숫자 포함 문장 우선
        - 마무리: 전망/시사점
        """
        primary_source = self._get_primary_source(sentences)
        used_texts: Set[str] = set()

        # 안전장치
        sentences = sentences[:self.MAX_TOTAL_SENTENCES]

        # 리드: Primary source의 statistic/lead 문장 (숫자 포함 우선)
        stat_leads = [
            s for s in sentences
            if s.role in ("statistic", "lead")
            and s.has_number
            and s.source_news_id == primary_source
        ]
        if not stat_leads:
            stat_leads = [
                s for s in sentences
                if s.role in ("lead", "fact")
                and s.source_news_id == primary_source
            ]
        lead_sentences = stat_leads if stat_leads else sentences[:1]
        lead = " ".join(s.text for s in lead_sentences)
        used_texts.update(s.text for s in lead_sentences)

        # 본문: Primary source의 나머지 문장 (숫자 포함 우선)
        body_candidates = [
            s for s in sentences
            if s.text not in used_texts
            and s.source_news_id == primary_source
            and s.role not in ("outlook", "implication")
        ]
        # 숫자 포함 문장 우선 정렬
        with_numbers = [s for s in body_candidates if s.has_number]
        without_numbers = [s for s in body_candidates if not s.has_number]
        body_sentences = with_numbers + without_numbers
        body = " ".join(s.text for s in body_sentences)
        used_texts.update(s.text for s in body_sentences)

        # 마무리: Primary source의 outlook/implication 문장
        closing_candidates = [
            s for s in sentences
            if s.role in ("outlook", "implication")
            and s.source_news_id == primary_source
            and s.text not in used_texts
        ]
        closing = " ".join(s.text for s in closing_candidates)

        return {
            "lead": lead.strip(),
            "body": self._add_connectors(body.strip(), "body"),
            "closing": closing.strip(),
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

    def _normalize_image_url(self, url: str) -> str:
        """이미지 URL 정규화 (도메인 무시, 경로만 사용하여 중복 판단)

        Phase 1 개선: 도메인 제거, 경로만 비교
        - 같은 이미지가 다른 CDN에서 오면 중복으로 감지
        - 예: https://cdn1.com/news/photo.jpg?w=800 → /news/photo.jpg
        - 예: https://cdn2.com/news/photo.jpg → /news/photo.jpg (중복!)

        Args:
            url: 원본 URL

        Returns:
            정규화된 경로 (도메인/쿼리 제외)
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            # 경로만 사용 (도메인, 쿼리, 프래그먼트 제거)
            path = parsed.path

            # 경로가 없으면 전체 URL 사용 (fallback)
            if not path or path == '/':
                return url.lower()

            return path.lower()  # 대소문자 통일
        except Exception as e:
            logger.debug(f"URL 정규화 실패: {e}")
            return url.lower()

    def _is_valid_news_image(self, img_url: str) -> bool:
        """뉴스 관련 이미지인지 검증 (광고/아이콘/UI 이미지 제외)"""
        if not img_url:
            return False

        # HTTP로 시작해야 함
        if not img_url.startswith('http'):
            return False

        # 플레이스홀더/템플릿 변수 제외 (중괄호 변수 포함)
        if '{{' in img_url or '}}' in img_url or '{%' in img_url or '${' in img_url or '%%' in img_url:
            return False
        # {wcms_img} 등 치환되지 않은 변수
        if re.search(r'\{[a-zA-Z_]+\}', img_url):
            return False

        url_lower = img_url.lower()

        # 제외할 확장자 (SVG/ICO/GIF 등)
        excluded_extensions = ('.svg', '.ico', '.cur', '.gif')
        path = url_lower.split('?')[0]
        if any(path.endswith(ext) for ext in excluded_extensions):
            return False

        # 제외 패턴 (광고, 아이콘, 로고 등) - content_scraper.py와 동일
        exclude_patterns = [
            # 아이콘/로고/버튼/UI 요소
            'icon', 'logo', 'btn', 'button', 'badge',
            'util_', '_util', 'view_util', 'view_btn', 'view_bt',
            'tool-', '-tool', 'bookmark', 'print', 'copy', 'font',
            # 상단/하단 UI 이미지
            'top.', 'bottom.', '/top.', '/bottom.',
            # 날씨 아이콘
            'weather/', '/weather_', 'weather_icon',
            # 국기/플래그 이미지
            'flag_', '_flag', '/flag/', 'country_',
            # 추가 아이콘 패턴
            'ic_', '/ic_', 'img_icon',
            # 배경/장식/정보 이미지
            '_bg', 'bg_', '_bg.', 'series_', 'header_', 'footer_',
            '_info', 'info_', 'notice_', 'popup_', 'modal_',
            # 광고 관련
            'banner', 'ad_', 'ads_', '/ad/', '/ads/', 'adsense', 'advert', 'sponsor',
            'promo', 'promotion', 'campaign', 'click', 'track',
            # SNS 공유 버튼
            'sns', 'share', 'view_sns', 'social',
            'kakao', 'facebook', 'twitter', 'naver_', 'google_',
            'instagram', 'youtube', 'tiktok', 'linkedin',
            # 작은/썸네일/피드 이미지
            'thumb_s', 'thumb_xs', '_s.', '_xs.', '_t.',
            'small_', '_small', 'mini_', '_mini', 'thumbnail_small', '.thumb.',
            '/feed/', 'feed_', '_feed', '_thumb', '/thumb/',
            # 기자/관련기사/멤버 이미지
            'journalist', 'reporter', 'byline', 'author',
            '/member/', 'member_', '_member',
            'related_', '_related', 'recommend', 'sidebar',
            # 플레이어/비디오 UI
            'player', 'video_', '_video', 'play_', '_play',
            # 기타 UI/플레이스홀더
            'loading', 'spinner', 'placeholder', 'default', 'no-image', 'noimage',
            'pixel', 'tracker', 'spacer', 'blank', 'transparent',
            '1x1', '1px', 'sprite', 'emoji', 'avatar', 'profile',
            'nav_', 'menu_', 'comment', 'reply', 'like', 'dislike',
            # 로봇/검색 아이콘 (흔한 사이트 UI)
            'robot.png', 'search.png', 'search_icon', 'robots.png',
            # UI 장식/불릿/아이콘 이미지
            'bul_', '_bul', 'bullet', 'dot_', 'arr_', 'arrow_',
            'ico_', '_ico', 'g_circle', 'circle_',
            # 극소 썸네일 경로
            'thumbnail/custom/', '_120.jpg', '_120.png',
        ]

        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False

        # 크기 추정 (URL에 크기 정보가 있는 경우)
        size_pattern = r'[_-](\d+)x(\d+)'
        size_match = re.search(size_pattern, url_lower)
        if size_match:
            width, height = int(size_match.group(1)), int(size_match.group(2))
            if width < 150 or height < 100:
                return False

        # 쿼리스트링 크기 파라미터 체크 (w=105&h=67 등)
        qs_w_match = re.search(r'[?&]w=(\d+)', url_lower)
        qs_h_match = re.search(r'[?&]h=(\d+)', url_lower)
        if qs_w_match and qs_h_match:
            w, h = int(qs_w_match.group(1)), int(qs_h_match.group(1))
            if w < 150 or h < 100:
                return False

        return True

    # ==============================================================================
    # 이미지 품질 개선: 워터마크 처리 및 원본 찾기
    # ==============================================================================

    def _check_image_quality(self, url: str) -> bool:
        """이미지 품질 검증 (HEAD 요청으로 메타데이터만 확인)

        체크 항목:
        1. Content-Length: 최소 10KB (저화질 제외)
        2. Content-Type: image/* 확인

        Args:
            url: 이미지 URL

        Returns:
            True: 품질 OK, False: 저화질/무효
        """
        try:
            # HEAD 요청 (본문 다운로드 안 함)
            response = requests.head(
                url,
                timeout=3,
                allow_redirects=True,
                headers={'User-Agent': 'Mozilla/5.0'}
            )

            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                return False

            # 파일 크기 확인 (최소 10KB)
            content_length = response.headers.get('Content-Length')
            if content_length:
                size_kb = int(content_length) / 1024
                if size_kb < 10:  # 10KB 미만은 아이콘/썸네일
                    logger.debug(f"이미지 크기 부족: {size_kb:.1f}KB < 10KB")
                    return False
                if size_kb > 5000:  # 5MB 초과는 너무 큼
                    logger.debug(f"이미지 크기 초과: {size_kb:.1f}KB > 5MB")
                    return False

            return True

        except Exception as e:
            # 네트워크 오류 시 일단 통과 (너무 엄격하면 이미지 없음)
            logger.debug(f"이미지 품질 체크 실패: {e}")
            return True

    def _validate_image_dimensions(self, url: str) -> tuple:
        """이미지 해상도 확인 (헤더만 다운로드)

        Args:
            url: 이미지 URL

        Returns:
            (width, height) or (None, None)
        """
        try:
            from PIL import Image

            response = requests.get(
                url,
                timeout=3,
                stream=True,
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Range': 'bytes=0-5000'  # 첫 5KB만
                }
            )

            # PIL로 헤더 파싱
            img = Image.open(BytesIO(response.content))
            width, height = img.size

            logger.debug(f"이미지 해상도: {width}x{height}")
            return width, height

        except Exception as e:
            logger.debug(f"이미지 해상도 확인 실패: {e}")
            return None, None

    def _check_image_relevance(
        self,
        img_url: str,
        article_keywords: List[str],
        img_info: Optional[Any] = None
    ) -> bool:
        """이미지-내용 관련성 검증 (개선된 버전)

        점수 기반 시스템:
        - 높은 관련성 (5점 이상): 확실히 관련됨
        - 중간 관련성 (2-4점): 관련 가능성 있음
        - 낮은 관련성 (0-1점): 관련 없음

        점수 부여:
        - 키워드 매칭 (alt/title): +3점
        - 키워드 매칭 (파일명): +2점
        - article 태그 내부: +2점
        - 상위 위치 (position < 3): +1점

        Args:
            img_url: 이미지 URL
            article_keywords: 기사 키워드
            img_info: 이미지 메타데이터 (ImageInfo 객체)

        Returns:
            True: 관련성 있음 (2점 이상), False: 관련 없음
        """
        if not article_keywords:
            return True  # 키워드 없으면 통과

        try:
            relevance_score = 0

            # ImageInfo가 있으면 메타데이터 활용
            if img_info:
                # 1. article 태그 내부 (+3점, 기본 관련성 높음)
                if hasattr(img_info, 'in_article') and img_info.in_article:
                    relevance_score += 3
                    logger.debug(f"이미지 article 내부 (점수: {relevance_score})")

                # 2. alt/title에서 키워드 매칭 (+3점 추가)
                img_keywords = img_info.get_relevance_keywords()
                for keyword in article_keywords[:5]:
                    keyword_lower = keyword.lower()
                    if any(keyword_lower in img_kw for img_kw in img_keywords):
                        relevance_score += 3
                        logger.debug(f"이미지 alt/title 매칭: '{keyword}' (점수: {relevance_score})")
                        break

                # 3. 상위 위치 (+1점)
                if hasattr(img_info, 'position') and img_info.position < 3:
                    relevance_score += 1
            else:
                # ImageInfo 없는 경우 기본 점수 (+2점, 관대하게 처리)
                relevance_score += 2
                logger.debug(f"ImageInfo 없음, 기본 점수 부여 (점수: {relevance_score})")

            # 4. URL 파일명에서 키워드 매칭 (+2점)
            from urllib.parse import urlparse
            parsed = urlparse(img_url)
            filename = parsed.path.split('/')[-1].lower()

            for keyword in article_keywords[:5]:
                if keyword.lower() in filename:
                    relevance_score += 2
                    logger.debug(f"이미지 파일명 매칭: '{keyword}' in {filename} (점수: {relevance_score})")
                    break

            # 최종 판단
            # - 2점 미만: 관련 없음
            # - 2점 이상: 관련 있음 (article 내부는 자동 3점이므로 통과)
            is_relevant = relevance_score >= 2

            if not is_relevant:
                logger.debug(f"이미지 관련성 낮음 (점수: {relevance_score}): {img_url}")

            return is_relevant

        except Exception as e:
            logger.debug(f"이미지 관련성 체크 실패: {e}")
            # 예외 발생 시 관대하게 통과 (너무 엄격하면 이미지 없음)
            return True

    def _extract_organizations(self, text: str) -> List[str]:
        """텍스트에서 조직명 추출

        Args:
            text: 기사 본문

        Returns:
            조직명 리스트
        """
        found_orgs = []
        for org_name in self.OFFICIAL_NEWSROOMS.keys():
            if org_name in text:
                found_orgs.append(org_name)
        return found_orgs

    def _detect_watermark_position(self, img_url: str) -> str:
        """워터마크 위치 감지 (URL 패턴 기반 간단 버전)

        Args:
            img_url: 이미지 URL

        Returns:
            "none": 워터마크 없음
            "corner": 코너 워터마크 (우하단/좌하단)
            "center": 중앙 워터마크
        """
        url_lower = img_url.lower()

        # URL에 워터마크 표시가 있는 경우
        if any(p in url_lower for p in ['/watermark/', '/wm/', '_wm.', '-wm.']):
            # 중앙 워터마크 명시
            if 'center' in url_lower or 'full' in url_lower:
                return "center"
            return "corner"

        # 기본: 없다고 가정 (대부분 코너 워터마크는 URL에 표시 안 함)
        return "none"

    def _should_find_original(
        self,
        article_text: str,
        watermark_position: str
    ) -> bool:
        """원본 찾기 vs 스크린샷 판단

        기준:
        1. 중앙 워터마크 → 무조건 원본 찾기
        2. 대기업/정부 언급 → 원본 찾기 시도
        3. 나머지 → 스크린샷 사용

        Args:
            article_text: 기사 본문
            watermark_position: 워터마크 위치

        Returns:
            True: 원본 찾기, False: 스크린샷
        """
        # 중앙 워터마크는 무조건 원본 찾기
        if watermark_position == "center":
            return True

        # 기사에서 주요 조직 추출
        orgs = self._extract_organizations(article_text)

        # 주요 조직이 언급되면 원본 찾기 시도
        if orgs:
            return True

        return False

    def _find_original_from_newsroom(
        self,
        org_name: str,
        article_keywords: List[str],
        article_date: Optional[str] = None
    ) -> Optional[str]:
        """공식 뉴스룸에서 원본 이미지 찾기

        Args:
            org_name: 조직명
            article_keywords: 기사 키워드
            article_date: 기사 날짜 (선택)

        Returns:
            원본 이미지 URL or None
        """
        newsroom_url = self.OFFICIAL_NEWSROOMS.get(org_name)
        if not newsroom_url:
            return None

        try:
            # 간단 구현: 뉴스룸 메인 페이지 크롤링
            # (실제로는 각 사이트별 검색 API 사용 권장)
            from bs4 import BeautifulSoup

            response = requests.get(
                newsroom_url,
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0'}
            )

            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            # 최근 이미지 찾기
            # (각 사이트마다 구조가 다르므로 일반적인 img 태그 검색)
            images = soup.find_all('img', src=True)

            # 키워드 매칭하여 관련 이미지 찾기
            for img in images[:10]:  # 최근 10개만 체크
                img_url = img.get('src', '')
                img_alt = img.get('alt', '')

                # 상대 URL을 절대 URL로 변환
                if img_url.startswith('/'):
                    from urllib.parse import urljoin
                    img_url = urljoin(newsroom_url, img_url)

                # 키워드 매칭 (이미지 alt 텍스트와 비교)
                if article_keywords and img_alt:
                    if any(kw in img_alt for kw in article_keywords[:3]):
                        # 유효한 이미지 URL인지 확인
                        if self._is_valid_image_url(img_url):
                            logger.info(f"원본 이미지 발견: {org_name} 뉴스룸 - {img_url}")
                            return img_url

            return None

        except Exception as e:
            logger.warning(f"뉴스룸 검색 실패 ({org_name}): {e}")
            return None

    def _screenshot_image(
        self,
        news_url: str,
        img_url: str
    ) -> Optional[str]:
        """스크린샷으로 이미지 확보 (워터마크 우회)

        Args:
            news_url: 뉴스 기사 URL
            img_url: 이미지 URL

        Returns:
            스크린샷 이미지 경로 or None
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager
            import tempfile

            # 헤드리스 모드 설정
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')

            # WebDriver 자동 설치 및 실행
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_window_size(1920, 1080)

            try:
                # 기사 페이지 로드
                driver.get(news_url)

                # 이미지 로드 대기 (최대 10초)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "img"))
                )

                # 이미지 요소 찾기
                images = driver.find_elements(By.TAG_NAME, "img")
                target_img = None

                for img in images:
                    src = img.get_attribute('src')
                    if src and img_url in src:
                        target_img = img
                        break

                if not target_img:
                    logger.warning(f"이미지 요소를 찾을 수 없음: {img_url}")
                    return None

                # 스크린샷 저장
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix='.png',
                    dir=tempfile.gettempdir()
                )

                target_img.screenshot(temp_file.name)
                logger.info(f"스크린샷 저장: {temp_file.name}")

                return temp_file.name

            finally:
                driver.quit()

        except Exception as e:
            logger.warning(f"스크린샷 실패 ({img_url}): {e}")
            return None

    def _get_clean_image(
        self,
        article_text: str,
        article_keywords: List[str],
        img_url: str,
        news_url: str,
        img_info: Optional[Any] = None
    ) -> Optional[str]:
        """깨끗한 이미지 확보 (워터마크 제거/우회 + 품질 검증)

        전략:
        1. 기본 품질 체크 (파일 크기, 해상도)
        2. 관련성 체크 (키워드 매칭 + ImageInfo 메타데이터)
        3. 워터마크 위치 감지
        4. 중앙 워터마크 → 원본 찾기 (실패 시 None)
        5. 코너 워터마크 + 대기업/정부 → 원본 찾기 시도 → 실패 시 스크린샷
        6. 코너 워터마크 + 기타 → 스크린샷

        Args:
            article_text: 기사 본문
            article_keywords: 기사 키워드
            img_url: 원본 이미지 URL (워터마크 있을 수 있음)
            news_url: 뉴스 기사 URL
            img_info: 이미지 메타데이터 (ImageInfo 객체)

        Returns:
            깨끗한 이미지 URL/경로 or None
        """
        # 0. 기본 품질 체크 (파일 크기)
        if not self._check_image_quality(img_url):
            logger.debug(f"이미지 품질 부족: {img_url}")
            return None

        # 0-1. 해상도 체크 (최소 400px)
        width, height = self._validate_image_dimensions(img_url)
        if width and height:
            if width < 400 or height < 300:
                logger.debug(f"이미지 해상도 부족: {width}x{height}")
                return None

        # 0-2. 관련성 체크 (ImageInfo 메타데이터 활용)
        if not self._check_image_relevance(img_url, article_keywords, img_info):
            logger.debug(f"이미지 관련성 낮음: {img_url}")
            return None

        # 1. 워터마크 분석
        watermark_pos = self._detect_watermark_position(img_url)

        # 2. 워터마크 없으면 그대로 사용
        if watermark_pos == "none":
            return img_url

        # 3. 중앙 워터마크 → 무조건 원본 찾기
        if watermark_pos == "center":
            orgs = self._extract_organizations(article_text)
            for org in orgs:
                original = self._find_original_from_newsroom(
                    org,
                    article_keywords
                )
                if original:
                    return original

            # 원본 못 찾으면 None (이미지 없이 발행)
            logger.warning(f"중앙 워터마크 이미지 원본 못 찾음: {img_url}")
            return None

        # 4. 코너 워터마크 → 출처에 따라 결정
        if self._should_find_original(article_text, watermark_pos):
            # 대기업/정부 → 원본 찾기 시도
            orgs = self._extract_organizations(article_text)
            for org in orgs:
                original = self._find_original_from_newsroom(
                    org,
                    article_keywords
                )
                if original:
                    return original

            # 원본 못 찾으면 스크린샷 폴백
            logger.info(f"원본 못 찾음, 스크린샷 시도: {img_url}")
            screenshot = self._screenshot_image(news_url, img_url)
            if screenshot:
                return screenshot

            # 스크린샷도 실패하면 원본 그대로 (워터마크 있지만)
            return img_url

        else:
            # 중소기업/연예 → 바로 스크린샷
            screenshot = self._screenshot_image(news_url, img_url)
            if screenshot:
                return screenshot

            # 스크린샷 실패하면 원본 그대로
            return img_url
