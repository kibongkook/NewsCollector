"""본문 손실 원인 추적"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator
from news_collector.models.generated_news import NewsFormat

# 테슬라로 테스트
news_list = search_news(query='테슬라', limit=3)

generator = NewsGenerator()

# Step 1: FallbackGenerator 결과
print("=" * 100)
print("Step 1: FallbackGenerator 직접 호출")
print("=" * 100)

fallback_result = generator.fallback.generate(
    NewsFormat.STRAIGHT,
    news_list,
    mode=None,
    search_keywords=['테슬라'],
    enrich_content=True
)

print(f"Fallback text 길이: {len(fallback_result.text)}자")
print(f"Fallback text 첫 500자:\n{fallback_result.text[:500]}\n")

# Step 2: _extract_title_body 테스트
print("=" * 100)
print("Step 2: _extract_title_body 파싱 테스트")
print("=" * 100)

title, body = generator._extract_title_body(fallback_result.text, news_list[0].title)

print(f"Parsed title: {title}")
print(f"Parsed body 길이: {len(body)}자")
print(f"Parsed body 첫 500자:\n{body[:500]}\n")

# Step 3: 전체 generate 호출
print("=" * 100)
print("Step 3: 전체 NewsGenerator.generate() 호출")
print("=" * 100)

result = generator.generate(
    source_news=news_list,
    target_format=NewsFormat.STRAIGHT,  # 명시적으로 STRAIGHT 지정
    style="neutral",
    enrich_content=True
)

print(f"Final title: {result.generated_news.title if result.generated_news else 'None'}")
print(f"Final body 길이: {len(result.generated_news.body if result.generated_news else '')}자")
print(f"Final body:\n{result.generated_news.body if result.generated_news else 'None'}\n")

print("=" * 100)
