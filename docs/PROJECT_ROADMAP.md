# NewsCollector 프로젝트 로드맵 v2

## 프로젝트 비전

**"뉴스 수집 → 분석 → 생성 → 검수 → 배포"** 전 과정을 자동화하는 AI 기반 뉴스 파이프라인

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Stage 1    │ → │  Stage 2    │ → │  Stage 3    │ → │  Stage 4    │ → │  Stage 5    │
│  뉴스 수집   │    │  분석/요약   │    │  뉴스 생성   │    │  검수/승인   │    │  배포/관리   │
│  ✅ 완료     │    │  개발 예정   │    │  개발 예정   │    │  개발 예정   │    │  개발 예정   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

---

## Stage 1: 뉴스 수집 파이프라인 ✅ 완료

### 개요
다중 소스에서 뉴스를 수집하고, 정규화/중복제거/랭킹하여 고품질 뉴스를 선별

### 완료된 모듈 (9개)
| 모듈 | 역할 | 상태 |
|------|------|------|
| ingestion | 뉴스 수집 (Google News RSS, Naver API) | ✅ |
| normalizer | RawNewsRecord → NormalizedNews 변환 | ✅ |
| dedup | 중복 제거 (유사도 기반) | ✅ |
| ranking | 프리셋별 랭킹 (trending, quality, credible, latest) | ✅ |
| scoring | 다차원 점수 계산 | ✅ |
| integrity | 무결성 검증, 증거 패턴 분석 | ✅ |
| registry | 뉴스 소스 레지스트리 | ✅ |
| models | 데이터 모델 | ✅ |
| parsers | HTML/RSS 파싱 | ✅ |

### 핵심 기능
- 특정 날짜/기간 뉴스 검색
- 키워드 기반 검색 (동의어 확장)
- 4가지 랭킹 프리셋
- 310개 테스트, 95% 커버리지

### 출력 데이터
```python
@dataclass
class NewsWithScores:
    # 기본 정보
    id: str
    title: str
    body: str
    url: str
    source_name: str
    published_at: datetime

    # 점수
    credibility_score: float
    quality_score: float
    popularity_score: float
    relevance_score: float
    final_score: float
    rank_position: int
```

---

## Stage 2: 뉴스 분석 및 요약

### 목표
수집된 뉴스를 심층 분석하고, AI 기반 요약 및 인사이트 추출

### 2.1 content_analyzer (콘텐츠 분석기)

**역할:** 뉴스 본문 심층 분석

| 기능 | 설명 | 기술 |
|------|------|------|
| 감성 분석 | 긍정/부정/중립 판별 | KoBERT, VADER |
| 엔티티 추출 | 인물, 조직, 장소, 날짜 | spaCy, KoNLPy |
| 키워드 추출 | 핵심 키워드 + TF-IDF | TextRank, YAKE |
| 토픽 분류 | 자동 카테고리 분류 | Zero-shot Classification |
| 팩트/의견 분류 | 사실 vs 의견 문장 구분 | Fine-tuned BERT |

**데이터 모델:**
```python
@dataclass
class AnalyzedNews:
    news_id: str

    # 감성 분석
    sentiment: SentimentResult
    # - score: float (-1.0 ~ 1.0)
    # - label: str (positive/negative/neutral)
    # - confidence: float

    # 엔티티
    entities: List[Entity]
    # - name: str
    # - type: str (PERSON/ORG/LOC/DATE/MONEY)
    # - frequency: int
    # - importance: float

    # 키워드
    keywords: List[Keyword]
    # - word: str
    # - score: float
    # - is_named_entity: bool

    # 토픽/카테고리
    topics: List[TopicScore]
    # - topic: str
    # - confidence: float

    # 팩트 분석
    fact_sentences: List[str]
    opinion_sentences: List[str]
    fact_ratio: float

    # 메타
    readability_score: float  # 가독성
    text_complexity: str      # simple/medium/complex
    analysis_timestamp: datetime
```

### 2.2 summarizer (요약 엔진)

**역할:** 다양한 길이와 스타일의 요약 생성

| 요약 유형 | 길이 | 용도 |
|----------|------|------|
| 헤드라인 | 15자 이내 | 푸시 알림, SNS 타이틀 |
| 한 줄 요약 | 50자 이내 | 뉴스 피드 미리보기 |
| 3줄 요약 | 150자 이내 | 뉴스레터 요약 |
| 단락 요약 | 300자 이내 | 상세 요약 |
| 키포인트 | 3-5개 | 불릿 포인트 형식 |

