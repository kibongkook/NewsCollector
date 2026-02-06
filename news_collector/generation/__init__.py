"""Stage 3: AI 뉴스 생성 모듈

이 패키지는 분석된 뉴스를 기반으로 다양한 포맷의 새로운 뉴스 콘텐츠를 생성합니다.

모듈:
    - format_selector: 뉴스 특성에 맞는 최적 포맷 추천
    - template_engine: 포맷별 템플릿 관리 및 렌더링
    - prompt_builder: AI 생성용 프롬프트 구성
    - news_generator: AI 기반 뉴스 콘텐츠 생성
    - citation_manager: 원본 뉴스 인용 및 저작권 관리
    - content_assembler: AI 없이 콘텐츠 조립 (문장 분류, 중요도 평가)
"""

from news_collector.generation.format_selector import FormatSelector, select_format
from news_collector.generation.template_engine import TemplateEngine
from news_collector.generation.prompt_builder import PromptBuilder
from news_collector.generation.news_generator import NewsGenerator, generate_news
from news_collector.generation.citation_manager import CitationManager
from news_collector.generation.content_assembler import (
    ContentAssembler,
    SentenceClassifier,
    GenerationConfig,
    ClassifiedSentence,
    AssembledContent,
)
from news_collector.models.generated_news import (
    NewsFormat,
    GenerationMode,
    GeneratedNews,
    Citation,
)

__all__ = [
    # FormatSelector
    "FormatSelector",
    "select_format",
    # TemplateEngine
    "TemplateEngine",
    # PromptBuilder
    "PromptBuilder",
    # NewsGenerator
    "NewsGenerator",
    "generate_news",
    # CitationManager
    "CitationManager",
    # ContentAssembler
    "ContentAssembler",
    "SentenceClassifier",
    "GenerationConfig",
    "ClassifiedSentence",
    "AssembledContent",
    # Models
    "NewsFormat",
    "GenerationMode",
    "GeneratedNews",
    "Citation",
]
