"""인용 관리자

원본 뉴스의 인용 정보를 관리하고 저작권을 보호합니다.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from news_collector.models.generated_news import Citation, CitationType
from news_collector.models.news import NewsWithScores
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 인용 패턴
# ============================================================

# 직접 인용 패턴 (쌍따옴표로 감싸진 텍스트)
DIRECT_QUOTE_PATTERN = re.compile(r'"([^"]+)"')

# 간접 인용 패턴
INDIRECT_QUOTE_PATTERNS = [
    re.compile(r'(.+?)(?:에 따르면|에 의하면|가 전했다|라고 밝혔다|라고 말했다)'),
    re.compile(r'(.+?)(?:reported|said|according to|stated)', re.IGNORECASE),
]

# 출처 명시 패턴
SOURCE_PATTERNS = [
    re.compile(r'출처:\s*(.+)'),
    re.compile(r'Source:\s*(.+)', re.IGNORECASE),
    re.compile(r'\[(.+?)\]'),
]


class CitationManager:
    """
    인용 관리자.

    생성된 뉴스에서 인용을 추출하고 원본 뉴스와 연결합니다.

    사용법:
        manager = CitationManager()

        # 인용 생성
        citations = manager.create_citations(source_news, generated_text)

        # 인용 삽입
        text_with_citations = manager.insert_citations(text, citations)

        # 출처 포맷팅
        source_text = manager.format_sources(citations)
    """

    def __init__(self):
        self.direct_quote_pattern = DIRECT_QUOTE_PATTERN
        self.indirect_patterns = INDIRECT_QUOTE_PATTERNS
        self.source_patterns = SOURCE_PATTERNS

    def create_citations(
        self,
        source_news: List[NewsWithScores],
        generated_text: str,
    ) -> List[Citation]:
        """
        생성된 텍스트에서 인용 추출 및 생성.

        Args:
            source_news: 원본 뉴스 리스트
            generated_text: 생성된 텍스트

        Returns:
            Citation 리스트
        """
        citations = []
        position = 0

        # 각 원본 뉴스에 대해 인용 확인
        for news in source_news:
            # 직접 인용 찾기
            direct_citations = self._find_direct_quotes(
                news, generated_text, position
            )
            citations.extend(direct_citations)

            # 팩트 인용 생성 (원본 정보 기반)
            fact_citation = self._create_fact_citation(news, position)
            citations.append(fact_citation)

            position += 1

        return citations

    def create_citation(
        self,
        news: NewsWithScores,
        cited_content: str,
        citation_type: CitationType,
        position: int = 0,
        original_text: str = "",
    ) -> Citation:
        """
        단일 인용 생성.

        Args:
            news: 원본 뉴스
            cited_content: 인용된 내용
            citation_type: 인용 유형
            position: 기사 내 위치
            original_text: 원본 텍스트

        Returns:
            Citation 객체
        """
        return Citation(
            source_news_id=news.id,
            source_name=news.source_name,
            source_url=news.url,
            cited_content=cited_content,
            citation_type=citation_type,
            position=position,
            original_text=original_text,
        )

    def _find_direct_quotes(
        self,
        news: NewsWithScores,
        text: str,
        base_position: int,
    ) -> List[Citation]:
        """직접 인용 찾기"""
        citations = []

        # 원본에서 따옴표 내용 추출
        if not news.body:
            return citations

        original_quotes = set(self.direct_quote_pattern.findall(news.body))

        # 생성 텍스트에서 일치하는 인용 찾기
        generated_quotes = self.direct_quote_pattern.findall(text)

        for i, quote in enumerate(generated_quotes):
            # 원본과 유사한 인용인지 확인
            if self._is_similar_quote(quote, original_quotes):
                citations.append(Citation(
                    source_news_id=news.id,
                    source_name=news.source_name,
                    source_url=news.url,
                    cited_content=quote,
                    citation_type=CitationType.DIRECT_QUOTE,
                    position=base_position + i,
                    original_text=quote,
                ))

        return citations

    def _is_similar_quote(self, quote: str, original_quotes: set) -> bool:
        """인용 유사도 확인"""
        quote_lower = quote.lower().strip()

        for original in original_quotes:
            original_lower = original.lower().strip()

            # 정확히 일치
            if quote_lower == original_lower:
                return True

            # 부분 일치 (70% 이상)
            words_quote = set(quote_lower.split())
            words_original = set(original_lower.split())

            if not words_original:
                continue

            overlap = len(words_quote & words_original) / len(words_original)
            if overlap >= 0.7:
                return True

        return False

    def _create_fact_citation(self, news: NewsWithScores, position: int) -> Citation:
        """팩트 인용 생성"""
        return Citation(
            source_news_id=news.id,
            source_name=news.source_name,
            source_url=news.url,
            cited_content=news.title,
            citation_type=CitationType.FACT,
            position=position,
        )

    def insert_citations(
        self,
        text: str,
        citations: List[Citation],
        style: str = "inline",
    ) -> str:
        """
        텍스트에 인용 표시 삽입.

        Args:
            text: 원본 텍스트
            citations: 인용 리스트
            style: 인용 스타일 (inline/footnote/endnote)

        Returns:
            인용이 삽입된 텍스트
        """
        if style == "inline":
            return self._insert_inline_citations(text, citations)
        elif style == "footnote":
            return self._insert_footnote_citations(text, citations)
        else:
            return self._insert_endnote_citations(text, citations)

    def _insert_inline_citations(
        self,
        text: str,
        citations: List[Citation],
    ) -> str:
        """인라인 인용 삽입"""
        # 직접 인용에 출처 추가
        for citation in citations:
            if citation.citation_type == CitationType.DIRECT_QUOTE:
                quoted = f'"{citation.cited_content}"'
                with_source = f'"{citation.cited_content}" ({citation.source_name})'
                text = text.replace(quoted, with_source, 1)

        return text

    def _insert_footnote_citations(
        self,
        text: str,
        citations: List[Citation],
    ) -> str:
        """각주 스타일 인용 삽입"""
        footnotes = []

        for i, citation in enumerate(citations, 1):
            marker = f"[{i}]"

            if citation.citation_type == CitationType.DIRECT_QUOTE:
                quoted = f'"{citation.cited_content}"'
                text = text.replace(quoted, f'{quoted}{marker}', 1)

            footnotes.append(f"{marker} {citation.source_name}")

        if footnotes:
            text += "\n\n---\n" + "\n".join(footnotes)

        return text

    def _insert_endnote_citations(
        self,
        text: str,
        citations: List[Citation],
    ) -> str:
        """미주 스타일 인용 삽입"""
        # 텍스트 끝에 출처 목록 추가
        sources = self.format_sources(citations)
        return f"{text}\n\n---\n출처: {sources}"

    def format_sources(
        self,
        citations: List[Citation],
        include_urls: bool = False,
    ) -> str:
        """
        출처 목록 포맷팅.

        Args:
            citations: 인용 리스트
            include_urls: URL 포함 여부

        Returns:
            포맷팅된 출처 문자열
        """
        # 중복 제거
        seen = set()
        unique_sources = []

        for citation in citations:
            if citation.source_name not in seen:
                seen.add(citation.source_name)
                unique_sources.append(citation)

        if include_urls:
            return ", ".join(
                f"{c.source_name} ({c.source_url})"
                for c in unique_sources
            )
        else:
            return ", ".join(c.source_name for c in unique_sources)

    def validate_citations(
        self,
        generated_text: str,
        citations: List[Citation],
    ) -> Tuple[bool, List[str]]:
        """
        인용 유효성 검사.

        Args:
            generated_text: 생성된 텍스트
            citations: 인용 리스트

        Returns:
            (유효 여부, 문제점 리스트)
        """
        issues = []

        # 직접 인용 검사
        for citation in citations:
            if citation.citation_type == CitationType.DIRECT_QUOTE:
                if citation.cited_content not in generated_text:
                    issues.append(
                        f"인용 '{citation.cited_content[:30]}...'가 텍스트에 없음"
                    )

        # 출처 명시 검사
        if citations:
            has_source_mention = any(
                pattern.search(generated_text)
                for pattern in self.source_patterns
            )
            if not has_source_mention:
                # 출처가 언급되지 않음 (경고만)
                pass

        return len(issues) == 0, issues

    def get_citation_summary(self, citations: List[Citation]) -> Dict[str, int]:
        """
        인용 요약 통계.

        Args:
            citations: 인용 리스트

        Returns:
            유형별 인용 수
        """
        summary = {
            "direct_quote": 0,
            "paraphrase": 0,
            "fact": 0,
            "total": len(citations),
            "unique_sources": len(set(c.source_name for c in citations)),
        }

        for citation in citations:
            if citation.citation_type == CitationType.DIRECT_QUOTE:
                summary["direct_quote"] += 1
            elif citation.citation_type == CitationType.PARAPHRASE:
                summary["paraphrase"] += 1
            elif citation.citation_type == CitationType.FACT:
                summary["fact"] += 1

        return summary
