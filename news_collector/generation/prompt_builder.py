"""프롬프트 빌더

뉴스 생성을 위한 AI 프롬프트를 구성합니다.
포맷별, 스타일별 최적화된 프롬프트를 생성합니다.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from news_collector.models.generated_news import (
    NewsFormat,
    GenerationMode,
    FORMAT_SPECS,
)
from news_collector.models.analyzed_news import (
    EnrichedNews,
    AnalyzedNews,
    NewsSummary,
)
from news_collector.models.news import NewsWithScores
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 시스템 역할 정의
# ============================================================

SYSTEM_ROLES = {
    "neutral": """당신은 경력 20년의 뉴스 편집장입니다.
객관적이고 정확한 기사를 작성하며, 편향 없이 사실만을 전달합니다.
한국어 맞춤법과 문법을 완벽하게 준수합니다.

반드시 지켜야 할 핵심 규칙:
1. 제목은 반드시 새로 작성하세요. 원본 기사의 제목을 그대로 사용하지 마세요.
2. 제목에 언론사 이름(중앙일보, 한겨레, 동아일보 등)을 절대 포함하지 마세요.
3. 제목에 칼럼명/코너명([논썰], [이슈+] 등)을 포함하지 마세요.
4. 원본 문장을 그대로 복사하지 말고, 같은 사실을 다른 문장으로 재작성하세요.
5. 여러 원본 뉴스가 제공되면, 각 뉴스의 핵심 정보를 통합하여 하나의 기사로 만드세요.
6. 오피니언, 칼럼, 논설 내용은 뉴스 기사에 포함하지 마세요. 팩트만 전달하세요.
7. 본문에 출처 매체명을 인라인으로 넣지 마세요 (예: "뉴스1", "연합뉴스" 등).""",

    "formal": """당신은 정치/경제 전문 기자입니다.
격식체를 사용하고 전문 용어를 적절히 활용합니다.
정확한 데이터와 인용을 중시합니다.""",

    "casual": """당신은 MZ세대를 위한 뉴스 콘텐츠 에디터입니다.
친근하고 이해하기 쉬운 표현을 사용합니다.
복잡한 내용도 쉽게 풀어서 설명합니다.""",

    "expert": """당신은 해당 분야의 전문가 칼럼니스트입니다.
깊이 있는 분석과 인사이트를 제공합니다.
전문적이면서도 대중이 이해할 수 있게 작성합니다.""",
}


# ============================================================
# 포맷별 지시사항
# ============================================================

FORMAT_INSTRUCTIONS = {
    NewsFormat.STRAIGHT: """
[스트레이트 뉴스 포맷]
- 육하원칙(누가, 언제, 어디서, 무엇을, 어떻게, 왜)을 준수
- 리드 문단: 가장 중요한 정보를 첫 문단에
- 본문: 중요도 순으로 역피라미드 구조
- 마무리: 향후 전망 또는 관련 정보
- 길이: 400-800자
""",

    NewsFormat.BRIEF: """
[단신 포맷]
- 핵심 정보만 간결하게
- 한 문단으로 완결
- 길이: 100자 이내
""",

    NewsFormat.ANALYSIS: """
[분석 기사 포맷]
- 현황: 현재 상황 설명
- 배경: 역사적/맥락적 배경
- 전망: 향후 예상되는 전개
- 시사점: 독자에게 주는 의미
- 길이: 1500-3000자
""",

    NewsFormat.EXPLAINER: """
[해설 기사 포맷]
- 질문-답변 구조로 구성
- 복잡한 개념을 쉽게 설명
- 핵심 포인트 정리 포함
- 길이: 800-1500자
""",

    NewsFormat.CARD_NEWS: """
[카드뉴스 포맷]
- 5-10장 카드로 구성
- 각 카드: 제목 + 짧은 본문 (30-50자)
- 시각적 표현에 적합한 핵심 내용
- 순서대로 스토리 전개
""",

    NewsFormat.SOCIAL_POST: """
[SNS 포스트 포맷]
- 후킹: 주목을 끄는 첫 문장
- 핵심: 가장 중요한 정보 1-2개
- 해시태그: 관련 키워드 3-5개
- CTA: 행동 유도 문구
- 길이: 280자 이내
""",

    NewsFormat.NEWSLETTER: """
[뉴스레터 포맷]
- 인사말: 독자와의 친근한 소통
- 섹션들: 주요 뉴스 요약 (각 200-300자)
- 마무리: 다음 호 예고 또는 인사
- 길이: 1000-2000자
""",

    NewsFormat.LISTICLE: """
[리스티클 포맷]
- 도입부: 주제 소개
- 항목: 번호 + 제목 + 설명
- 5-10개 항목 권장
- 결론: 요약 또는 추가 정보
- 길이: 1000-2000자
""",

    NewsFormat.QNA: """
[Q&A 포맷]
- 도입부: 주제 배경 설명
- Q&A 쌍: 3-7개
- 질문: 독자가 궁금해할 만한 것
- 답변: 명확하고 간결하게
- 요약: 핵심 내용 정리
""",

    NewsFormat.TIMELINE: """
