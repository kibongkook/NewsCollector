"""HTML 렌더링 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 테슬라로 테스트
news_list = search_news(query='테슬라', limit=3)

generator = NewsGenerator()

result = generator.generate(
    source_news=news_list,
    target_format=None,
    style="neutral",
    enrich_content=True,
    search_keywords=['테슬라']
)

if result.generated_news:
    print("=" * 100)
    print("생성된 뉴스 데이터")
    print("=" * 100)
    print(f"\n포맷: {result.generated_news.format}")
    print(f"제목: {result.generated_news.title}")
    print(f"\n본문 (첫 500자):")
    print(result.generated_news.body[:500])
    print(f"\n본문 전체 길이: {len(result.generated_news.body)}자")

    print(f"\nstructured_content:")
    if result.generated_news.structured_content:
        for key, value in result.generated_news.structured_content.items():
            print(f"  {key}: {len(value) if value else 0}자")
    else:
        print("  None")

    print(f"\n이미지 개수: {len(result.images) if result.images else 0}개")
    if result.images:
        for i, img in enumerate(result.images, 1):
            print(f"  [{i}] {img[:80]}")

    print("\n" + "=" * 100)
else:
    print("✗ 생성 실패")
