"""이미지 관련성 테스트"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.content_assembler import ContentAssembler
from news_collector.models.generated_news import NewsFormat

keywords = ['테슬라', '삼성전자']

assembler = ContentAssembler()

print("=" * 100)
print("이미지 관련성 테스트")
print("=" * 100)

for keyword in keywords:
    print(f"\n[키워드: {keyword}]")
    news_list = search_news(query=keyword, limit=3)

    if not news_list:
        print(f"  ⚠ 뉴스 없음")
        continue

    assembled = assembler.assemble(
        source_news=news_list,
        format=NewsFormat.STRAIGHT,
        search_keywords=[keyword],
        enrich_content=True,
    )

    print(f"\n  수집된 이미지 ({len(assembled.images)}개):")
    for i, img_url in enumerate(assembled.images, 1):
        # URL에서 파일명 추출
        filename = img_url.split('/')[-1] if '/' in img_url else img_url
        print(f"    [{i}] {filename[:80]}")
        print(f"        URL: {img_url[:100]}...")

    print(f"\n  뉴스 제목:")
    for i, news in enumerate(news_list, 1):
        print(f"    [{i}] {news.title}")

print("\n" + "=" * 100)
