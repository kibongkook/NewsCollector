"""스크래핑 실패 원인 분석"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.content_assembler import ContentAssembler
from news_collector.models.generated_news import NewsFormat

# 테슬라로 테스트
print("=" * 100)
print("스크래핑 실패 원인 분석: 테슬라")
print("=" * 100)

news_list = search_news(query='테슬라', limit=3)

print(f"\n수집된 뉴스:")
for i, news in enumerate(news_list, 1):
    print(f"\n[{i}] {news.title[:60]}")
    print(f"    URL: {news.url}")
    print(f"    Source: {news.source_name}")
    print(f"    본문 길이: {len(news.body or '')}자")
    print(f"    본문: {(news.body or '')[:100]}...")

# ContentAssembler로 스크래핑 시도
print("\n" + "=" * 100)
print("ContentAssembler 스크래핑 테스트")
print("=" * 100)

assembler = ContentAssembler()
assembled = assembler.assemble(
    source_news=news_list,
    format=NewsFormat.STRAIGHT,
    search_keywords=['테슬라'],
    enrich_content=True
)

print(f"\nAssembled 결과:")
print(f"  Primary source: {assembled.primary_source_id}")
print(f"  Lead 길이: {len(assembled.sections.get('lead', ''))}자")
print(f"  Body 길이: {len(assembled.sections.get('body', ''))}자")
print(f"  Lead: {assembled.sections.get('lead', '')[:200]}...")
print(f"  Body: {assembled.sections.get('body', '')[:200]}...")

print("\n" + "=" * 100)