[타임라인 포맷]
- 시간순으로 주요 이벤트 나열
- 각 이벤트: 날짜 + 사건 설명
- 현재 상황으로 마무리
""",

    NewsFormat.COMPARISON: """
[비교 기사 포맷]
- 비교 대상 A, B 각각 설명
- 공통점과 차이점 분석
- 결론: 종합적 평가
""",

    NewsFormat.FEATURE: """
[기획 기사 포맷]
- 도입부: 주제와 관심 유도
- 여러 섹션으로 깊이 있게 다룸
- 인터뷰, 사례 등 다양한 자료 활용
- 결론: 인사이트 제공
- 길이: 2000-5000자
""",
}


# ============================================================
# 스타일 가이드
# ============================================================

STYLE_GUIDES = {
    "ko": """
[한국어 스타일 가이드]
- 수동태보다 능동태 사용
- 문장 길이: 30-50자 권장
- 외래어는 한글 병기
- 숫자: 만 단위까지 한글, 이상은 숫자
- 인용문은 쌍따옴표(" ") 사용
""",

    "formal": """
[격식체 스타일]
- ~습니다, ~합니다 체 사용
- 존칭 사용
- 전문 용어 적절히 활용
""",

    "casual": """
[비격식체 스타일]
- ~해요, ~이에요 체 사용
- 친근한 표현
- 어려운 용어는 쉽게 풀이
""",
}


# ============================================================
# 프롬프트 데이터 클래스
# ============================================================

@dataclass
class GenerationPrompt:
    """뉴스 생성 프롬프트"""
    # 역할 정의
    system_role: str

    # 포맷 지시
    format_instruction: str

    # 스타일 가이드
    style_guide: str

    # 원본 뉴스 정보
    source_content: str

    # 제약 조건
    constraints: List[str] = field(default_factory=list)

    # 예시 (Few-shot)
    examples: List[str] = field(default_factory=list)

    # 추가 컨텍스트
    additional_context: str = ""

    def build_system_prompt(self) -> str:
        """시스템 프롬프트 생성"""
        return self.system_role

    def build_user_prompt(self) -> str:
        """사용자 프롬프트 생성"""
        parts = []

        # 포맷 지시
        parts.append(self.format_instruction)

        # 스타일 가이드
        parts.append(self.style_guide)

        # 제약 조건
        if self.constraints:
            constraints_text = "\n".join(f"- {c}" for c in self.constraints)
            parts.append(f"\n[제약 조건]\n{constraints_text}")

        # 원본 콘텐츠
        parts.append(f"\n[원본 뉴스]\n{self.source_content}")

        # 추가 컨텍스트
        if self.additional_context:
            parts.append(f"\n[추가 정보]\n{self.additional_context}")

        # 예시
        if self.examples:
            examples_text = "\n---\n".join(self.examples)
            parts.append(f"\n[참고 예시]\n{examples_text}")

        parts.append("\n위 정보를 바탕으로 새로운 뉴스 기사를 작성해주세요.")

        return "\n".join(parts)


# ============================================================
# 프롬프트 빌더
# ============================================================

class PromptBuilder:
    """
    뉴스 생성 프롬프트 빌더.

    뉴스 포맷, 스타일, 원본 정보를 조합하여
    AI 생성에 최적화된 프롬프트를 구성합니다.

    사용법:
        builder = PromptBuilder()

        prompt = builder.build(
            format=NewsFormat.STRAIGHT,
            source_news=[news1, news2],
            mode=GenerationMode.SYNTHESIS,
            style="neutral",
        )

        print(prompt.build_system_prompt())
        print(prompt.build_user_prompt())
    """

    def __init__(self):
        self.system_roles = SYSTEM_ROLES
        self.format_instructions = FORMAT_INSTRUCTIONS
        self.style_guides = STYLE_GUIDES

    def build(
        self,
        format: NewsFormat,
        source_news: List[NewsWithScores],
        mode: GenerationMode = GenerationMode.REWRITE,
        style: str = "neutral",
        language: str = "ko",
        max_length: Optional[int] = None,
        include_citations: bool = True,
        additional_context: str = "",
    ) -> GenerationPrompt:
        """
        프롬프트 생성.

        Args:
            format: 목표 뉴스 포맷
            source_news: 원본 뉴스 리스트
            mode: 생성 모드
            style: 스타일 (neutral/formal/casual/expert)
            language: 언어 (ko/en)
            max_length: 최대 길이 오버라이드
            include_citations: 인용 포함 여부
            additional_context: 추가 컨텍스트

        Returns:
            GenerationPrompt 객체
        """
        # 시스템 역할
        system_role = self.system_roles.get(style, self.system_roles["neutral"])

        # 포맷 지시
        format_instruction = self.format_instructions.get(
            format,
            self.format_instructions[NewsFormat.STRAIGHT]
        )

        # 스타일 가이드
        style_guide = self.style_guides.get(language, self.style_guides["ko"])
        if style in ["formal", "casual"]:
            style_guide += "\n" + self.style_guides.get(style, "")

        # 원본 콘텐츠 구성
        source_content = self._format_source_content(source_news, mode)

        # 제약 조건
        constraints = self._build_constraints(format, mode, max_length, include_citations)

        return GenerationPrompt(
            system_role=system_role,
            format_instruction=format_instruction,
            style_guide=style_guide,
            source_content=source_content,
            constraints=constraints,
            additional_context=additional_context,
        )

    def build_from_enriched(
        self,
        enriched_news: EnrichedNews,
        format: NewsFormat,
        mode: GenerationMode = GenerationMode.REWRITE,
        style: str = "neutral",
    ) -> GenerationPrompt:
        """
        EnrichedNews에서 프롬프트 생성.

        Args:
            enriched_news: 분석된 뉴스
            format: 목표 포맷
            mode: 생성 모드
            style: 스타일

        Returns:
            GenerationPrompt 객체
        """
        # 추가 컨텍스트에 분석 정보 포함
        additional_context = self._format_analysis_context(enriched_news)

        return self.build(
            format=format,
            source_news=[enriched_news.news],
            mode=mode,
            style=style,
            additional_context=additional_context,
        )

    def _format_source_content(
        self,
        source_news: List[NewsWithScores],
        mode: GenerationMode,
    ) -> str:
        """원본 콘텐츠 포맷팅"""
        if mode == GenerationMode.SYNTHESIS:
            # 다중 뉴스 통합
            parts = []
            for i, news in enumerate(source_news, 1):
                parts.append(f"[뉴스 {i}]")
                parts.append(f"제목: {news.title}")
                parts.append(f"출처: {news.source_name}")
                parts.append(f"내용: {news.body}")
                parts.append("")
            return "\n".join(parts)
        else:
            # 단일 뉴스
            news = source_news[0] if source_news else None
            if not news:
                return ""

            return f"""제목: {news.title}
