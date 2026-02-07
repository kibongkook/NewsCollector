"""Phase 2 테스트 - 상세 에러 추적"""
import sys
import traceback

sys.path.insert(0, "d:\\Claude\\NewsCollector")

try:
    from news_collector.generation.news_generator import NewsGenerator

    print("NewsGenerator import 성공")

    # 뉴스 생성 테스트
    generator = NewsGenerator()
    print("NewsGenerator 생성 성공")

    result = generator.generate_from_keyword("테스트")
    print(f"뉴스 생성 성공! 길이: {len(result.sections.get('body', ''))}")

except Exception as e:
    print(f"\n에러 발생: {e}\n")
    print("=" * 80)
    print("전체 트레이스백:")
    print("=" * 80)
    traceback.print_exc()
