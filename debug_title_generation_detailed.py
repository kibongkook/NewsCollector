"""제목 생성 전체 과정 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.content_assembler import ContentAssembler
from news_collector.generation.intelligent_generator import IntelligentNewsGenerator
from news_collector.models.news import NewsWithScores
from news_collector.models.generated_news import NewsFormat

# 삼성전자로 테스트
news_list = search_news(query='삼성전자', limit=3)

print("=" * 100)
print("제목 생성 전체 과정 디버깅: 삼성전자")
print("=" * 100)

# ContentAssembler로 콘텐츠 조립
assembler = ContentAssembler()
assembled = assembler.assemble(
    source_news=news_list,
    format=NewsFormat.STRAIGHT,
    search_keywords=['삼성전자'],
    enrich_content=True,
)

sections = assembled.sections
combined_text = (sections.get("lead", "") + " " + sections.get("body", ""))[:2000]

print(f"\n[1] ContentAssembler 출력:")
print(f"  Lead 길이: {len(sections.get('lead', ''))}자")
print(f"  Body 길이: {len(sections.get('body', ''))}자")
print(f"  Combined (2000자 제한): {len(combined_text)}자")
print(f"\n  Combined 내용 미리보기:")
print(f"  {combined_text[:500]}...")

# 임시 NewsWithScores 생성
enriched_news = NewsWithScores(
    id="temp",
    title=news_list[0].title,
    body=combined_text,
    source_name=news_list[0].source_name,
    url=news_list[0].url if news_list[0].url else ""
)

# IntelligentNewsGenerator로 팩트 추출
generator = IntelligentNewsGenerator()
facts = generator.extract_facts([enriched_news], search_keywords=['삼성전자'])

print(f"\n[2] Fact Extraction:")
print(f"  Entities: {facts.entities}")
print(f"  Numbers: {facts.numbers}")
print(f"  Dates: {facts.dates}")
print(f"  Actions: {facts.key_actions}")
print(f"  Main topic: {facts.main_topic}")

# 제목 생성
title = generator.generate_title(facts)

print(f"\n[3] 생성된 제목:")
print(f"  {title}")

print("\n" + "=" * 100)