**기술 스택:**
- **추출적 요약**: TextRank, LexRank
- **생성적 요약**: Claude API, KoBART
- **멀티뉴스 요약**: 클러스터링 + 통합 요약

**데이터 모델:**
```python
@dataclass
class NewsSummary:
    news_id: str

    headline: str           # 15자 헤드라인
    one_line: str           # 50자 한 줄 요약
    brief: str              # 150자 3줄 요약
    detailed: str           # 300자 단락 요약
    key_points: List[str]   # 핵심 포인트 3-5개

    # 메타데이터
    summary_model: str
    extractive_ratio: float  # 추출적 요약 비율
    created_at: datetime
```

### 2.3 trend_tracker (트렌드 추적기)

**역할:** 뉴스 트렌드 및 이슈 추적

| 기능 | 설명 |
|------|------|
| 급상승 키워드 | 시간대별 키워드 빈도 변화 추적 |
| 토픽 클러스터링 | 유사 뉴스 그룹화 |
| 이슈 타임라인 | 특정 이슈의 시간순 전개 |
| 관련 뉴스 연결 | 뉴스 간 관계 그래프 |

**데이터 모델:**
```python
@dataclass
class TrendReport:
    period: str  # daily/weekly/monthly

    rising_keywords: List[KeywordTrend]
    # - keyword: str
    # - growth_rate: float
    # - current_count: int
    # - previous_count: int

    topic_clusters: List[TopicCluster]
    # - cluster_id: str
    # - main_topic: str
    # - news_ids: List[str]
    # - size: int

    hot_issues: List[Issue]
    # - issue_id: str
    # - title: str
    # - related_news: List[str]
    # - timeline: List[TimelineEvent]

    generated_at: datetime
```

### 2.4 fact_checker (팩트 체크)

**역할:** 뉴스 신뢰도 및 사실 검증

| 검증 유형 | 방법 |
|----------|------|
| 교차 검증 | 동일 사건 다중 소스 비교 |
| 인용 확인 | 인용문 원본 출처 추적 |
| 숫자 검증 | 통계/수치 신뢰성 평가 |
| 일관성 검사 | 과거 기사와 모순 체크 |

### Stage 2 출력
```python
@dataclass
class EnrichedNews:
    # Stage 1 데이터
    news: NewsWithScores

    # Stage 2 분석 결과
    analysis: AnalyzedNews
    summary: NewsSummary
    trend_context: Optional[TrendContext]
    fact_check: Optional[FactCheckResult]

    # 생성 적합성 평가
    generation_suitability: GenerationSuitability
    # - recommended_formats: List[NewsFormat]
    # - has_enough_content: bool
    # - visual_potential: float (이미지 활용 가능성)
    # - depth_potential: float (심층 기사 가능성)
```

---

## Stage 3: AI 뉴스 생성

### 목표
분석된 뉴스를 기반으로 다양한 포맷의 새로운 뉴스 콘텐츠 생성

### 3.1 뉴스 포맷 정의

#### 포맷 카테고리

```python
class NewsFormat(Enum):
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
```

#### 포맷별 상세 스펙

| 포맷 | 길이 | 구조 | 이미지 | 용도 |
|------|------|------|--------|------|
| **STRAIGHT** | 400-800자 | 리드+본문+마무리 | 1장 | 일반 뉴스 |
| **BRIEF** | 100자 이내 | 단일 문단 | 없음 | 속보, 단신 |
| **ANALYSIS** | 1500-3000자 | 현황+배경+전망+시사점 | 2-3장 | 심층 보도 |
| **FEATURE** | 2000-5000자 | 인트로+섹션들+결론 | 5장+ | 기획 시리즈 |
| **EXPLAINER** | 800-1500자 | 질문→답변 구조 | 도표 | 복잡한 이슈 해설 |
| **PHOTO_NEWS** | 50-100자/사진 | 사진+캡션 | 3-10장 | 현장 보도 |
| **CARD_NEWS** | 30-50자/카드 | 5-10장 카드 | 매 카드 | SNS 공유용 |
| **INFOGRAPHIC** | 최소화 | 데이터 중심 | 1장(대형) | 통계/비교 |
| **SOCIAL_POST** | 280자 이내 | 후킹+핵심+CTA | 1장 | 트위터/인스타 |
| **NEWSLETTER** | 1000-2000자 | 인사+요약들+마무리 | 섬네일 | 이메일 발송 |
| **LISTICLE** | 1000-2000자 | 번호+항목+설명 | 항목당 1장 | 정보 정리형 |

