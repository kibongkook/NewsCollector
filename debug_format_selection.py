"""포맷 선택 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator
from news_collector.generation.format_selector import FormatSelector

# 테슬라로 테스트
news_list = search_news(query='테슬라', limit=3)

print("=" * 100)
print("포맷 선택 디버깅")
print("=" * 100)

# FormatSelector 테스트
selector = FormatSelector()
recommendation = selector.recommend_from_analysis(news_list[0])

print(f"\n추천된 포맷:")
for i, rec in enumerate(recommendation.recommendations, 1):
    print(f"  [{i}] {rec.format.value} (confidence: {rec.confidence})")
    print(f"      reason: {rec.reason}")

# NewsGenerator에서 선택된 포맷 확인
print(f"\n실제 선택된 포맷:")
generator = NewsGenerator()
result = generator.generate(
    source_news=news_list,
    target_format=None,  # 자동 선택
    style="neutral",
    enrich_content=True
)

print(f"  Format: {result.generated_news.format if result.generated_news else 'None'}")
print(f"  Title: {result.generated_news.title if result.generated_news else 'None'}")
print(f"  Body length: {len(result.generated_news.body if result.generated_news else '')}자")

print("\n" + "=" * 100)
