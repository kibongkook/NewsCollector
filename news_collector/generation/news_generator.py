"""뉴스 생성기

Claude API를 사용하여 다양한 포맷의 뉴스를 생성합니다.
"""

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from news_collector.models.generated_news import (
    NewsFormat,
    GenerationMode,
    GeneratedNews,
    Citation,
    CitationType,
    ReviewStatus,
    GenerationRequest,
    GenerationResponse,
    FORMAT_SPECS,
)
from news_collector.models.analyzed_news import EnrichedNews
from news_collector.models.news import NewsWithScores
from news_collector.generation.format_selector import FormatSelector
from news_collector.generation.template_engine import TemplateEngine
from news_collector.generation.prompt_builder import PromptBuilder, GenerationPrompt
from news_collector.generation.citation_manager import CitationManager
from news_collector.generation.content_assembler import ContentAssembler, GenerationConfig
from news_collector.generation.intelligent_generator import IntelligentNewsGenerator
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# 매체명 제거용 패턴 (제목에서 "- 중앙일보", "- 한겨레" 등 제거)
_MEDIA_SUFFIX_PATTERN = re.compile(
    r'\s*[-–—|]\s*(뉴스1|연합뉴스|조선일보|중앙일보|한국일보|경향신문|동아일보|'
    r'매일경제|한국경제|머니투데이|뉴시스|YTN|KBS|MBC|SBS|JTBC|이데일리|'
    r'파이낸셜뉴스|서울신문|세계일보|문화일보|아시아경제|헤럴드경제|디지털타임스|'
    r'전자신문|한겨레|CBS|TV조선|채널A|MBN|아주경제|인포스탁데일리|'
    r'dailian\.co\.kr|imaeil\.com|g-enews\.com|viva100\.com|'
    r'sisajournal-e\.com|joongangenews\.com|mbn\.mk\.co\.kr|'
    r'[a-zA-Z0-9\-]+\.(com|co\.kr|net|org))\s*$'
)

# 제목에서 칼럼/코너 태그 제거 (예: [논썰], [이슈+], [박의명의 실리콘 트래커])
_COLUMN_TAG_PATTERN = re.compile(r'\s*\[[^\]]{2,30}\]\s*')

# 클릭베이트 표현 치환 (예: '이 제품' → 구체적 대체 불가 시 제거)
_CLICKBAIT_PATTERN = re.compile(r"'이\s*제품'|'이\s*기업'|'이\s*종목'|'이\s*것'")


def _clean_title(title: str) -> str:
    """제목에서 매체명, 칼럼 태그, 클릭베이트 표현 제거"""
    if not title:
        return title
    # 1. 매체명 접미사 제거
    title = _MEDIA_SUFFIX_PATTERN.sub('', title)
    # 2. 칼럼/코너 태그 제거
    title = _COLUMN_TAG_PATTERN.sub(' ', title)
    # 3. 클릭베이트 표현 제거
    title = _CLICKBAIT_PATTERN.sub('', title)
    # 4. 정리
    title = re.sub(r'\s{2,}', ' ', title).strip()
    return title


