"""분석된 뉴스 모델 (스텁)

뉴스 분석 파이프라인의 결과 모델 정의.
Stage 4 (분석 모듈) 구현 전까지 스텁으로 사용됩니다.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from news_collector.models.news import NewsWithScores


# ==============================================================================
# Enums
# ==============================================================================

class SentimentLabel(Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"


class EntityType(Enum):
    PERSON = "PERSON"
    ORG = "ORG"
    LOC = "LOC"
    DATE = "DATE"
    EVENT = "EVENT"
    PRODUCT = "PRODUCT"


class TextComplexity(Enum):
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"


class SummaryType(Enum):
    ABSTRACT = "ABSTRACT"
    EXTRACTIVE = "EXTRACTIVE"


# ==============================================================================
# Data Classes
# ==============================================================================

@dataclass
class SentimentResult:
    label: SentimentLabel = SentimentLabel.NEUTRAL
    score: float = 0.0
    confidence: float = 0.0


@dataclass
class Entity:
    name: str = ""
    text: str = ""
    type: EntityType = EntityType.PERSON
    confidence: float = 0.0


@dataclass
class Keyword:
    word: str = ""
    score: float = 0.0
    frequency: int = 0


@dataclass
class TopicScore:
    topic: str = ""
    confidence: float = 0.0


@dataclass
class AnalyzedNews:
    news_id: str = ""
    sentiment: SentimentResult = field(default_factory=SentimentResult)
    keywords: List[Keyword] = field(default_factory=list)
    topics: List[TopicScore] = field(default_factory=list)
    entities: List[Entity] = field(default_factory=list)
    text_complexity: TextComplexity = TextComplexity.MEDIUM
    word_count: int = 0
    sentence_count: int = 0


@dataclass
class NewsSummary:
    one_line: str = ""
    summary_type: SummaryType = SummaryType.EXTRACTIVE
    text: str = ""


@dataclass
class KeywordTrend:
    keyword: str = ""
    count: int = 0
    trend: str = "stable"


@dataclass
class TopicCluster:
    topic: str = ""
    news_ids: List[str] = field(default_factory=list)


@dataclass
class TimelineEvent:
    date: str = ""
    description: str = ""


@dataclass
class Issue:
    title: str = ""
    description: str = ""
    severity: str = "low"


@dataclass
class TrendReport:
    keywords: List[KeywordTrend] = field(default_factory=list)
    clusters: List[TopicCluster] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)


@dataclass
class GenerationSuitability:
    recommended_formats: List[str] = field(default_factory=list)
    complexity_level: str = "medium"


@dataclass
class TrendContext:
    trend_keywords: List[str] = field(default_factory=list)
    related_topics: List[str] = field(default_factory=list)


@dataclass
class FactCheckResult:
    claim: str = ""
    verdict: str = "unverified"
    confidence: float = 0.0


@dataclass
class EnrichedNews:
    news: NewsWithScores = field(default_factory=lambda: NewsWithScores(
        id="", title="", body="", url="", source_name="",
    ))
    analysis: Optional[AnalyzedNews] = None
    summary: Optional[NewsSummary] = None
    generation_suitability: Optional[GenerationSuitability] = None