### 3.2 format_selector (포맷 선택기)

**역할:** 뉴스 특성에 맞는 최적 포맷 추천

```python
@dataclass
class FormatRecommendation:
    news_id: str

    # 추천 포맷 (우선순위순)
    recommendations: List[FormatScore]
    # - format: NewsFormat
    # - score: float (0-1)
    # - reason: str

    # 포맷 선택 근거
    content_length: str          # short/medium/long
    visual_richness: float       # 시각 자료 활용 가능성
    complexity_level: str        # simple/moderate/complex
    time_sensitivity: str        # breaking/daily/evergreen
    target_audience: str         # general/expert/youth

    # 필수/권장 요소
    required_elements: List[str]
    optional_elements: List[str]
```

**선택 로직:**
```python
def recommend_format(enriched_news: EnrichedNews) -> FormatRecommendation:
    scores = {}

    # 1. 콘텐츠 길이 기반
    if enriched_news.analysis.text_complexity == "complex":
        scores[NewsFormat.ANALYSIS] += 0.3
        scores[NewsFormat.EXPLAINER] += 0.3

    # 2. 엔티티 수 기반
    if len(enriched_news.analysis.entities) >= 5:
        scores[NewsFormat.FEATURE] += 0.2

    # 3. 숫자/통계 포함 여부
    if has_statistics(enriched_news):
        scores[NewsFormat.INFOGRAPHIC] += 0.4
        scores[NewsFormat.COMPARISON] += 0.2

    # 4. 시각 자료 가능성
    if enriched_news.generation_suitability.visual_potential > 0.7:
        scores[NewsFormat.PHOTO_NEWS] += 0.3
        scores[NewsFormat.CARD_NEWS] += 0.3

    # 5. 시의성
    if is_breaking_news(enriched_news):
        scores[NewsFormat.STRAIGHT] += 0.5
        scores[NewsFormat.BRIEF] += 0.4

    return FormatRecommendation(
        recommendations=sorted(scores.items(), key=lambda x: -x[1])[:3]
    )
```

### 3.3 template_engine (템플릿 엔진)

**역할:** 포맷별 템플릿 관리 및 렌더링

#### 템플릿 구조
```
templates/
├── straight/
│   ├── default.jinja2
│   ├── breaking.jinja2
│   └── economy.jinja2
├── analysis/
│   ├── default.jinja2
│   ├── political.jinja2
│   └── tech.jinja2
├── photo_news/
│   ├── single_event.jinja2
│   └── collection.jinja2
├── card_news/
│   ├── 5_cards.jinja2
│   ├── 7_cards.jinja2
│   └── 10_cards.jinja2
├── newsletter/
│   ├── daily_morning.jinja2
│   ├── daily_evening.jinja2
│   └── weekly.jinja2
└── social/
    ├── twitter.jinja2
    ├── instagram.jinja2
    └── linkedin.jinja2
```

#### 템플릿 예시 (스트레이트 뉴스)
```jinja2
{# templates/straight/default.jinja2 #}

{{ headline }}

{{ lead_paragraph }}

{% for paragraph in body_paragraphs %}
{{ paragraph }}

{% endfor %}

{% if quote %}
{{ quote.speaker }}은(는) "{{ quote.content }}"라고 말했다.
{% endif %}

{% if background %}
[배경] {{ background }}
{% endif %}

{{ closing_paragraph }}

---
출처: {% for source in sources %}{{ source.name }}{% if not loop.last %}, {% endif %}{% endfor %}
```

### 3.4 news_generator (뉴스 생성기)

**역할:** AI 기반 뉴스 콘텐츠 생성

#### 생성 파이프라인

```
EnrichedNews
    ↓
┌──────────────────┐
│ format_selector  │ → 최적 포맷 선택
└──────────────────┘
    ↓
┌──────────────────┐
│ template_engine  │ → 템플릿 로드
└──────────────────┘
    ↓
┌──────────────────┐
│ prompt_builder   │ → AI 프롬프트 구성
└──────────────────┘
    ↓
┌──────────────────┐
│ ai_generator     │ → Claude/GPT 호출
└──────────────────┘
    ↓
┌──────────────────┐
│ post_processor   │ → 후처리 (포맷팅, 인용 삽입)
└──────────────────┘
    ↓
GeneratedNews (초안)
```

