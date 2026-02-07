"""반복 테스트: 문제 발견 및 개선"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

keywords = ['테슬라', '비트코인', 'AI', '삼성전자']

for keyword in keywords:
    print("=" * 100)
    print(f"테스트 키워드: {keyword}")
    print("=" * 100)

    # 뉴스 수집
    news_list = search_news(query=keyword, limit=3)

    print(f"\n수집된 뉴스 개수: {len(news_list)}")
    for i, news in enumerate(news_list, 1):
        print(f"  [{i}] {news.title[:50]}... - 본문: {len(news.body or '')}자")

    # 뉴스 생성
    generator = NewsGenerator()
    result = generator.generate(
        source_news=news_list,
        target_format=None,
        style="neutral",
        enrich_content=True
    )

    print(f"\n생성 결과:")
    print(f"  제목: {result.generated_news.title if result.generated_news else 'None'}")
    print(f"  본문 길이: {len(result.generated_news.body if result.generated_news else '')}자")
    print(f"  이미지: {len(result.images)}개")

    # 본문 미리보기 (처음 200자)
    if result.generated_news and result.generated_news.body:
        body_preview = result.generated_news.body[:200]
        print(f"  본문 미리보기: {body_preview}...")

        # 문단 개수 확인
        paragraphs = result.generated_news.body.split('\n\n')
        print(f"  문단 개수: {len(paragraphs)}개")

    print()

print("=" * 100)
print("전체 테스트 완료")
print("=" * 100)
