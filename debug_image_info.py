"""ImageInfo 관련 에러 디버그"""
import sys
import traceback

# 경로 추가
sys.path.insert(0, "d:\\Claude\\NewsCollector")

from news_collector.generation.news_generator import NewsGenerator
from news_collector.utils.config_manager import ConfigManager

try:
    config = ConfigManager()
    generator = NewsGenerator(config=config)

    # 간단한 뉴스 생성 테스트
    result = generator.generate_from_keyword("테스트")

    print(f"성공! 이미지 개수: {len(result.images if hasattr(result, 'images') else [])}")
    if hasattr(result, 'images') and result.images:
        print(f"첫 번째 이미지 타입: {type(result.images[0])}")
        print(f"첫 번째 이미지 값: {result.images[0]}")

except Exception as e:
    print(f"에러 발생: {e}")
    print("\n전체 트레이스백:")
    traceback.print_exc()