#### 프롬프트 전략

```python
@dataclass
class GenerationPrompt:
    # 역할 정의
    system_role: str
    # "당신은 경력 20년의 뉴스 편집장입니다..."

    # 포맷 지시
    format_instruction: str
    # "다음 포맷으로 기사를 작성하세요: [스트레이트 뉴스]..."

    # 스타일 가이드
    style_guide: str
    # "객관적 어조, 수동태 지양, 짧은 문장..."

    # 원본 뉴스 정보
    source_news: List[NewsSummary]

    # 제약 조건
    constraints: List[str]
    # ["800자 이내", "인용 2회 이상", "팩트만 포함"]

    # 예시 (Few-shot)
    examples: List[str]
```

#### 생성 모드

| 모드 | 설명 | 원본 활용도 |
|------|------|-------------|
| **REWRITE** | 기존 기사 리라이팅 | 1개 기사 → 1개 결과 |
| **SYNTHESIS** | 다중 기사 통합 | N개 기사 → 1개 결과 |
| **EXPANSION** | 기사 확장/심화 | 1개 기사 → 더 긴 결과 |
| **COMPRESSION** | 기사 압축/요약 | 1개 기사 → 더 짧은 결과 |
| **TRANSFORM** | 포맷 변환 | 1개 기사 → 다른 포맷 |

### 3.5 citation_manager (인용 관리)

**역할:** 원본 뉴스 인용 및 저작권 관리

```python
@dataclass
class Citation:
    source_news_id: str
    source_name: str
    source_url: str
    cited_content: str      # 인용된 내용
    citation_type: str      # direct_quote / paraphrase / fact
    position: int           # 기사 내 위치
```

**인용 규칙:**
1. 직접 인용: 원문 그대로 + 출처 명시
2. 패러프레이징: 재작성 + 출처 명시
3. 팩트 인용: 사실 정보 + 출처 링크

### 3.6 visual_generator (비주얼 생성기)

**역할:** 뉴스에 필요한 시각 자료 생성/추천

| 기능 | 설명 |
|------|------|
| 이미지 추천 | Unsplash/Pixabay에서 관련 이미지 검색 |
| 차트 생성 | 데이터 기반 차트 자동 생성 |
| 카드뉴스 레이아웃 | Canva-like 자동 레이아웃 |
| 섬네일 생성 | AI 이미지 생성 (DALL-E, Midjourney) |

### Stage 3 출력

```python
@dataclass
class GeneratedNews:
    id: str

    # 기본 정보
    format: NewsFormat
    title: str
    subtitle: Optional[str]
    body: str

    # 구조화된 콘텐츠 (포맷별)
    structured_content: Dict[str, Any]
    # STRAIGHT: {lead, paragraphs, closing}
    # CARD_NEWS: {cards: [{title, body, image}]}
    # NEWSLETTER: {greeting, sections, footer}

    # 원본 정보
    source_news_ids: List[str]
    citations: List[Citation]

    # 비주얼
    images: List[ImageAsset]
    charts: List[ChartAsset]

    # 메타
    generation_mode: str
    model_used: str
    prompt_used: str
    created_at: datetime

    # 검수 상태
    review_status: ReviewStatus  # draft/pending_review/approved/rejected
    review_history: List[ReviewRecord]
```

---

## Stage 4: 검수 및 승인 (신규)

### 목표
생성된 뉴스가 품질 기준을 충족하고 의도대로 작성되었는지 검증

### 4.1 검수 프로세스 개요

```
GeneratedNews (초안)
    ↓
┌─────────────────────┐
│  1. 자동 품질 검사   │ ← AI 기반 자동 검수
└─────────────────────┘
    ↓ (통과/실패)
┌─────────────────────┐
│  2. 규칙 기반 검사   │ ← 정량적 기준 검사
└─────────────────────┘
    ↓ (통과/실패)
┌─────────────────────┐
│  3. AI 의도 검증     │ ← 생성 의도 vs 결과 비교
└─────────────────────┘
    ↓ (통과/실패)
┌─────────────────────┐
│  4. 사람 검수 (선택) │ ← Human-in-the-loop
└─────────────────────┘
    ↓
GeneratedNews (승인됨) → Stage 5
```

