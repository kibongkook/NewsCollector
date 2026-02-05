"""NewsCollector - Module 1 데모 진입점"""

from news_collector.utils.logger import setup_logging, get_logger
from news_collector.utils.config_manager import ConfigManager
from news_collector.parsers.request_parser import RequestParser


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    logger.info("NewsCollector 시작")

    config = ConfigManager()
    parser = RequestParser(config)

    # 자연어 예시들
    examples = [
        "어제 정치 뉴스 Top 10",
        "2월 1일~5일 동안 AI 관련 뉴스",
        "지난 1주일간 가장 많이 본 과학 뉴스",
        "화제의 경제 뉴스 20개",
    ]

    print("=" * 60)
    print(" NewsCollector Module 1: Request Parser 데모")
    print("=" * 60)

    for text in examples:
        print(f"\n입력: \"{text}\"")
        query = parser.parse(text)
        print(f"  popularity_type: {query.popularity_type}")
        print(f"  date_from: {query.date_from}")
        print(f"  date_to: {query.date_to}")
        print(f"  category: {query.category}")
        print(f"  keywords: {query.keywords}")
        print(f"  limit: {query.limit}")

    # 파라미터 예시
    print(f"\n{'=' * 60}")
    params = {
        "date_from": "2026-02-01",
        "date_to": "2026-02-05",
        "keywords": ["AI", "기술"],
        "category": "경제",
        "limit": 50,
        "sort_by": "quality",
    }
    print(f"파라미터 입력: {params}")
    query = parser.parse(params)
    print(f"  popularity_type: {query.popularity_type}")
    print(f"  date_from: {query.date_from}")
    print(f"  date_to: {query.date_to}")
    print(f"  category: {query.category}")
    print(f"  keywords: {query.keywords}")
    print(f"  limit: {query.limit}")


if __name__ == "__main__":
    main()
