"""엔티티 추출 디버깅"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from news_collector.generation.intelligent_generator import IntelligentNewsGenerator
from news_collector.models.news import NewsWithScores

# 테슬라 뉴스로 테스트
test_text = """블룸버그에 따르면 테슬라 매립형 도어가 사고 후 작동 불능이 되면서 지난 10년간 10건의 사고에서 최소 15명의 사망자가 나왔다고 한다.
테슬라의 매립형 도어 손잡이를 열지 못해 차량 사고 시 사망하는 사례가 꾸준히 늘고 있다.
현대차는 매립형 도어를 채택했으나, 충돌 감지 시 도어 잠금 해제와 동시에 외부 손잡이가 튀어나오도록 설계됐다는 점에서 테슬라와 다르다."""

test_news = NewsWithScores(
    id="test",
    title="테슬라 손잡이 보기엔 좋지만 불 나면 갇힌다",
    body=test_text,
    source_name="테스트",
    url="http://test.com"
)

generator = IntelligentNewsGenerator()

print("=" * 100)
print("엔티티 추출 디버깅: 테슬라")
print("=" * 100)

# 팩트 추출
facts = generator.extract_facts([test_news])

print(f"\n추출된 팩트:")
print(f"  Main topic: {facts.main_topic}")
print(f"  Entities: {facts.entities}")
print(f"  Numbers: {facts.numbers}")
print(f"  Dates: {facts.dates}")
print(f"  Key actions: {facts.key_actions}")

# 제목 생성
title = generator.generate_title(facts)
print(f"\n생성된 제목: {title}")

# 리드 생성
lead = generator.generate_lead(facts)
print(f"생성된 리드: {lead}")

print("\n" + "=" * 100)