### 4.2 auto_quality_checker (자동 품질 검사)

**역할:** AI 기반 품질 자동 평가

| 검사 항목 | 방법 | 기준 |
|----------|------|------|
| 문법/맞춤법 | py-hanspell, LanguageTool | 오류율 < 1% |
| 가독성 | Flesch-Kincaid (한국어 변형) | 점수 > 60 |
| 문장 길이 | 평균 문장 길이 계산 | 30-50자 |
| 반복 표현 | N-gram 분석 | 반복률 < 5% |
| 금지어 검사 | 블랙리스트 매칭 | 0건 |

```python
@dataclass
class QualityCheckResult:
    news_id: str

    # 문법/맞춤법
    grammar_score: float        # 0-100
    spelling_errors: List[SpellingError]
    grammar_errors: List[GrammarError]

    # 가독성
    readability_score: float    # 0-100
    avg_sentence_length: float
    complex_sentence_ratio: float

    # 스타일
    repetition_score: float     # 낮을수록 좋음
    passive_voice_ratio: float  # 낮을수록 좋음

    # 금지어/민감어
    forbidden_words_found: List[str]
    sensitive_words_found: List[str]

    # 종합
    overall_score: float
    passed: bool
    issues: List[QualityIssue]
```

### 4.3 rule_based_checker (규칙 기반 검사)

**역할:** 정량적/형식적 기준 검증

#### 포맷별 검사 규칙

```python
FORMAT_RULES = {
    NewsFormat.STRAIGHT: {
        "min_length": 400,
        "max_length": 800,
        "required_elements": ["lead", "body", "closing"],
        "min_paragraphs": 3,
        "max_paragraphs": 6,
        "citation_required": True,
    },
    NewsFormat.BRIEF: {
        "min_length": 50,
        "max_length": 100,
        "required_elements": ["body"],
        "max_paragraphs": 1,
    },
    NewsFormat.ANALYSIS: {
        "min_length": 1500,
        "max_length": 3000,
        "required_elements": ["intro", "background", "analysis", "outlook"],
        "min_paragraphs": 8,
        "citation_required": True,
        "min_citations": 2,
    },
    NewsFormat.CARD_NEWS: {
        "min_cards": 5,
        "max_cards": 10,
        "card_text_max": 50,
        "image_required": True,
    },
    # ... 포맷별 규칙 계속
}
```

```python
@dataclass
class RuleCheckResult:
    news_id: str
    format: NewsFormat

    # 길이 검사
    length_check: CheckResult
    # - actual: int
    # - min: int
    # - max: int
    # - passed: bool

    # 구조 검사
    structure_check: CheckResult
    # - required_elements: List[str]
    # - found_elements: List[str]
    # - missing_elements: List[str]
    # - passed: bool

    # 인용 검사
    citation_check: CheckResult
    # - required: bool
    # - min_count: int
    # - actual_count: int
    # - passed: bool

    # 종합
    all_passed: bool
    violations: List[RuleViolation]
```

### 4.4 intent_verifier (의도 검증기)

**역할:** 생성 의도와 결과물 일치 여부 검증

#### 검증 항목

| 항목 | 검증 방법 |
|------|----------|
| 포맷 일치 | 요청 포맷 vs 실제 구조 비교 |
| 톤/어조 | 요청 스타일 vs 실제 텍스트 분석 |
| 핵심 내용 포함 | 원본 키포인트가 결과물에 포함되었는지 |
| 정보 왜곡 | 원본 팩트와 결과물 팩트 비교 |
| 추가 정보 | 원본에 없는 내용이 추가되었는지 |

```python
@dataclass
class IntentVerificationResult:
    news_id: str

    # 포맷 검증
    format_match: float         # 0-1
    format_issues: List[str]

    # 톤/스타일 검증
    tone_match: float           # 0-1
    requested_tone: str
    detected_tone: str

    # 내용 검증
    key_points_coverage: float  # 0-1 (원본 키포인트 포함률)
    missing_key_points: List[str]

    # 정확성 검증
    factual_accuracy: float     # 0-1
    distorted_facts: List[FactDistortion]
    hallucinated_content: List[str]  # 원본에 없는 내용

    # 종합
    intent_alignment_score: float
    passed: bool
    major_issues: List[str]
```

#### AI 기반 의도 검증 프롬프트