class ClaudeGeneratorClient:
    """Claude API 클라이언트 (뉴스 생성용)"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._client = None

        if self.api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("Claude API 클라이언트 초기화 완료")
            except ImportError:
                logger.warning("anthropic 패키지 미설치. 템플릿 기반 생성만 가능")
            except Exception as e:
                logger.warning("Claude API 초기화 실패: %s", e)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def generate(
        self,
        prompt: GenerationPrompt,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        """뉴스 생성"""
        if not self._client:
            raise RuntimeError("Claude API 사용 불가")

        try:
            message = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                temperature=temperature,
                system=prompt.build_system_prompt(),
                messages=[
                    {"role": "user", "content": prompt.build_user_prompt()}
                ]
            )
            return message.content[0].text.strip()
        except Exception as e:
            logger.error("Claude API 호출 실패: %s", e)
            raise


@dataclass
class FallbackGeneratorResult:
    """폴백 생성기 결과"""
    text: str
    images: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    news_type: str = "standard"  # 뉴스 유형 (standard/visual/data)


class FallbackGenerator:
    """폴백 생성기 (API 없이 템플릿 + ContentAssembler 기반)"""

    def __init__(self):
        self.template_engine = TemplateEngine()
        self.content_assembler = ContentAssembler()
        self.intelligent_generator = IntelligentNewsGenerator()
        self.config = GenerationConfig()

    def _select_best_source(
        self,
        source_news: List[NewsWithScores],
        search_keywords: Optional[List[str]] = None,
    ) -> NewsWithScores:
        """검색 키워드와 가장 관련성 높은 최고 품질 소스 기사 선택.

        합성 제목 대신 원본 기사의 제목을 활용하기 위해,
        키워드 관련성 + 품질 + 신뢰도 + 본문 길이를 종합 평가합니다.
        """
        if not source_news:
            return source_news[0] if source_news else None
        if len(source_news) == 1:
            return source_news[0]

        best = None
        best_score = -1

        for news in source_news:
            score = 0.0
            title = (news.title or "").lower()
            body = (news.body or "").lower()

            # 1. 검색 키워드 매칭 (제목에서 = 가장 중요)
            if search_keywords:
                for kw in search_keywords:
                    kw_lower = kw.lower()
                    if kw_lower in title:
                        score += 50
                    if kw_lower in body[:300]:
                        score += 10

            # 2. 뉴스가치 키워드 보너스 (제목에서)
            newsworthy = [
                '하한가', '상한가', '급등', '급락', '폭락', '폭등',
                '사상최고', '사상최대', '역대최', '최초', '신기록',
                '긴급', '속보', '비상', '파산', '부도', '서킷브레이커',
            ]
            for nw in newsworthy:
                if nw in title:
                    score += 30
                    break

            # 3. 품질/신뢰도 점수
            score += getattr(news, 'quality_score', 0) * 10
            score += getattr(news, 'credibility_score', 0) * 10

            # 4. 본문 길이 (더 상세한 기사 선호, 최대 10점)
            body_len = len(news.body or "")
            score += min(body_len / 100, 10)

            if score > best_score:
                best_score = score
                best = news

        return best or source_news[0]

    def generate(
        self,
        format: NewsFormat,
        source_news: List[NewsWithScores],
        mode: GenerationMode,
        search_keywords: Optional[List[str]] = None,
        enrich_content: bool = True,
    ) -> FallbackGeneratorResult:
        """
        템플릿 기반 뉴스 생성.

        ContentAssembler를 사용하여 다중 뉴스에서 문장을 추출하고,
        중요도순으로 정렬하여 포맷별 구조에 맞게 조립합니다.

        Args:
            format: 목표 포맷
            source_news: 원본 뉴스 리스트
            mode: 생성 모드
            search_keywords: 검색 키워드 (중요도 계산용)
            enrich_content: 본문 확장 활성화 (스크래핑 + 병합)

        Returns:
            FallbackGeneratorResult (텍스트, 이미지, 출처)
        """
        if not source_news:
            return FallbackGeneratorResult(text="")

        # ContentAssembler로 콘텐츠 조립
        assembled = self.content_assembler.assemble(
            source_news=source_news,
            format=format,
            search_keywords=search_keywords,
            enrich_content=enrich_content,
        )

        # 출처 문자열 생성
        sources_str = ", ".join(assembled.sources) if assembled.sources else "뉴스 출처"

        # 최고 품질 소스 기사 선택 (모든 포맷에서 공용)
        best_source = self._select_best_source(source_news, search_keywords)

        # 포맷별 렌더링
        if format == NewsFormat.BRIEF:
            text = self._render_brief(assembled, best_source, search_keywords)

        elif format == NewsFormat.SOCIAL_POST:
            text = self._render_social_post(assembled, best_source, search_keywords)

        elif format == NewsFormat.CARD_NEWS:
            text = self._render_card_news(assembled, best_source, sources_str, search_keywords)

        elif format == NewsFormat.ANALYSIS:
            text = self._render_analysis(assembled, best_source, sources_str, search_keywords)

        elif format == NewsFormat.FEATURE:
            text = self._render_feature(assembled, best_source, sources_str, search_keywords)

        elif format == NewsFormat.NEWSLETTER:
            text = self._render_newsletter(assembled, best_source, search_keywords)

        else:
            # 기본: 스트레이트 뉴스
            text = self._render_straight(assembled, source_news, sources_str, search_keywords)

        return FallbackGeneratorResult(
            text=text,
            images=assembled.images,
            sources=assembled.sources,
            news_type=assembled.news_type,
        )

    def _render_straight(
        self,
        assembled: 'AssembledContent',
        source_news: List['NewsWithScores'],
        sources: str,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """스트레이트 뉴스 렌더링 (최고 품질 원본 제목 + ContentAssembler 본문)"""
        sections = assembled.sections

        # 제목: 최고 품질 소스 기사의 원본 제목 사용 (합성 제목 대신)
        best_source = self._select_best_source(source_news, search_keywords)
        title = _clean_title(best_source.title)

        # 제목이 비어있거나 너무 짧으면 IntelligentNewsGenerator로 폴백
        if not title or len(title) < 5:
            try:
                facts = self.intelligent_generator.extract_facts(source_news, search_keywords)
                title = self.intelligent_generator.generate_title(facts)
            except Exception as e:
                logger.warning(f"제목 생성 폴백 실패: {e}")
                title = _clean_title(source_news[0].title)

        # 본문: ContentAssembler의 풍부한 내용 사용
        return self.template_engine.render_straight(
            title=title,
            lead=sections.get("lead", ""),
            body=sections.get("body", ""),
            closing=sections.get("closing", ""),
            sources=sources,
        )

    def _render_brief(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """속보/간략 뉴스 렌더링 (원본 제목 + 첫 문장)"""
        title = _clean_title(primary_news.title)
        headline = assembled.sections.get("headline", "")
        if not headline and primary_news.body:
            # 본문의 첫 문장 추출
            first_sent = re.split(r'(?<=[.!?])\s+', primary_news.body.strip())
            headline = first_sent[0] if first_sent else primary_news.body[:100]

        return self.template_engine.render_brief(
            title=title,
            content=headline,
        )

    def _render_social_post(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """SNS 포스트 렌더링 (원본 제목 기반)"""
        title = _clean_title(primary_news.title)
        hook = title[:50] if title else primary_news.title[:50]

        sections = assembled.sections
        core = sections.get("core", "")
        if not core:
            # 본문의 첫 문장 활용
            body = primary_news.body or ""
            first_sents = re.split(r'(?<=[.!?])\s+', body.strip())
            core = ' '.join(first_sents[:2])[:150] if first_sents else body[:100]

        hashtags = self._extract_hashtags(primary_news)

        return self.template_engine.render_social_post(
            hook=hook,
            main_content=core,
            hashtags=hashtags,
            cta="자세히 보기 ▶",
        )

    def _render_card_news(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        sources: str,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """카드뉴스 렌더링 (원본 제목 기반)"""
        title = _clean_title(primary_news.title)
        sections = assembled.sections

        # 섹션에서 카드 데이터 추출
        cards = []
        for key, value in sorted(sections.items()):
            if key.startswith("card_"):
                card_num = key.replace("card_", "")
                cards.append({
                    "title": f"Point {card_num}" if card_num != "1" else title[:30],
                    "body": value,
                })

        if not cards:
            cards = self._create_cards(primary_news, search_keywords=search_keywords)

        return self.template_engine.render_card_news(
            title=title,
            cards=cards,
            sources=sources,
        )

    def _render_analysis(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        sources: str,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """분석 기사 렌더링 (원본 제목 기반)"""
        title = _clean_title(primary_news.title)
        sections = assembled.sections

        return self.template_engine.render(NewsFormat.ANALYSIS, {
            "title": title,
            "subtitle": f"[심층 분석] {title[:30]}...",
            "current_situation": sections.get("current_situation", ""),
            "background": sections.get("background", ""),
            "outlook": sections.get("outlook", ""),
            "implications": sections.get("implications", ""),
            "sources": sources,
        })

    def _render_feature(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        sources: str,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """기획 기사 렌더링 (원본 제목 기반)"""
        title = _clean_title(primary_news.title)
        sections = assembled.sections

        return self.template_engine.render(NewsFormat.FEATURE, {
            "title": title,
            "subtitle": "",
            "intro": sections.get("intro", ""),
            "sections": sections.get("main_body", ""),
            "conclusion": sections.get("conclusion", ""),
            "sources": sources,
        })

    def _render_newsletter(
        self,
        assembled: 'AssembledContent',
        primary_news: NewsWithScores,
        search_keywords: Optional[List[str]] = None,
    ) -> str:
        """뉴스레터 렌더링"""
        sections = assembled.sections

        return self.template_engine.render(NewsFormat.NEWSLETTER, {
            "greeting": sections.get("greeting", "오늘의 주요 뉴스입니다."),
            "sections": f"▶ 주요 뉴스\n{sections.get('highlights', '')}\n\n▶ 심층 분석\n{sections.get('deep_dive', '')}",
            "footer": sections.get("closing", "더 자세한 내용은 원문을 확인해주세요."),
        })

    def _extract_hashtags(self, news: NewsWithScores) -> str:
        """해시태그 추출"""
        words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}', news.title)
        # 상위 3개 단어
        return " ".join(f"#{w}" for w in words[:3])

    def _create_cards(self, news: NewsWithScores, max_cards: int = 5, search_keywords: Optional[List[str]] = None) -> List[Dict[str, str]]:
        """카드뉴스용 카드 생성 (원본 제목 + 본문 문장 기반)"""
        title = _clean_title(news.title)
        body = news.body or ""
        sentences = re.split(r'[.!?]\s*', body)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 20]

        cards = [{"title": title[:30], "body": title}]

        for i, sent in enumerate(sentences[:max_cards - 1]):
            cards.append({
                "title": f"Point {i + 1}",
                "body": sent[:150],
            })

        return cards


# AssembledContent 타입 힌트용 임포트
from news_collector.generation.content_assembler import AssembledContent


class NewsGenerator:
    """
    뉴스 생성기.

    분석된 뉴스를 기반으로 다양한 포맷의 새로운 뉴스를 생성합니다.

    사용법:
        generator = NewsGenerator()

        # 단일 뉴스 생성
        result = generator.generate(
            source_news=[news1],
            target_format=NewsFormat.STRAIGHT,
        )

        # 다중 뉴스 통합 생성
        result = generator.generate(
            source_news=[news1, news2, news3],
            target_format=NewsFormat.ANALYSIS,
            mode=GenerationMode.SYNTHESIS,
        )

        if result.success:
            print(result.generated_news.body)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.claude = ClaudeGeneratorClient(api_key)
        self.fallback = FallbackGenerator()
        self.format_selector = FormatSelector()
        self.prompt_builder = PromptBuilder()
        self.citation_manager = CitationManager()
        self.template_engine = TemplateEngine()

    def generate(
        self,
        source_news: List[NewsWithScores],
        target_format: Optional[NewsFormat] = None,
        mode: GenerationMode = GenerationMode.REWRITE,
        style: str = "neutral",
        language: str = "ko",
        max_length: Optional[int] = None,
        include_citations: bool = True,
        enrich_content: bool = True,
        search_keywords: Optional[List[str]] = None,
    ) -> GenerationResponse:
        """
        뉴스 생성.

        Args:
            source_news: 원본 뉴스 리스트
            target_format: 목표 포맷 (None이면 자동 선택)
            mode: 생성 모드
            style: 스타일
            language: 언어
            max_length: 최대 길이
            include_citations: 인용 포함 여부
            enrich_content: 본문 확장 활성화 (스크래핑 + 병합)
            search_keywords: 검색 키워드 (문장 중요도 계산용)

        Returns:
            GenerationResponse 객체
        """
        start_time = time.time()

        if not source_news:
            return GenerationResponse(
                success=False,
                error_message="원본 뉴스가 없습니다.",
            )

        try:
            # 포맷 자동 선택 (컨텐츠 풍부화 전 임시 선택)
            temp_format = target_format
            if temp_format is None:
                recommendation = self.format_selector.recommend_from_analysis(source_news[0])
                if recommendation.recommendations:
                    temp_format = recommendation.recommendations[0].format
                else:
                    temp_format = NewsFormat.STRAIGHT

            # 뉴스 생성
            images: List[str] = []
            sources: List[str] = []

            used_claude = False
            if self.claude.is_available:
                # 프롬프트 생성
                prompt = self.prompt_builder.build(
                    format=temp_format,
                    source_news=source_news,
                    mode=mode,
                    style=style,
                    language=language,
                    max_length=max_length,
                    include_citations=include_citations,
                )
                try:
                    generated_text = self.claude.generate(prompt)
                    sources = list(set(n.source_name for n in source_news if n.source_name))
                    used_claude = True
                    target_format = temp_format
                except Exception as e:
                    logger.warning("Claude API 실패, 템플릿 폴백 전환: %s", e)

            if not used_claude:
                # Fallback 모드: 컨텐츠 풍부화 후 재선택
                if target_format is None and enrich_content:
                    # ContentAssembler로 먼저 컨텐츠 조립 (포맷은 임시로 STRAIGHT 사용)
                    test_assembled = self.fallback.content_assembler.assemble(
                        source_news=source_news,
                        format=NewsFormat.STRAIGHT,
                        search_keywords=search_keywords,
                        enrich_content=True,
                    )

                    # 풍부화된 컨텐츠 길이로 포맷 재선택
                    enriched_length = len(test_assembled.sections.get("body", "")) + len(test_assembled.sections.get("lead", ""))

                    # 임시 NewsWithScores 생성 (풍부화된 길이 반영)
                    enriched_news = NewsWithScores(
                        id=source_news[0].id,
                        title=source_news[0].title,
                        body="x" * enriched_length,  # 길이만 반영
                        source_name=source_news[0].source_name,
                        url=source_news[0].url if source_news[0].url else ""
                    )

                    # 풍부화된 컨텐츠 기반으로 재선택
                    recommendation = self.format_selector.recommend_from_analysis(enriched_news)
                    if recommendation.recommendations:
                        target_format = recommendation.recommendations[0].format
                        logger.info(f"풍부화 후 포맷 재선택: {temp_format} -> {target_format} (길이: {enriched_length}자)")
                    else:
                        target_format = NewsFormat.STRAIGHT
                else:
                    target_format = temp_format

                fallback_result = self.fallback.generate(
                    target_format,
                    source_news,
                    mode,
                    search_keywords=search_keywords,
                    enrich_content=enrich_content,
                )
                generated_text = fallback_result.text
                images = fallback_result.images
                sources = fallback_result.sources

            # 인용 추출
            citations = []
            if include_citations:
                citations = self.citation_manager.create_citations(
                    source_news, generated_text
                )

            # 구조화된 콘텐츠 파싱
            structured_content = self._parse_structured_content(target_format, generated_text)

            # 제목/본문 분리
            title, body = self._extract_title_body(generated_text, source_news[0].title)

            # GeneratedNews 생성
            generated_news = GeneratedNews(
                id=str(uuid.uuid4())[:8],
                format=target_format,
                title=title,
                body=body,
                structured_content=structured_content,
                source_news_ids=[n.id for n in source_news],
                citations=citations,
                generation_mode=mode,
                model_used="claude" if used_claude else "template",
                prompt_used=prompt.build_user_prompt()[:500] if used_claude else "template_fallback",
                word_count=len(body.split()),
                char_count=len(body),
                review_status=ReviewStatus.DRAFT,
            )

            elapsed_ms = int((time.time() - start_time) * 1000)

            return GenerationResponse(
                success=True,
                generated_news=generated_news,
                generation_time_ms=elapsed_ms,
                images=images,
                sources=sources,
            )

        except Exception as e:
            import traceback
            logger.error("뉴스 생성 실패: %s", e)
            logger.error("Stack trace:\n%s", traceback.format_exc())  # Phase 2 디버깅: 상세 에러 출력
            return GenerationResponse(
                success=False,
                error_message=str(e),
                generation_time_ms=int((time.time() - start_time) * 1000),
            )

    def generate_from_enriched(
        self,
        enriched_news: EnrichedNews,
        target_format: Optional[NewsFormat] = None,
        style: str = "neutral",
    ) -> GenerationResponse:
        """
        EnrichedNews에서 뉴스 생성.

        Args:
            enriched_news: 분석된 뉴스
            target_format: 목표 포맷
            style: 스타일

        Returns:
            GenerationResponse 객체
        """
        # 추천 포맷 사용
        if target_format is None and enriched_news.generation_suitability:
            recommended = enriched_news.generation_suitability.recommended_formats
            if recommended:
                target_format = NewsFormat(recommended[0])

        return self.generate(
            source_news=[enriched_news.news],
            target_format=target_format,
            style=style,
        )

    def generate_batch(
        self,
        requests: List[GenerationRequest],
    ) -> List[GenerationResponse]:
        """
        배치 뉴스 생성.

        Args:
            requests: 생성 요청 리스트

        Returns:
            GenerationResponse 리스트
        """
        # 실제로는 source_news_ids로 뉴스를 조회해야 함
        # 여기서는 간단히 빈 응답 반환
        return [
            GenerationResponse(
                success=False,
                error_message="배치 생성은 뉴스 저장소 연동 필요",
            )
            for _ in requests
        ]

    def _parse_structured_content(
        self,
        format: NewsFormat,
        text: str,
    ) -> Dict[str, Any]:
        """구조화된 콘텐츠 파싱"""
        content: Dict[str, Any] = {}

        if format == NewsFormat.STRAIGHT:
            lines = text.split("\n\n")
            content["paragraphs"] = [l.strip() for l in lines if l.strip()]

        elif format == NewsFormat.CARD_NEWS:
            # [1], [2] 등의 카드 구분자 파싱
            cards = []
            card_pattern = re.compile(r'\[(\d+)\]\s*([^\[]+)', re.DOTALL)
            for match in card_pattern.finditer(text):
                cards.append({
                    "number": int(match.group(1)),
                    "content": match.group(2).strip(),
                })
            content["cards"] = cards

        elif format == NewsFormat.QNA:
            # Q., A. 패턴 파싱
            qa_pairs = []
            qa_pattern = re.compile(r'Q\.\s*(.+?)\s*A\.\s*(.+?)(?=Q\.|$)', re.DOTALL)
            for match in qa_pattern.finditer(text):
                qa_pairs.append({
                    "question": match.group(1).strip(),
                    "answer": match.group(2).strip(),
                })
            content["qa_pairs"] = qa_pairs

        elif format == NewsFormat.LISTICLE:
            # 1., 2. 등의 리스트 아이템 파싱
            items = []
            item_pattern = re.compile(r'(\d+)\.\s*(.+?)(?=\d+\.|$)', re.DOTALL)
            for match in item_pattern.finditer(text):
                items.append({
                    "number": int(match.group(1)),
                    "content": match.group(2).strip(),
                })
            content["items"] = items

        return content

    def _extract_title_body(self, text: str, default_title: str) -> tuple:
        """제목과 본문 분리 (매체명/태그 자동 제거)"""
        lines = text.strip().split("\n")

        if not lines:
            return _clean_title(default_title), ""

        # 첫 줄이 제목
        title = _clean_title(lines[0].strip())
        body = "\n".join(lines[1:]).strip()

        # 제목이 너무 길면 기본 제목 사용
        if len(title) > 100:
            return _clean_title(default_title), text

        return title or _clean_title(default_title), body


# 편의 함수
def generate_news(
    source_news: List[NewsWithScores],
    format: Optional[NewsFormat] = None,
    style: str = "neutral",
) -> GenerationResponse:
    """
    뉴스 생성 (편의 함수).

    Args:
        source_news: 원본 뉴스 리스트
        format: 목표 포맷
        style: 스타일

    Returns:
        GenerationResponse 객체
    """
    generator = NewsGenerator()
    return generator.generate(source_news, target_format=format, style=style)
