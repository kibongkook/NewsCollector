"""숫자 추출 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.intelligent_generator import IntelligentNewsGenerator

# 삼성전자로 테스트
news_list = search_news(query='삼성전자', limit=3)

generator = IntelligentNewsGenerator()

print("=" * 100)
print("숫자 추출 디버깅: 삼성전자")
print("=" * 100)

# 팩트 추출
facts = generator.extract_facts(news_list, search_keywords=['삼성전자'])

print(f"\n추출된 숫자:")
for number, category in facts.numbers:
    print(f"  - {number} ({category})")

print(f"\n추출된 엔티티:")
for entity in facts.entities:
    print(f"  - {entity}")

print(f"\n생성된 제목:")
title = generator.generate_title(facts)
print(f"  {title}")

print("\n" + "=" * 100)
