"""템플릿 엔진

포맷별 뉴스 템플릿을 관리하고 렌더링합니다.
Jinja2 없이 간단한 문자열 템플릿으로 구현합니다.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import re

from news_collector.models.generated_news import NewsFormat, FORMAT_SPECS
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 템플릿 정의
# ============================================================

# 스트레이트 뉴스 템플릿
STRAIGHT_TEMPLATE = """
{title}

{lead}

{body}

{closing}

---
출처: {sources}
""".strip()

# 단신 템플릿
BRIEF_TEMPLATE = """
[속보] {title}

{content}
""".strip()

# 분석 기사 템플릿
ANALYSIS_TEMPLATE = """
{title}

{subtitle}

■ 현황
{current_situation}

■ 배경
{background}

■ 전망
{outlook}

■ 시사점
{implications}

---
출처: {sources}
""".strip()

# 해설 기사 템플릿
EXPLAINER_TEMPLATE = """
{title}

[Q] {question}

[A] {answer}

■ 핵심 정리
{key_points}

---
출처: {sources}
""".strip()

# 카드뉴스 템플릿
CARD_NEWS_TEMPLATE = """
=== {title} ===

{cards}

---
출처: {sources}
""".strip()

# SNS 포스트 템플릿
SOCIAL_POST_TEMPLATE = """
{hook}

{main_content}

{hashtags}

{cta}
""".strip()

# 뉴스레터 템플릿
NEWSLETTER_TEMPLATE = """
{greeting}

━━━━━━━━━━━━━━━━━━━━━━

{sections}

━━━━━━━━━━━━━━━━━━━━━━

{footer}
""".strip()

# 리스티클 템플릿
LISTICLE_TEMPLATE = """
{title}

{intro}

{items}

{conclusion}

---
출처: {sources}
""".strip()

# Q&A 템플릿
QNA_TEMPLATE = """
{title}

{intro}

{qa_pairs}

■ 요약
{summary}

---
출처: {sources}
""".strip()

# 타임라인 템플릿
TIMELINE_TEMPLATE = """
{title}

[타임라인]

{events}

■ 현재 상황
{current_status}

---
출처: {sources}
""".strip()

# 비교 기사 템플릿
COMPARISON_TEMPLATE = """
{title}

■ {item_a_name}
{item_a_content}

■ {item_b_name}
{item_b_content}

■ 비교 분석
{comparison_analysis}

■ 결론
{conclusion}

---
출처: {sources}
""".strip()

# 피처 기사 템플릿
FEATURE_TEMPLATE = """
{title}

{subtitle}

{intro}

{sections}

{conclusion}

