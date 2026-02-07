"""뉴스 생성 과정 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 뉴스 수집
print("=" * 80)
print("1. 뉴스 수집")
print("=" * 80)
news_list = search_news(query='삼성전자', limit=3)

for i, news in enumerate(news_list, 1):
    print(f"\n[뉴스 {i}]")
    print(f"제목: {news.title}")
    print(f"본문 길이: {len(news.body or '')}자")
    print(f"본문: {(news.body or '')[:200]}...")
    print(f"이미지: {len(news.image_urls)}개")

# 뉴스 생성
print("\n" + "=" * 80)
print("2. 뉴스 생성 (enrich_content=True)")
print("=" * 80)

generator = NewsGenerator()
result = generator.generate(
    source_news=news_list,
    target_format=None,
    style="neutral",
    enrich_content=True  # 본문 확장 활성화
)

print(f"\n생성 성공: {result.success}")
print(f"제목: {result.generated_news.title if result.generated_news else 'None'}")
print(f"본문 길이: {len(result.generated_news.body if result.generated_news else '')}자")
print(f"본문:\n{result.generated_news.body if result.generated_news else 'None'}")
print(f"이미지: {len(result.images)}개")

# ContentAssembler 직접 테스트
print("\n" + "=" * 80)
print("3. ContentAssembler 직접 테스트")
print("=" * 80)

from news_collector.generation.content_assembler import ContentAssembler
from news_collector.models.generated_news import NewsFormat

assembler = ContentAssembler()
assembled = assembler.assemble(
    source_news=news_list,
    format=NewsFormat.STRAIGHT,
    search_keywords=['삼성전자'],
    enrich_content=True  # 본문 확장 활성화
)

print(f"\nPrimary source ID: {assembled.primary_source_id}")
print(f"Sections: {list(assembled.sections.keys())}")
print(f"Lead 길이: {len(assembled.sections.get('lead', ''))}자")
print(f"Lead: {assembled.sections.get('lead', '')[:200]}...")
print(f"Body 길이: {len(assembled.sections.get('body', ''))}자")
print(f"Body: {assembled.sections.get('body', '')[:200]}...")
print(f"Images: {len(assembled.images)}개")

print("\n" + "=" * 80)
