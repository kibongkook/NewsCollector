"""여러 키워드로 포맷 선택 테스트"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

keywords = ['테슬라', '비트코인', 'AI', '삼성전자']

generator = NewsGenerator()

print("=" * 100)
print("자동 포맷 선택 테스트 (enrich_content=True)")
print("=" * 100)

for keyword in keywords:
    print(f"\n[키워드: {keyword}]")
    news_list = search_news(query=keyword, limit=3)

    if not news_list:
        print(f"  ⚠ 뉴스 없음")
        continue

    result = generator.generate(
        source_news=news_list,
        target_format=None,  # 자동 선택
        style="neutral",
        enrich_content=True,
        search_keywords=[keyword]
    )

    if result.generated_news:
        print(f"  ✓ 포맷: {result.generated_news.format.value}")
        print(f"  ✓ 본문 길이: {len(result.generated_news.body)}자")
        print(f"  ✓ 제목: {result.generated_news.title[:60]}...")
    else:
        print(f"  ✗ 생성 실패")

print("\n" + "=" * 100)
