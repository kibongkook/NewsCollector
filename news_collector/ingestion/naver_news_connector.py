"""Naver News API 커넥터 - 네이버 뉴스 검색 API 통합"""

import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote

from news_collector.ingestion.base_connector import BaseConnector
from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.source import NewsSource, RateLimit
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# 네이버 뉴스 API 정책
# - 일일 호출 제한: 25,000회
# - 최대 결과 수: display 1~100, start 1~1000
# - 응답: title, link, originallink, description, pubDate
# - 본문 전체는 제공하지 않음 (description = 요약 ~100자)
NAVER_API_DAILY_QUOTA = 25000
NAVER_API_MAX_DISPLAY = 100
NAVER_API_MAX_START = 1000
NAVER_API_BASE_URL = "https://openapi.naver.com/v1/search/news.json"


@dataclass
class NaverAPIRateLimiter:
    """Naver API 호출 제한 관리."""

    requests_per_second: float = 5.0  # 안전 마진 (실제: ~10/sec)
    daily_quota: int = NAVER_API_DAILY_QUOTA

    # 상태 추적
    _last_request_time: float = field(default=0.0, repr=False)
    _daily_count: int = field(default=0, repr=False)
    _daily_reset_date: str = field(default="", repr=False)

    def wait_if_needed(self) -> None:
        """레이트 리밋 준수를 위해 대기."""
        # 일일 쿼터 리셋 체크
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_reset_date != today:
            self._daily_reset_date = today
            self._daily_count = 0

        # 일일 쿼터 초과 체크
        if self._daily_count >= self.daily_quota:
            raise RuntimeError(f"Naver API 일일 쿼터 초과: {self.daily_quota}회")

        # 초당 요청 제한
        now = time.time()
        min_interval = 1.0 / self.requests_per_second
        elapsed = now - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self._last_request_time = time.time()
        self._daily_count += 1

    @property
    def remaining_quota(self) -> int:
        """남은 일일 쿼터."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._daily_reset_date != today:
            return self.daily_quota
        return max(0, self.daily_quota - self._daily_count)


class NaverNewsConnector(BaseConnector):
    """
    Naver News API 커넥터.

    특징:
    - 네이버 뉴스 검색 API (v1/search/news) 사용
    - 일일 25,000회 호출 제한 준수
    - HTML 엔티티 디코딩 (제목/설명)
    - 선택적 본문 스크래핑 (trafilatura 사용)
    - 날짜 필터링 지원

    사용법:
        connector = NaverNewsConnector(
            client_id="YOUR_CLIENT_ID",
            client_secret="YOUR_CLIENT_SECRET",
        )
        records = await connector.fetch(keywords=["경제"], limit=20)

    환경변수:
        NAVER_CLIENT_ID: 네이버 개발자 센터 Client ID
        NAVER_CLIENT_SECRET: 네이버 개발자 센터 Client Secret
    """

    def __init__(
        self,
        source: Optional[NewsSource] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        fetch_full_body: bool = False,
        rate_limiter: Optional[NaverAPIRateLimiter] = None,
    ) -> None:
        """
        NaverNewsConnector 초기화.

        Args:
            source: 뉴스 소스 메타데이터 (None이면 기본값 사용)
            client_id: Naver API Client ID (None이면 환경변수 사용)
            client_secret: Naver API Client Secret (None이면 환경변수 사용)
            fetch_full_body: True면 원본 기사 URL에서 본문 스크래핑
            rate_limiter: 레이트 리미터 (None이면 기본 생성)
        """
        if source is None:
            source = NewsSource(
                id="naver_news",
                name="네이버 뉴스",
                ingestion_type="api",
                base_url=NAVER_API_BASE_URL,
                tier="tier1",  # 네이버는 한국 주요 포털
                credibility_base_score=85.0,
                rate_limit=RateLimit(
                    requests_per_minute=300,
                    requests_per_hour=5000,
                    daily_quota=NAVER_API_DAILY_QUOTA,
                ),
            )

        super().__init__(source)

        # API 인증 정보 (환경변수 우선)
        self._client_id = client_id or os.environ.get("NAVER_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("NAVER_CLIENT_SECRET", "")

        if not self._client_id or not self._client_secret:
            logger.warning(
                "Naver API 인증 정보 없음. "
                "환경변수 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 설정 필요."
            )

        self._fetch_full_body = fetch_full_body
        self._rate_limiter = rate_limiter or NaverAPIRateLimiter()

    async def fetch(
        self,
        keywords: Optional[List[str]] = None,
        limit: int = 20,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort: str = "date",  # "sim" (유사도) 또는 "date" (최신순)
    ) -> List[RawNewsRecord]:
        """
        Naver News API에서 뉴스 수집.

        Args:
            keywords: 검색 키워드 리스트
            limit: 최대 결과 수 (1~1000)
            date_from: 시작 날짜 (포함)
            date_to: 종료 날짜 (포함)
            sort: 정렬 방식 ("sim": 유사도, "date": 최신순)

        Returns:
            수집된 RawNewsRecord 리스트
        """
        if not self._client_id or not self._client_secret:
            logger.error("Naver API 인증 정보 없음. 수집 불가.")
            return []

        query = " ".join(keywords) if keywords else "뉴스"
        logger.info("Naver News API 검색 시작: query='%s', limit=%d", query, limit)

        all_records: List[RawNewsRecord] = []
        start = 1
        display = min(NAVER_API_MAX_DISPLAY, limit)

        while len(all_records) < limit and start <= NAVER_API_MAX_START:
            try:
                self._rate_limiter.wait_if_needed()

                records = self._fetch_page(query, display, start, sort)
                if not records:
                    break

                # 날짜 필터링
                for record in records:
                    if len(all_records) >= limit:
                        break

                    pub_date = self._parse_pub_date(record.raw_data.get("pubDate", ""))

                    if date_from and pub_date and pub_date < date_from:
                        continue
                    if date_to and pub_date and pub_date > date_to:
                        continue

                    # 본문 스크래핑 (옵션)
                    if self._fetch_full_body:
                        record = self._enrich_with_full_body(record)

                    all_records.append(record)

                start += display

            except RuntimeError as e:
                logger.error("Naver API 호출 중단: %s", e)
                break
            except Exception as e:
                logger.error("Naver API 수집 오류: %s", e)
                break

        logger.info("Naver News API 수집 완료: %d건", len(all_records))
        return all_records

    def _fetch_page(
        self,
        query: str,
        display: int,
        start: int,
        sort: str,
    ) -> List[RawNewsRecord]:
        """단일 API 페이지 조회."""
        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": sort,
        }
        url = f"{NAVER_API_BASE_URL}?{urlencode(params, quote_via=quote)}"

        headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
            "User-Agent": self.source.user_agent,
        }

        start_time = time.time()
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as resp:
                status = resp.status
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("Naver API 요청 실패: %s", e)
            return []

        elapsed_ms = int((time.time() - start_time) * 1000)

        items = data.get("items", [])
        records: List[RawNewsRecord] = []

        for item in items:
            # HTML 엔티티 디코딩 및 태그 제거
            title = self._clean_html(item.get("title", ""))
            description = self._clean_html(item.get("description", ""))

            # 원본 링크 우선 (네이버 래핑 링크보다 신뢰도 높음)
            original_link = item.get("originallink", "")
            naver_link = item.get("link", "")
            url = original_link or naver_link

            # 소스 이름 추출 (URL 도메인에서)
            source_name = self._extract_source_name(original_link)

            record = RawNewsRecord(
                source_id="naver_news",
                source_name=source_name,
                raw_data={
                    **item,
                    "title": title,  # 정제된 버전
                    "description": description,
                    "source_tier": self._infer_tier(source_name),
                },
                raw_html=item.get("description", ""),
                extracted_text=f"{title} {description}",
                url=url,
                page_language="ko",
                http_status=status,
                response_time_ms=elapsed_ms,
            )
            records.append(record)

        return records

    def _clean_html(self, text: str) -> str:
        """HTML 엔티티 디코딩 및 태그 제거."""
        if not text:
            return ""
        # HTML 엔티티 디코딩
        text = html.unescape(text)
        # HTML 태그 제거
        text = re.sub(r"<[^>]+>", "", text)
        # 연속 공백 정리
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _parse_pub_date(self, pub_date_str: str) -> Optional[datetime]:
        """pubDate 문자열 파싱 (RFC 2822 형식)."""
        if not pub_date_str:
            return None
        try:
            # "Mon, 06 Jan 2025 12:30:00 +0900" 형식
            return parsedate_to_datetime(pub_date_str)
        except Exception:
            return None

    def _extract_source_name(self, url: str) -> str:
        """URL에서 소스 이름 추출."""
        if not url:
            return "네이버 뉴스"

        # 도메인 추출
        match = re.search(r"https?://(?:www\.)?([^/]+)", url)
        if not match:
            return "Unknown"

        domain = match.group(1)

        # 알려진 소스 매핑 (www. 제거된 도메인 사용)
        domain_to_name = {
            "news.yna.co.kr": "연합뉴스",
            "yna.co.kr": "연합뉴스",
            "news.kbs.co.kr": "KBS",
            "imnews.imbc.com": "MBC",
            "news.sbs.co.kr": "SBS",
            "chosun.com": "조선일보",
            "joongang.co.kr": "중앙일보",
            "hani.co.kr": "한겨레",
            "donga.com": "동아일보",
            "mk.co.kr": "매일경제",
            "hankyung.com": "한국경제",
            "ytn.co.kr": "YTN",
            "jtbc.co.kr": "JTBC",
        }

        return domain_to_name.get(domain, domain)

    def _infer_tier(self, source_name: str) -> str:
        """소스 이름으로 신뢰도 tier 추론."""
        tier1_sources = {
            "연합뉴스", "KBS", "MBC", "SBS", "조선일보", "중앙일보",
            "한겨레", "동아일보", "YTN", "JTBC",
        }
        tier2_sources = {
            "매일경제", "한국경제", "뉴시스", "뉴스1", "아시아경제",
        }

        if source_name in tier1_sources:
            return "tier1"
        if source_name in tier2_sources:
            return "tier2"
        return "tier3"

    def _enrich_with_full_body(self, record: RawNewsRecord) -> RawNewsRecord:
        """
        원본 기사 URL에서 본문 전체 스크래핑.

        주의: trafilatura 설치 필요 (pip install trafilatura)
        """
        original_link = record.raw_data.get("originallink", "")
        if not original_link:
            return record

        try:
            # trafilatura 동적 임포트 (선택적 의존성)
            import trafilatura

            # 본문 추출 시도
            downloaded = trafilatura.fetch_url(original_link)
            if downloaded:
                full_body = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                )
                if full_body:
                    # 기존 description 대신 전체 본문 사용
                    title = record.raw_data.get("title", "")
                    record.raw_data["full_body"] = full_body
                    record.extracted_text = f"{title} {full_body}"
                    logger.debug("본문 추출 성공: %s (%d자)", original_link[:50], len(full_body))

        except ImportError:
            logger.warning(
                "trafilatura 미설치. 본문 스크래핑 불가. "
                "설치: pip install trafilatura"
            )
        except Exception as e:
            logger.debug("본문 추출 실패: %s - %s", original_link[:50], e)

        return record

    @property
    def remaining_quota(self) -> int:
        """남은 일일 API 쿼터."""
        return self._rate_limiter.remaining_quota


# 편의 함수: 동기 버전
def fetch_naver_news_sync(
    keywords: List[str],
    limit: int = 20,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    date_str: Optional[str] = None,
    fetch_full_body: bool = False,
) -> List[RawNewsRecord]:
    """
    Naver News API 동기 호출 (async 없이 사용).

    Args:
        keywords: 검색 키워드 리스트
        limit: 최대 결과 수
        client_id: API Client ID (없으면 환경변수)
        client_secret: API Client Secret (없으면 환경변수)
        date_str: 검색 날짜 (YYYY-MM-DD, 해당 날짜 +-1일 범위)
        fetch_full_body: 본문 전체 스크래핑 여부

    Returns:
        RawNewsRecord 리스트
    """
    import asyncio

    connector = NaverNewsConnector(
        client_id=client_id,
        client_secret=client_secret,
        fetch_full_body=fetch_full_body,
    )

    # 날짜 범위 계산
    date_from = None
    date_to = None
    if date_str:
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            date_from = target - timedelta(days=1)
            date_to = target + timedelta(days=1)
        except ValueError:
            pass

    # async 함수 실행
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 이미 이벤트 루프가 있으면 새 태스크 생성
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                connector.fetch(keywords, limit, date_from, date_to)
            )
            return future.result()
    else:
        return asyncio.run(connector.fetch(keywords, limit, date_from, date_to))
