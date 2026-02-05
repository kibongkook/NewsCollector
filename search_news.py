"""뉴스 검색 데모 - 전체 파이프라인 실행"""

import asyncio
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.parse import quote
from xml.etree import ElementTree

from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.news import NormalizedNews, NewsWithScores
from news_collector.normalizer.news_normalizer import NewsNormalizer
from news_collector.dedup.dedup_engine import DeduplicationEngine
from news_collector.ranking.ranker import Ranker
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# 알려진 소스 → tier 매핑 (source_name 기반)
KNOWN_SOURCE_TIERS = {
    # whitelist
    "대한민국 정책브리핑": "whitelist",
    "Korea.net": "whitelist",
    # tier1
    "연합뉴스": "tier1", "yna.co.kr": "tier1",
    "KBS": "tier1", "KBS 뉴스": "tier1",
    "MBC": "tier1", "MBC 뉴스": "tier1",
    "SBS": "tier1", "SBS 뉴스": "tier1",
    "조선일보": "tier1", "중앙일보": "tier1",
    "한겨레": "tier1", "동아일보": "tier1",
    "BBC": "tier1", "BBC News": "tier1",
    "Reuters": "tier1", "AP News": "tier1",
    "The New York Times": "tier1",
    "The Washington Post": "tier1",
    "CNN": "tier1",
    # tier2
    "네이트": "tier2", "뉴스펭귄": "tier2",
    "매일경제": "tier2", "한국경제": "tier2",
}


def search_google_news_rss(
    query: str,
    date_str: str,
    lang: str = "ko",
    country: str = "KR",
    max_results: int = 30,
) -> List[RawNewsRecord]:
    """
    Google News RSS를 통해 특정 날짜의 뉴스 검색.

    Args:
        query: 검색어 (빈 문자열이면 전체 뉴스)
        date_str: 날짜 (YYYY-MM-DD)
        lang: 언어 코드
        country: 국가 코드
        max_results: 최대 결과 수
    """
    # 날짜 범위 설정 (하루) - datetime으로 정확한 전후일 계산
    from datetime import timedelta
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    before_date = target_date - timedelta(days=1)
    after_date = target_date + timedelta(days=1)

    # Google News RSS 검색 URL
    search_query = query if query else "뉴스"
    search_query += f" after:{before_date.strftime('%Y-%m-%d')} before:{after_date.strftime('%Y-%m-%d')}"

    encoded_query = quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl={country}&ceid={country}:{lang}"

    logger.info("Google News RSS 검색: %s", url)

    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsCollector/1.0"
        })
        with urlopen(req, timeout=20) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("Google News RSS 검색 실패: %s", e)
        print(f"  [오류] Google News RSS 접속 실패: {e}")
        return []

    # RSS 파싱
    records = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as e:
        logger.error("XML 파싱 실패: %s", e)
        return []

    for item in root.iter("item"):
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        source_el = item.find("source")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        link = link_el.text.strip() if link_el is not None and link_el.text else ""
        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        pub_date = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
        source_name = source_el.text.strip() if source_el is not None and source_el.text else "Unknown"

        # 실제 출처명을 source_id로 사용 (다양성 필터 정확도 향상)
        safe_source_id = re.sub(r'[^a-zA-Z0-9가-힣_]', '_', source_name).lower()

        record = RawNewsRecord(
            source_id=safe_source_id,
            source_name=source_name,
            raw_html=desc,
            raw_data={
                "title": title,
                "description": desc,
                "link": link,
                "pubDate": pub_date,
                "source": source_name,
                "source_tier": KNOWN_SOURCE_TIERS.get(source_name, "tier2"),
            },
            extracted_text=f"{title} {re.sub(r'<[^>]+>', '', desc)}",
            url=link,
            page_language=lang,
            http_status=200,
        )
        records.append(record)

        if len(records) >= max_results:
            break

    logger.info("검색 결과: %d건", len(records))
    return records


def run_pipeline(
    records: List[RawNewsRecord],
    preset: str = "quality",
    limit: int = 3,
) -> List[NewsWithScores]:
    """전체 파이프라인 실행: 정규화 → 중복 제거 → 랭킹."""
    if not records:
        return []

    # Module 4: 정규화
    normalizer = NewsNormalizer()
    normalized = normalizer.normalize_batch(records)
    logger.info("정규화: %d건", len(normalized))

    # Module 5: 중복 제거
    dedup = DeduplicationEngine(similarity_threshold=0.5)
    unique = dedup.deduplicate(normalized)
    logger.info("중복 제거: %d건", len(unique))

    # Module 9: 랭킹 (Module 6/7/8 포함)
    ranker = Ranker()
    results = ranker.rank(unique, preset=preset, limit=limit)
    logger.info("랭킹: %d건 (프리셋: %s)", len(results), preset)

    return results


def print_results(results: List[NewsWithScores], query_title: str):
    """결과 출력."""
    print(f"\n{'='*70}")
    print(f"  {query_title}")
    print(f"{'='*70}")

    if not results:
        print("  결과 없음")
        return

    for news in results:
        source = news.raw_data.get("source", news.source_name) if hasattr(news, "raw_data") else news.source_name
        print(f"\n  [{news.rank_position}위] {news.title}")
        print(f"      출처: {news.source_name}")
        print(f"      점수: {news.final_score}점 (신뢰도:{news.credibility_score:.2f} 품질:{news.quality_score:.2f} 인기도:{news.popularity_score:.2f})")
        if news.published_at:
            print(f"      발행: {news.published_at.strftime('%Y-%m-%d %H:%M')}")
        if news.url:
            print(f"      URL: {news.url}")

    print(f"\n{'─'*70}")


def main():
    """4개 뉴스 검색 쿼리 실행."""

    queries = [
        {
            "title": "2025년 6월 9일 가장 인기 있는 뉴스 TOP 3",
            "query": "",
            "date": "2025-06-09",
            "preset": "trending",
            "limit": 3,
        },
        {
            "title": "2025년 7월 7일 가장 핫했던 KPOP 뉴스 TOP 3",
            "query": "KPOP",
            "date": "2025-07-07",
            "preset": "trending",
            "limit": 3,
        },
        {
            "title": "2025년 12월 10일 깊이 있는 경제 뉴스 TOP 2",
            "query": "경제",
            "date": "2025-12-10",
            "preset": "quality",
            "limit": 2,
        },
        {
            "title": "2026년 1월 13일 세계에서 가장 핫한 뉴스 TOP 3",
            "query": "world news",
            "date": "2026-01-13",
            "preset": "trending",
            "limit": 3,
            "lang": "en",
            "country": "US",
        },
    ]

    print("\n" + "=" * 70)
    print("  NewsCollector - 뉴스 검색 파이프라인 실행")
    print("  Module 1~9 전체 파이프라인 통합 테스트")
    print("=" * 70)

    for q in queries:
        lang = q.get("lang", "ko")
        country = q.get("country", "KR")

        print(f"\n>>> 검색 중: {q['title']}...")

        # 수집
        records = search_google_news_rss(
            query=q["query"],
            date_str=q["date"],
            lang=lang,
            country=country,
        )
        print(f"    수집: {len(records)}건")

        # 파이프라인 실행
        results = run_pipeline(records, preset=q["preset"], limit=q["limit"])

        # 결과 출력
        print_results(results, q["title"])

    print(f"\n{'='*70}")
    print("  검색 완료!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
