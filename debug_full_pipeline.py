"""전체 파이프라인 추적"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator
from news_collector.models.generated_news import NewsFormat

# 테슬라로 테스트
print("=" * 100)
print("전체 파이프라인 추적: 테슬라")
print("=" * 100)

news_list = search_news(query='테슬라', limit=3)

print(f"\n[Step 1] 수집된 뉴스:")
for i, news in enumerate(news_list, 1):
    print(f"  [{i}] 본문: {len(news.body or '')}자")

# 뉴스 생성
generator = NewsGenerator()

# FallbackGenerator 직접 테스트
print(f"\n[Step 2] FallbackGenerator 테스트:")
fallback_result = generator.fallback.generate(
    NewsFormat.STRAIGHT,
    news_list,
    mode=None,
    search_keywords=['테슬라'],
    enrich_content=True
)

print(f"  Fallback text 길이: {len(fallback_result.text)}자")
print(f"  Fallback text 미리보기: {fallback_result.text[:200]}...")

# 전체 생성
print(f"\n[Step 3] 전체 NewsGenerator:")
result = generator.generate(
    source_news=news_list,
    target_format=None,
    style="neutral",
    enrich_content=True
)

print(f"  Generated title: {result.generated_news.title if result.generated_news else 'None'}")
print(f"  Generated body 길이: {len(result.generated_news.body if result.generated_news else '')}자")
print(f"  Generated body 미리보기: {(result.generated_news.body if result.generated_news else '')[:200]}...")

print("\n" + "=" * 100)
