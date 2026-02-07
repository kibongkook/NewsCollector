"""IntelligentNewsGenerator 테스트"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from news_collector.generation.intelligent_generator import IntelligentNewsGenerator
from news_collector.models.news import NewsWithScores

# Create test news
test_news = [
    NewsWithScores(
        id='1',
        title='삼성전자, 2분기 영업이익 10조원 돌파',
        body='삼성전자가 2024년 2분기 영업이익 10조5000억원을 기록했다. 전년 동기 대비 50% 증가한 수치다. 메모리 반도체 가격 상승과 스마트폰 판매 호조가 실적 개선에 기여했다.',
        source_name='테스트뉴스',
        url='http://test.com/1'
    ),
    NewsWithScores(
        id='2',
        title='삼성전자 실적 발표, 메모리 부문 강세',
        body='삼성전자는 7월 5일 실적을 발표했다. 메모리 반도체 부문이 전체 영업이익의 70%를 차지했다.',
        source_name='테스트뉴스2',
        url='http://test.com/2'
    )
]

# Generate news
generator = IntelligentNewsGenerator()
result = generator.generate_news(test_news, ['테스트뉴스', '테스트뉴스2'])

print('=' * 80)
print('IntelligentNewsGenerator Test Result')
print('=' * 80)
print()
print('Generated Title:')
print(result['title'])
print()
print('Generated Body:')
print(result['body'])
print()
print('Sources:')
print(result['sources'])
print()
print('=' * 80)
