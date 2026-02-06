"""Stage 3 뉴스 생성 데이터 모델

뉴스 포맷, 생성된 뉴스, 인용 정보 등을 담는 데이터 클래스들.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any


# ============================================================
# 뉴스 포맷 정의
# ============================================================

class NewsFormat(Enum):
    """뉴스 포맷 유형"""
    # === 기본 포맷 ===
    STRAIGHT = "straight"           # 스트레이트 뉴스 (육하원칙)
    BRIEF = "brief"                 # 단신 (100자 이내)

    # === 심층/기획 포맷 ===
    ANALYSIS = "analysis"           # 분석 기사 (배경 + 전망)
    FEATURE = "feature"             # 기획 기사 (심층 취재)
    EXPLAINER = "explainer"         # 해설 기사 (쉬운 설명)
    TIMELINE = "timeline"           # 타임라인 기사 (시간순 정리)
    COMPARISON = "comparison"       # 비교 기사 (A vs B)

    # === 비주얼 중심 포맷 ===
    PHOTO_NEWS = "photo_news"       # 포토뉴스 (사진 + 짧은 설명)
    CARD_NEWS = "card_news"         # 카드뉴스 (슬라이드형)
    INFOGRAPHIC = "infographic"     # 인포그래픽 (데이터 시각화)

    # === 숏폼/SNS 포맷 ===
    SOCIAL_POST = "social_post"     # SNS 포스트 (280자 이내)
    SHORT_VIDEO_SCRIPT = "short_video"  # 숏폼 영상 스크립트
    THREAD = "thread"               # 트위터 스레드형

    # === 뉴스레터/브리핑 ===
    NEWSLETTER = "newsletter"       # 이메일 뉴스레터
    DAILY_BRIEFING = "daily_briefing"   # 일일 브리핑
    WEEKLY_DIGEST = "weekly_digest"     # 주간 다이제스트

    # === 특수 포맷 ===
    QNA = "qna"                     # Q&A 형식
    LISTICLE = "listicle"           # 리스트형 기사 (Top 10 등)
    OPINION = "opinion"             # 오피니언/칼럼


# ============================================================
# 포맷 스펙 정의
# ============================================================

@dataclass
class FormatSpec:
    """포맷별 상세 스펙"""
    format: NewsFormat
    min_length: int              # 최소 글자 수
    max_length: int              # 최대 글자 수
    structure: List[str]         # 필수 구조 요소
    image_count: str             # "0", "1", "2-3", "5+"
    use_case: str                # 용도 설명


# 포맷별 스펙 정의
FORMAT_SPECS: Dict[NewsFormat, FormatSpec] = {
    NewsFormat.STRAIGHT: FormatSpec(
        format=NewsFormat.STRAIGHT,
        min_length=400, max_length=800,
        structure=["lead", "body", "closing"],
        image_count="1",
        use_case="일반 뉴스",
    ),
    NewsFormat.BRIEF: FormatSpec(
        format=NewsFormat.BRIEF,
        min_length=50, max_length=100,
        structure=["single_paragraph"],
        image_count="0",
        use_case="속보, 단신",
    ),
    NewsFormat.ANALYSIS: FormatSpec(
        format=NewsFormat.ANALYSIS,
        min_length=1500, max_length=3000,
        structure=["current", "background", "outlook", "implications"],
        image_count="2-3",
        use_case="심층 보도",
    ),
    NewsFormat.FEATURE: FormatSpec(
        format=NewsFormat.FEATURE,
        min_length=2000, max_length=5000,
        structure=["intro", "sections", "conclusion"],
        image_count="5+",
        use_case="기획 시리즈",
    ),
    NewsFormat.EXPLAINER: FormatSpec(
        format=NewsFormat.EXPLAINER,
        min_length=800, max_length=1500,
        structure=["question", "answer", "context"],
        image_count="1-2",
        use_case="복잡한 이슈 해설",
    ),
    NewsFormat.CARD_NEWS: FormatSpec(
        format=NewsFormat.CARD_NEWS,
        min_length=150, max_length=500,
        structure=["cards"],
        image_count="5-10",
        use_case="SNS 공유용",
    ),
    NewsFormat.SOCIAL_POST: FormatSpec(
        format=NewsFormat.SOCIAL_POST,
        min_length=50, max_length=280,
        structure=["hook", "main", "cta"],
        image_count="1",
        use_case="트위터/인스타",
    ),
    NewsFormat.NEWSLETTER: FormatSpec(
        format=NewsFormat.NEWSLETTER,
        min_length=1000, max_length=2000,
        structure=["greeting", "sections", "footer"],
        image_count="thumbnails",
        use_case="이메일 발송",
    ),
    NewsFormat.LISTICLE: FormatSpec(
        format=NewsFormat.LISTICLE,
        min_length=1000, max_length=2000,
        structure=["intro", "items", "conclusion"],
        image_count="per_item",
        use_case="정보 정리형",
    ),
    NewsFormat.QNA: FormatSpec(
        format=NewsFormat.QNA,
        min_length=500, max_length=1500,
        structure=["intro", "qa_pairs", "summary"],
        image_count="0-1",
        use_case="FAQ 형식",
    ),
}


# ============================================================
# 생성 모드
# ============================================================

class GenerationMode(Enum):
    """뉴스 생성 모드"""
    REWRITE = "rewrite"         # 기존 기사 리라이팅 (1개 → 1개)
    SYNTHESIS = "synthesis"     # 다중 기사 통합 (N개 → 1개)
    EXPANSION = "expansion"     # 기사 확장/심화
    COMPRESSION = "compression" # 기사 압축/요약
    TRANSFORM = "transform"     # 포맷 변환


# ============================================================
# 인용 관련
# ============================================================

class CitationType(Enum):
    """인용 유형"""
    DIRECT_QUOTE = "direct_quote"   # 직접 인용 (원문 그대로)
    PARAPHRASE = "paraphrase"       # 패러프레이징 (재작성)
    FACT = "fact"                   # 팩트 인용 (사실 정보)


@dataclass
class Citation:
    """인용 정보"""
    source_news_id: str
    source_name: str
    source_url: str
    cited_content: str           # 인용된 내용
    citation_type: CitationType
    position: int = 0            # 기사 내 위치 (문단 번호)
    original_text: str = ""      # 원본 텍스트 (직접 인용 시)


# ============================================================
# 비주얼 자산
# ============================================================

@dataclass
class ImageAsset:
    """이미지 자산"""
    id: str
    url: str
    alt_text: str
    source: str                  # "unsplash", "generated", "original"
    position: int = 0            # 기사 내 위치
    caption: str = ""


@dataclass
class ChartAsset:
    """차트 자산"""
    id: str
    chart_type: str              # "bar", "line", "pie", "table"
    data: Dict[str, Any]
    title: str = ""
    position: int = 0


# ============================================================
# 검수 상태
# ============================================================

class ReviewStatus(Enum):
    """검수 상태"""
    DRAFT = "draft"                 # 초안
    PENDING_REVIEW = "pending_review"  # 검수 대기
    IN_REVIEW = "in_review"         # 검수 중
    APPROVED = "approved"           # 승인됨
    REJECTED = "rejected"           # 거부됨
    REVISION_NEEDED = "revision_needed"  # 수정 필요


@dataclass
class ReviewRecord:
    """검수 기록"""
    reviewer: str                # "auto", "ai", "human"
    status: ReviewStatus
    score: float = 0.0
    feedback: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================
# 포맷 추천
# ============================================================

@dataclass
class FormatScore:
    """포맷 점수"""
    format: NewsFormat
    score: float                 # 0.0 ~ 1.0
    reason: str


@dataclass
class FormatRecommendation:
    """포맷 추천 결과"""
    news_id: str

    # 추천 포맷 (우선순위순)
    recommendations: List[FormatScore] = field(default_factory=list)

    # 분석 정보
    content_length: str = "medium"      # short/medium/long
    visual_richness: float = 0.5        # 시각 자료 활용 가능성
    complexity_level: str = "moderate"  # simple/moderate/complex
    time_sensitivity: str = "daily"     # breaking/daily/evergreen
    target_audience: str = "general"    # general/expert/youth

    # 필수/권장 요소
    required_elements: List[str] = field(default_factory=list)
    optional_elements: List[str] = field(default_factory=list)


# ============================================================
# 생성된 뉴스
# ============================================================

@dataclass
class GeneratedNews:
    """생성된 뉴스"""
    id: str

    # 기본 정보
    format: NewsFormat
    title: str
    subtitle: str = ""
    body: str = ""

    # 구조화된 콘텐츠 (포맷별 다른 구조)
    # STRAIGHT: {lead, paragraphs, closing}
    # CARD_NEWS: {cards: [{title, body, image}]}
    # NEWSLETTER: {greeting, sections, footer}
    structured_content: Dict[str, Any] = field(default_factory=dict)

    # 원본 정보
    source_news_ids: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)

    # 비주얼
    images: List[ImageAsset] = field(default_factory=list)
    charts: List[ChartAsset] = field(default_factory=list)

    # 생성 메타데이터
    generation_mode: GenerationMode = GenerationMode.REWRITE
    model_used: str = "claude"
    prompt_used: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    # 검수 상태
    review_status: ReviewStatus = ReviewStatus.DRAFT
    review_history: List[ReviewRecord] = field(default_factory=list)

    # 통계
    word_count: int = 0
    char_count: int = 0


# ============================================================
# 생성 요청/응답
# ============================================================

@dataclass
class GenerationRequest:
    """뉴스 생성 요청"""
    source_news_ids: List[str]           # 원본 뉴스 ID들
    target_format: NewsFormat            # 목표 포맷
    generation_mode: GenerationMode = GenerationMode.REWRITE

    # 옵션
    max_length: Optional[int] = None     # 최대 길이 오버라이드
    style: str = "neutral"               # 스타일 (neutral/formal/casual)
    language: str = "ko"                 # 언어
    include_citations: bool = True       # 인용 포함 여부
    include_images: bool = False         # 이미지 추천 여부


@dataclass
class GenerationResponse:
    """뉴스 생성 응답"""
    success: bool
    generated_news: Optional[GeneratedNews] = None
    error_message: str = ""
    generation_time_ms: int = 0
    images: List[str] = field(default_factory=list)  # 추출된 이미지 URL
    sources: List[str] = field(default_factory=list)  # 출처 목록