```python
INTENT_VERIFICATION_PROMPT = """
당신은 뉴스 품질 검수 전문가입니다.

[원본 뉴스 요약]
{original_summary}

[원본 핵심 포인트]
{key_points}

[생성 요청]
- 포맷: {requested_format}
- 톤: {requested_tone}
- 특별 지시: {special_instructions}

[생성된 결과물]
{generated_content}

다음을 검증해주세요:
1. 요청한 포맷대로 작성되었는가?
2. 원본의 핵심 내용이 모두 포함되었는가?
3. 원본에 없는 내용이 추가되었는가?
4. 팩트가 왜곡되거나 과장되었는가?
5. 요청한 톤/어조가 유지되었는가?

JSON 형식으로 응답:
{
    "format_match": 0.0-1.0,
    "content_coverage": 0.0-1.0,
    "hallucination_detected": true/false,
    "fact_distortion": true/false,
    "tone_match": 0.0-1.0,
    "issues": ["이슈1", "이슈2"],
    "overall_score": 0.0-1.0
}
"""
```

### 4.5 human_review_manager (사람 검수 관리)

**역할:** Human-in-the-loop 검수 프로세스 관리

#### 검수 워크플로우

```
자동 검수 통과
    ↓
┌─────────────────────┐
│ 자동 승인 조건 확인  │
│ - 모든 점수 > 90    │
│ - 중요 이슈 없음     │
└─────────────────────┘
    ↓ Yes              ↓ No
자동 승인          사람 검수 요청
    ↓                  ↓
               ┌─────────────────┐
               │ 검수자 할당     │
               │ (우선순위 기반) │
               └─────────────────┘
                       ↓
               ┌─────────────────┐
               │ 검수 UI 제공    │
               │ - 원본 vs 생성물│
               │ - 자동검수 결과 │
               │ - 수정 도구     │
               └─────────────────┘
                       ↓
               승인 / 수정요청 / 반려
```

#### 검수 결정 옵션

```python
class ReviewDecision(Enum):
    APPROVE = "approve"              # 승인 - 배포 가능
    APPROVE_WITH_EDITS = "approve_with_edits"  # 수정 후 승인
    REQUEST_REGENERATION = "request_regeneration"  # 재생성 요청
    REJECT = "reject"                # 반려 - 사용 불가
```

```python
@dataclass
class HumanReviewRecord:
    news_id: str
    reviewer_id: str

    decision: ReviewDecision

    # 수정 사항
    edits_made: List[Edit]
    # - field: str
    # - original: str
    # - modified: str
    # - reason: str

    # 피드백
    feedback: str
    quality_rating: int  # 1-5

    # 재생성 요청 시
    regeneration_instructions: Optional[str]

    # 메타
    review_time_seconds: int
    reviewed_at: datetime
```

### 4.6 feedback_collector (피드백 수집기)

**역할:** 검수 결과를 바탕으로 생성 품질 개선

```python
@dataclass
class GenerationFeedback:
    # 통계
    total_generated: int
    auto_approved: int
    human_approved: int
    human_edited: int
    rejected: int

    # 공통 이슈
    common_issues: List[IssueFrequency]
    # - issue_type: str
    # - frequency: int
    # - example_cases: List[str]

    # 포맷별 성공률
    format_success_rates: Dict[NewsFormat, float]

    # 개선 제안
    improvement_suggestions: List[str]

    # 프롬프트 튜닝 제안
    prompt_tuning_suggestions: List[PromptTuningSuggestion]
```

### Stage 4 출력

```python
@dataclass
class ApprovedNews:
    # 원본 생성 뉴스
    generated_news: GeneratedNews

    # 검수 결과
    quality_check: QualityCheckResult
    rule_check: RuleCheckResult
    intent_verification: IntentVerificationResult

    # 최종 콘텐츠 (수정 반영됨)
    final_content: FinalContent
    # - title: str
    # - body: str
    # - structured_content: Dict
    # - images: List[ImageAsset]

    # 승인 정보
    approval_type: str  # auto / human
    approval_record: Optional[HumanReviewRecord]

    # 배포 준비 상태
    ready_for_publish: bool
    publish_channels: List[str]  # 적합한 채널 목록
```

---

## Stage 5: 배포 및 관리

### 목표
승인된 뉴스 콘텐츠를 다양한 채널로 배포하고 성과 관리

### 5.1 publisher (배포 엔진)

