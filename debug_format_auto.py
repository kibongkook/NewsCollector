"""자동 포맷 선택 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 테슬라로 테스트
news_list = search_news(query='테슬라', limit=3)

generator = NewsGenerator()

print("=" * 100)
print("자동 포맷 선택 테스트 (target_format=None)")
print("=" * 100)

# target_format=None으로 자동 선택
result = generator.generate(
    source_news=news_list,
    target_format=None,  # 자동 선택
    style="neutral",
    enrich_content=True
)

print(f"\n선택된 포맷: {result.generated_news.format if result.generated_news else 'None'}")
print(f"제목: {result.generated_news.title if result.generated_news else 'None'}")
print(f"본문 길이: {len(result.generated_news.body if result.generated_news else '')}자")
print(f"본문 미리보기: {(result.generated_news.body if result.generated_news else '')[:200]}...")

# FormatSelector로 직접 확인
from news_collector.generation.format_selector import FormatSelector
selector = FormatSelector()
recommendation = selector.recommend_from_analysis(news_list[0])

print(f"\nFormatSelector 추천:")
if hasattr(recommendation, 'recommendations') and recommendation.recommendations:
    for i, rec in enumerate(recommendation.recommendations[:3], 1):
        print(f"  [{i}] {rec.format.value}")
        print(f"      reason: {rec.reason if hasattr(rec, 'reason') else 'N/A'}")

print("\n" + "=" * 100)
