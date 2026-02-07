"""삼성전자 제목 생성 테스트"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 삼성전자로 테스트
news_list = search_news(query='삼성전자', limit=3)

generator = NewsGenerator()

print("=" * 100)
print("삼성전자 제목 생성 테스트")
print("=" * 100)

result = generator.generate(
    source_news=news_list,
    target_format=None,  # 자동 선택
    style="neutral",
    enrich_content=True,
    search_keywords=['삼성전자']
)

if result.generated_news:
    print(f"\n✓ 포맷: {result.generated_news.format.value}")
    print(f"✓ 제목: {result.generated_news.title}")
    print(f"✓ 본문 길이: {len(result.generated_news.body)}자")
    print(f"✓ 본문 미리보기:\n{result.generated_news.body[:300]}...")
else:
    print("\n✗ 생성 실패")

print("\n" + "=" * 100)
