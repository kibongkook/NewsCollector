"""뉴스 검색 - Stage 1 통합 파이프라인

지원 기능:
- 특정 키워드 검색
- 특정 날짜/기간 범위 검색
- 다중 소스 수집 (Google News + Naver API)
- 프리셋별 랭킹 (trending, quality, credible, latest)
- 다국어 지원 (한국어, 영어)
"""

import io
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

# Windows 인코딩 문제 해결
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.news import NormalizedNews, NewsWithScores
from news_collector.normalizer.news_normalizer import NewsNormalizer
from news_collector.dedup.dedup_engine import DeduplicationEngine
from news_collector.ranking.ranker import Ranker
from news_collector.ingestion.google_news_connector import fetch_google_news_sync
from news_collector.ingestion.naver_news_connector import fetch_naver_news_sync
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# 알려진 소스 → tier 매핑
KNOWN_SOURCE_TIERS = {
    "대한민국 정책브리핑": "whitelist", "Korea.net": "whitelist",
    "연합뉴스": "tier1", "KBS": "tier1", "KBS 뉴스": "tier1",
    "MBC": "tier1", "SBS": "tier1", "SBS 뉴스": "tier1",
    "조선일보": "tier1", "중앙일보": "tier1", "한겨레": "tier1",
    "동아일보": "tier1", "YTN": "tier1", "JTBC": "tier1",
    "BBC": "tier1", "Reuters": "tier1", "CNN": "tier1",
    "매일경제": "tier2", "한국경제": "tier2", "아시아경제": "tier2",
}


def collect_news(
    keywords: List[str],
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    date_str: Optional[str] = None,
    sources: List[str] = None,
    lang: str = "ko",
    country: str = "KR",
    limit: int = 50,
) -> List[RawNewsRecord]:
    """
    다중 소스에서 뉴스 수집.

    Args:
        keywords: 검색 키워드 리스트
        date_from: 시작 날짜 (datetime)
        date_to: 종료 날짜 (datetime)
        date_str: 단일 날짜 (YYYY-MM-DD, date_from/to 대신 사용)
        sources: 사용할 소스 리스트 ["google", "naver"] (기본: 모두)
        lang: 언어 코드
        country: 국가 코드
        limit: 소스당 최대 결과 수

    Returns:
        수집된 RawNewsRecord 리스트
    """
    if sources is None:
        # 기본: Google (과거 날짜 가능) + Naver (최신만)
        sources = ["google", "naver"] if lang == "ko" else ["google"]

    # 단일 날짜 → 날짜 범위 변환 (해당 날짜만 검색)
    if date_str and not date_from and not date_to:
        target = datetime.strptime(date_str, "%Y-%m-%d")
        date_from = target  # 해당 날짜
        date_to = target    # 해당 날짜

    all_records: List[RawNewsRecord] = []
    seen_urls = set()

    # Google News 수집
    if "google" in sources:
        try:
            google_records = fetch_google_news_sync(
                keywords=keywords,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
                language=lang,
                country=country,
            )
            for r in google_records:
                if r.url not in seen_urls:
                    all_records.append(r)
                    seen_urls.add(r.url)
            logger.info("Google News 수집: %d건", len(google_records))
        except Exception as e:
            logger.error("Google News 수집 실패: %s", e)

    # Naver News API 수집 (한국어 & 최신 뉴스만)
    if "naver" in sources and lang == "ko":
        # Naver API는 과거 날짜 검색 불가 - 최신 뉴스만 수집
        # 과거 날짜 요청 시 건너뜀
        is_recent = True
        if date_from:
            days_ago = (datetime.now() - date_from.replace(tzinfo=None)).days
            is_recent = days_ago <= 7  # 7일 이내만 Naver 사용

        if is_recent:
            try:
                naver_records = fetch_naver_news_sync(
                    keywords=keywords,
                    limit=limit,
                    date_str=date_str,
                )
                for r in naver_records:
                    if r.url not in seen_urls:
                        all_records.append(r)
                        seen_urls.add(r.url)
                logger.info("Naver News 수집: %d건", len(naver_records))
            except Exception as e:
                logger.error("Naver News 수집 실패: %s", e)
        else:
            logger.info("Naver News 건너뜀 (과거 날짜 검색 불가)")

    logger.info("총 수집: %d건 (중복 제거 후)", len(all_records))
    return all_records


def run_pipeline(
    records: List[RawNewsRecord],
    preset: str = "quality",
    limit: int = 5,
    keywords: Optional[List[str]] = None,
    target_date: Optional[datetime] = None,
) -> List[NewsWithScores]:
    """
    전체 파이프라인 실행: 정규화 → 중복 제거 → 랭킹.

    Args:
        records: 원본 뉴스 레코드
        preset: 랭킹 프리셋 (trending, quality, credible, latest)
        limit: 결과 수
        keywords: 검색 키워드 (관련성 점수용)
        target_date: 검색 대상 날짜 (날짜 필터링용)

    Returns:
        랭킹된 뉴스 리스트
    """
    if not records:
        return []

    # 정규화 (날짜 필터링 적용)
    normalizer = NewsNormalizer()
    normalized = normalizer.normalize_batch(
        records,
        target_date=target_date,
        date_tolerance_days=0,  # 정확히 해당 날짜만
    )
    logger.info("정규화: %d건", len(normalized))

    # 중복 제거
    dedup = DeduplicationEngine(similarity_threshold=0.5)
    unique = dedup.deduplicate(normalized)
    logger.info("중복 제거: %d건", len(unique))

    # 랭킹
    ranker = Ranker()
    results = ranker.rank(unique, preset=preset, limit=limit, keywords=keywords)
    logger.info("랭킹 (%s): %d건", preset, len(results))

    return results