**지원 채널:**

| 카테고리 | 채널 | 적합 포맷 |
|----------|------|----------|
| **웹** | WordPress, Ghost, Custom CMS | 모든 포맷 |
| **이메일** | Mailchimp, SendGrid, Stibee | Newsletter, Briefing |
| **SNS** | Twitter/X, Facebook, LinkedIn | Social, Brief, Card |
| **이미지 SNS** | Instagram, Pinterest | Photo, Card, Infographic |
| **메신저** | Telegram, Slack, Discord | Brief, Summary |
| **피드** | RSS, Atom | Straight, Analysis |

### 5.2 scheduler (스케줄러)

**배포 스케줄 전략:**
- 채널별 최적 시간대
- 콘텐츠 유형별 빈도
- A/B 테스트 스케줄링

### 5.3 analytics (분석 대시보드)

**핵심 지표:**
- 도달률 / 참여율 / 클릭률
- 채널별 성과 비교
- 포맷별 성과 비교
- 시간대별 성과

### 5.4 feedback_loop (피드백 루프)

**자동 최적화:**
- 고성과 패턴 학습
- 프롬프트 자동 튜닝
- 발행 시간 최적화

### 5.5 admin_dashboard (관리 대시보드)

**기능:**
- 콘텐츠 관리 (CRUD)
- 검수 큐 관리
- 채널 설정
- 사용자 권한
- 시스템 모니터링

---

## 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         NewsCollector Full Pipeline v2                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  Stage 1: 수집                Stage 2: 분석              Stage 3: 생성          │
│  ┌─────────────────┐         ┌─────────────────┐        ┌─────────────────┐    │
│  │ • ingestion     │    →    │ • analyzer      │   →    │ • format_selector│   │
│  │ • normalizer    │         │ • summarizer    │        │ • template_engine│   │
│  │ • dedup         │         │ • trend_tracker │        │ • news_generator │   │
│  │ • scoring       │         │ • fact_checker  │        │ • citation_mgr   │   │
│  │ • ranking       │         │                 │        │ • visual_gen     │   │
│  └─────────────────┘         └─────────────────┘        └─────────────────┘    │
│          ↓                           ↓                          ↓              │
│    NewsWithScores              EnrichedNews               GeneratedNews        │
│                                                                 ↓              │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        Stage 4: 검수/승인                                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │ auto_quality │→│ rule_checker │→│intent_verify │→│ human_review │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │   │
│  │                                ↓                                        │   │
│  │                          ApprovedNews                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      ↓                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                        Stage 5: 배포/관리                                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │   │
│  │  │  scheduler   │→│  publisher   │→│  analytics   │→│feedback_loop │ │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          공통 인프라                                     │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────────────┐ │   │
│  │  │  database  │  │   cache    │  │   queue    │  │  admin_dashboard   │ │   │
│  │  │ PostgreSQL │  │   Redis    │  │   Celery   │  │    FastAPI+React   │ │   │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 개발 일정 (수정)

| 단계 | 기간 | 핵심 마일스톤 |
|------|------|--------------|
| **Stage 2** | 4-6주 | 분석/요약 엔진 완성 |
| **Stage 3** | 6-8주 | 포맷 시스템 + 뉴스 생성기 |
| **Stage 4** | 4-6주 | 자동검수 + 의도검증 + 검수 UI |
| **Stage 5** | 4-6주 | 다중 채널 배포 + 대시보드 |
| **통합/최적화** | 2-4주 | 전체 파이프라인 통합 |
| **총 예상** | **20-30주** | |

---

## 다음 단계

**Stage 2 개발 시작 권장 순서:**
1. `summarizer` 모듈 (Claude API 연동) - 요약 기능 우선
2. `content_analyzer` 모듈 (NLP 분석) - 포맷 선택 기반 데이터
3. `trend_tracker` 모듈 - 뉴스레터용 트렌드 데이터

**Stage 3 핵심 결정 사항:**
1. 어떤 뉴스 포맷부터 지원할 것인가? (추천: STRAIGHT → NEWSLETTER → CARD_NEWS)
2. 어떤 AI 모델을 사용할 것인가? (추천: Claude Sonnet 4 - 비용/성능 균형)
3. 검수 자동화 수준은? (추천: 90점 이상 자동 승인 + 나머지 사람 검수)

준비되면 Stage 2 개발을 시작하겠습니다.