---
출처: {sources}
""".strip()

# 포맷별 템플릿 매핑
TEMPLATES: Dict[NewsFormat, str] = {
    NewsFormat.STRAIGHT: STRAIGHT_TEMPLATE,
    NewsFormat.BRIEF: BRIEF_TEMPLATE,
    NewsFormat.ANALYSIS: ANALYSIS_TEMPLATE,
    NewsFormat.EXPLAINER: EXPLAINER_TEMPLATE,
    NewsFormat.CARD_NEWS: CARD_NEWS_TEMPLATE,
    NewsFormat.SOCIAL_POST: SOCIAL_POST_TEMPLATE,
    NewsFormat.NEWSLETTER: NEWSLETTER_TEMPLATE,
    NewsFormat.LISTICLE: LISTICLE_TEMPLATE,
    NewsFormat.QNA: QNA_TEMPLATE,
    NewsFormat.TIMELINE: TIMELINE_TEMPLATE,
    NewsFormat.COMPARISON: COMPARISON_TEMPLATE,
    NewsFormat.FEATURE: FEATURE_TEMPLATE,
}


class TemplateEngine:
    """
    뉴스 템플릿 엔진.

    포맷별 템플릿을 관리하고 변수를 치환하여 렌더링합니다.

    사용법:
        engine = TemplateEngine()

        # 스트레이트 뉴스 렌더링
        result = engine.render(NewsFormat.STRAIGHT, {
            "title": "제목",
            "lead": "리드 문단",
            "body": "본문",
            "closing": "마무리",
            "sources": "연합뉴스",
        })
    """

    def __init__(self, custom_templates: Optional[Dict[NewsFormat, str]] = None):
        """
        템플릿 엔진 초기화.

        Args:
            custom_templates: 커스텀 템플릿 (기본 템플릿 오버라이드)
        """
        self.templates = TEMPLATES.copy()
        if custom_templates:
            self.templates.update(custom_templates)

    def get_template(self, format: NewsFormat) -> str:
        """
        포맷별 템플릿 반환.

        Args:
            format: 뉴스 포맷

        Returns:
            템플릿 문자열
        """
        return self.templates.get(format, STRAIGHT_TEMPLATE)

    def get_required_fields(self, format: NewsFormat) -> List[str]:
        """
        템플릿에 필요한 필드 목록 반환.

        Args:
            format: 뉴스 포맷

        Returns:
            필드 이름 리스트
        """
        template = self.get_template(format)
        # {field} 패턴 추출
        fields = re.findall(r'\{(\w+)\}', template)
        return list(set(fields))

    def render(
        self,
        format: NewsFormat,
        data: Dict[str, Any],
        strict: bool = False,
    ) -> str:
        """
        템플릿 렌더링.

        Args:
            format: 뉴스 포맷
            data: 템플릿 변수 데이터
            strict: True면 누락된 필드에서 에러 발생

        Returns:
            렌더링된 문자열
        """
        template = self.get_template(format)

        # 누락된 필드 처리
        required = self.get_required_fields(format)
        missing = [f for f in required if f not in data]

        if missing:
            if strict:
                raise ValueError(f"누락된 필드: {missing}")
            else:
                # 빈 문자열로 대체
                for field in missing:
                    data[field] = ""

        # 변수 치환
        result = template
        for key, value in data.items():
            placeholder = "{" + key + "}"
            # 리스트인 경우 처리
            if isinstance(value, list):
                value = self._format_list(value, key)
            result = result.replace(placeholder, str(value))

        # 빈 줄 정리
        result = re.sub(r'\n{3,}', '\n\n', result)

        return result.strip()

    def _format_list(self, items: List[Any], field_name: str) -> str:
        """리스트 포맷팅"""
        if not items:
            return ""

        # 카드 형식
        if field_name == "cards":
            return "\n\n".join(
                f"[{i+1}] {item.get('title', '')}\n{item.get('body', '')}"
                for i, item in enumerate(items)
                if isinstance(item, dict)
            )

        # 아이템 형식 (리스티클)
        if field_name == "items":
            return "\n\n".join(
                f"{i+1}. {item.get('title', '')}\n   {item.get('description', '')}"
                for i, item in enumerate(items)
                if isinstance(item, dict)
            )

        # Q&A 형식
        if field_name == "qa_pairs":
            return "\n\n".join(
                f"Q. {item.get('question', '')}\nA. {item.get('answer', '')}"
                for item in items
                if isinstance(item, dict)
            )

        # 타임라인 이벤트
        if field_name == "events":
            return "\n".join(
                f"• [{item.get('date', '')}] {item.get('event', '')}"
                for item in items
                if isinstance(item, dict)
            )

        # 섹션 형식
        if field_name == "sections":
            return "\n\n".join(
                f"▶ {item.get('title', '')}\n{item.get('content', '')}"
                for item in items
                if isinstance(item, dict)
            )

        # 키 포인트 (불릿 리스트)
        if field_name == "key_points":
            return "\n".join(f"• {item}" for item in items)

        # 기본: 줄바꿈으로 연결
        return "\n".join(str(item) for item in items)

    def render_straight(
        self,
        title: str,
        lead: str,
        body: str,
        closing: str,
        sources: str,
    ) -> str:
        """스트레이트 뉴스 렌더링 헬퍼"""
        return self.render(NewsFormat.STRAIGHT, {
            "title": title,
            "lead": lead,
            "body": body,
            "closing": closing,
            "sources": sources,
        })

    def render_brief(self, title: str, content: str) -> str:
        """단신 렌더링 헬퍼"""
        return self.render(NewsFormat.BRIEF, {
            "title": title,
            "content": content,
        })

    def render_card_news(
        self,
        title: str,
        cards: List[Dict[str, str]],
        sources: str,
    ) -> str:
        """카드뉴스 렌더링 헬퍼"""
        return self.render(NewsFormat.CARD_NEWS, {
            "title": title,
            "cards": cards,
            "sources": sources,
        })

    def render_social_post(
        self,
        hook: str,
        main_content: str,
        hashtags: str = "",
        cta: str = "",
    ) -> str:
        """SNS 포스트 렌더링 헬퍼"""
        return self.render(NewsFormat.SOCIAL_POST, {
            "hook": hook,
            "main_content": main_content,
            "hashtags": hashtags,
            "cta": cta,
        })

    def validate_data(self, format: NewsFormat, data: Dict[str, Any]) -> List[str]:
        """
        데이터 유효성 검사.

        Args:
            format: 뉴스 포맷
            data: 템플릿 변수 데이터

        Returns:
            누락된 필드 리스트 (빈 리스트면 유효)
        """
        required = self.get_required_fields(format)
        return [f for f in required if f not in data or not data[f]]