def search_news(
    query: str = "",
    date: str = None,
    date_from: str = None,
    date_to: str = None,
    preset: str = "quality",
    limit: int = 5,
    lang: str = "ko",
    country: str = "KR",
    sources: List[str] = None,
) -> List[NewsWithScores]:
    """
    통합 뉴스 검색 함수.

    Args:
        query: 검색 키워드 (공백으로 구분)
        date: 단일 날짜 (YYYY-MM-DD)
        date_from: 시작 날짜 (YYYY-MM-DD)
        date_to: 종료 날짜 (YYYY-MM-DD)
        preset: 랭킹 프리셋 (trending, quality, credible, latest)
        limit: 결과 수
        lang: 언어 코드 (ko, en)
        country: 국가 코드 (KR, US)
        sources: 사용할 소스 ["google", "naver"]

    Returns:
        랭킹된 뉴스 리스트

    사용 예시:
        # 특정 날짜의 인기 뉴스
        results = search_news(query="경제", date="2025-06-15", preset="trending")

        # 기간 범위 검색
        results = search_news(
            query="AI 인공지능",
            date_from="2025-01-01",
            date_to="2025-01-31",
            preset="quality",
        )

        # 최신 뉴스
        results = search_news(query="정치", preset="latest", limit=10)
    """
    keywords = query.split() if query else []

    # 날짜 파싱
    dt_from = None
    dt_to = None
    if date_from:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    if date_to:
        dt_to = datetime.strptime(date_to, "%Y-%m-%d")

    # 수집
    records = collect_news(
        keywords=keywords,
        date_from=dt_from,
        date_to=dt_to,
        date_str=date,
        sources=sources,
        lang=lang,
        country=country,
        limit=50,
    )

    # 단일 날짜 검색 시 날짜 필터링용 target_date 설정
    target_dt = None
    if date and not date_from and not date_to:
        target_dt = datetime.strptime(date, "%Y-%m-%d")

    # 파이프라인 실행
    results = run_pipeline(
        records,
        preset=preset,
        limit=limit,
        keywords=keywords if keywords else None,
        target_date=target_dt,
    )

    return results


def print_results(results: List[NewsWithScores], title: str = "검색 결과"):
    """결과 출력."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

    if not results:
        print("  결과 없음")
        return

    for news in results:
        print(f"\n  [{news.rank_position}위] {news.title}")
        print(f"      출처: {news.source_name}")
        print(f"      점수: {news.final_score}점 "
              f"(신뢰도:{news.credibility_score:.2f} "
              f"품질:{news.quality_score:.2f} "
              f"인기도:{news.popularity_score:.2f})")
        if news.published_at:
            print(f"      발행: {news.published_at.strftime('%Y-%m-%d %H:%M')}")
        if news.url:
            print(f"      URL: {news.url}")

    print(f"\n{'─'*70}")


def main():
    """데모: 다양한 검색 시나리오 테스트."""

    print("\n" + "=" * 70)
    print("  NewsCollector Stage 1 - 통합 뉴스 수집 파이프라인")
    print("=" * 70)

    # 테스트 쿼리들
    queries = [
        {
            "title": "2025년 6월 가장 인기 있는 경제 뉴스 TOP 3",
            "query": "경제",
            "date": "2025-06-15",
            "preset": "trending",
            "limit": 3,
        },
        {
            "title": "2025년 1월 AI 관련 품질 높은 뉴스 TOP 3",
            "query": "AI 인공지능",
            "date_from": "2025-01-01",
            "date_to": "2025-01-31",
            "preset": "quality",
            "limit": 3,
        },
        {
            "title": "2025년 7월 KPOP 핫한 뉴스 TOP 3",
            "query": "KPOP",
            "date": "2025-07-07",
            "preset": "trending",
            "limit": 3,
        },
        {
            "title": "2026년 1월 세계 뉴스 (영어) TOP 3",
            "query": "world news",
            "date": "2026-01-20",
            "preset": "trending",
            "limit": 3,
            "lang": "en",
            "country": "US",
        },
    ]

    for q in queries:
        print(f"\n>>> 검색 중: {q['title']}...")

        results = search_news(
            query=q.get("query", ""),
            date=q.get("date"),
            date_from=q.get("date_from"),
            date_to=q.get("date_to"),
            preset=q.get("preset", "quality"),
            limit=q.get("limit", 3),
            lang=q.get("lang", "ko"),
            country=q.get("country", "KR"),
        )

        print_results(results, q["title"])

    print(f"\n{'='*70}")
    print("  검색 완료!")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