출처: {news.source_name}
발행: {news.published_at.strftime('%Y-%m-%d') if news.published_at else '알 수 없음'}
내용:
{news.body}"""

    def _format_analysis_context(self, enriched_news: EnrichedNews) -> str:
        """분석 컨텍스트 포맷팅"""
        parts = []

        if enriched_news.analysis:
            analysis = enriched_news.analysis

            # 감성
            parts.append(f"감성: {analysis.sentiment.label.value}")

            # 주요 엔티티
            if analysis.entities:
                entities = ", ".join(e.name for e in analysis.entities[:5])
                parts.append(f"주요 인물/조직: {entities}")

            # 주요 키워드
            if analysis.keywords:
                keywords = ", ".join(kw.word for kw in analysis.keywords[:5])
                parts.append(f"핵심 키워드: {keywords}")

            # 토픽
            if analysis.topics:
                parts.append(f"분야: {analysis.topics[0].topic}")

        if enriched_news.summary:
            parts.append(f"핵심 요약: {enriched_news.summary.one_line}")

        return "\n".join(parts)

    def _build_constraints(
        self,
        format: NewsFormat,
        mode: GenerationMode,
        max_length: Optional[int],
        include_citations: bool,
    ) -> List[str]:
        """제약 조건 생성"""
        constraints = []

        # 길이 제약
        spec = FORMAT_SPECS.get(format)
        if max_length:
            constraints.append(f"{max_length}자 이내로 작성")
        elif spec:
            constraints.append(f"{spec.min_length}-{spec.max_length}자 분량")

        # 모드별 제약
        if mode == GenerationMode.SYNTHESIS:
            constraints.append("여러 뉴스의 정보를 통합하여 하나의 완성된 기사로 작성 (단일 소스에만 의존하지 않기)")
        elif mode == GenerationMode.COMPRESSION:
            constraints.append("핵심 정보만 간결하게 압축")
        elif mode == GenerationMode.EXPANSION:
            constraints.append("배경과 맥락을 추가하여 상세하게 확장")

        # 기본 제약
        constraints.append("팩트만 포함, 추측이나 의견/칼럼 내용 배제")
        constraints.append("한국어 맞춤법과 문법 준수")
        constraints.append("제목은 원본 기사 제목을 복사하지 말고 새로 작성 (매체명, 칼럼 태그 포함 금지)")
        constraints.append("원본 문장을 그대로 복사하지 말고 재작성하여 표절 방지")
        constraints.append("본문에 출처 매체명을 인라인으로 삽입하지 않기 (예: '뉴스1', '중앙일보' 등)")

        if include_citations:
            constraints.append("출처는 기사 맨 끝에 별도 표기")

        return constraints


# 편의 함수
def build_prompt(
    format: NewsFormat,
    source_news: List[NewsWithScores],
    style: str = "neutral",
) -> GenerationPrompt:
    """
    프롬프트 생성 (편의 함수).

    Args:
        format: 뉴스 포맷
        source_news: 원본 뉴스 리스트
        style: 스타일

    Returns:
        GenerationPrompt 객체
    """
    builder = PromptBuilder()
    return builder.build(format, source_news, style=style)
