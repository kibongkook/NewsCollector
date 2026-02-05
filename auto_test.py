"""자동화 뉴스 검색 품질 검증 시스템

랜덤 쿼리 생성 → 검색 → 파이프라인 실행 → 결과 품질 자동 평가 → 문제 리포트.
하드코딩 없이, 다양한 조건을 자동으로 조합하여 파이프라인의 약점을 찾아냄.
"""

import io
import os
import random
import re
import sys
import time
import traceback

# Windows cp949 인코딩 문제 해결: stdout을 UTF-8로 설정
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.parse import quote
from xml.etree import ElementTree

from news_collector.models.raw_news import RawNewsRecord
from news_collector.models.news import NormalizedNews, NewsWithScores
from news_collector.normalizer.news_normalizer import NewsNormalizer
from news_collector.dedup.dedup_engine import DeduplicationEngine
from news_collector.ranking.ranker import Ranker, RANKING_PRESETS
from news_collector.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────── 쿼리 자동 생성 ───────────────────

# 카테고리별 검색 키워드 풀
KEYWORD_POOL = {
    "정치": ["대통령", "국회", "선거", "정당", "외교", "정치"],
    "경제": ["경제", "주식", "부동산", "환율", "금리", "물가", "GDP"],
    "사회": ["교육", "범죄", "사건", "복지", "인구", "사회"],
    "IT": ["AI", "인공지능", "반도체", "빅데이터", "로봇", "스타트업", "IT"],
    "과학": ["우주", "NASA", "과학", "연구", "바이오", "기후변화"],
    "문화": ["영화", "음악", "전시", "문화", "예술", "공연"],
    "스포츠": ["축구", "야구", "올림픽", "스포츠", "NBA", "FIFA"],
    "국제": ["미국", "중국", "일본", "유럽", "UN", "NATO"],
    "연예": ["KPOP", "아이돌", "드라마", "연예", "BTS"],
    "일반": ["뉴스", "오늘", "속보"],
}

# 영문 키워드 풀
EN_KEYWORD_POOL = {
    "politics": ["election", "president", "congress", "politics", "policy"],
    "economy": ["economy", "stock market", "inflation", "GDP", "trade"],
    "tech": ["AI", "artificial intelligence", "semiconductor", "tech", "startup"],
    "world": ["world news", "UN", "NATO", "climate", "global"],
    "sports": ["FIFA", "NBA", "Olympics", "football", "baseball"],
    "entertainment": ["KPOP", "movie", "Netflix", "music", "celebrity"],
}

PRESETS = list(RANKING_PRESETS.keys())

# 알려진 소스 → tier 매핑
KNOWN_SOURCE_TIERS = {
    "대한민국 정책브리핑": "whitelist", "Korea.net": "whitelist",
    "연합뉴스": "tier1", "yna.co.kr": "tier1",
    "KBS": "tier1", "KBS 뉴스": "tier1",
    "MBC": "tier1", "MBC 뉴스": "tier1",
    "SBS": "tier1", "SBS 뉴스": "tier1",
    "조선일보": "tier1", "중앙일보": "tier1",
    "한겨레": "tier1", "동아일보": "tier1",
    "BBC": "tier1", "BBC News": "tier1",
    "Reuters": "tier1", "AP News": "tier1",
    "The New York Times": "tier1", "The Washington Post": "tier1",
    "CNN": "tier1",
    "네이트": "tier2", "뉴스펭귄": "tier2",
    "매일경제": "tier2", "한국경제": "tier2",
}


def generate_random_query() -> Dict[str, Any]:
    """랜덤 검색 조건 생성 (하드코딩 없이 동적 조합)."""
    # 언어 결정 (70% 한국어, 30% 영어)
    is_korean = random.random() < 0.7
    lang = "ko" if is_korean else "en"
    country = "KR" if is_korean else "US"

    # 카테고리 랜덤 선택
    pool = KEYWORD_POOL if is_korean else EN_KEYWORD_POOL
    category = random.choice(list(pool.keys()))
    keywords = pool[category]

    # 1~2개 키워드 랜덤 조합
    num_keywords = random.randint(1, min(2, len(keywords)))
    selected_keywords = random.sample(keywords, num_keywords)
    query = " ".join(selected_keywords)

    # 날짜 범위: 최근 1~365일 중 랜덤
    days_ago = random.randint(1, 365)
    target_date = datetime.now() - timedelta(days=days_ago)
    date_str = target_date.strftime("%Y-%m-%d")

    # 프리셋 랜덤
    preset = random.choice(PRESETS)

    # 결과 수 랜덤 (2~5)
    limit = random.randint(2, 5)

    return {
        "query": query,
        "date": date_str,
        "lang": lang,
        "country": country,
        "preset": preset,
        "limit": limit,
        "category": category,
        "expected_language": lang,
    }


# ─────────────────── RSS 수집 ───────────────────

def fetch_google_news_rss(
    query: str,
    date_str: str,
    lang: str = "ko",
    country: str = "KR",
    max_results: int = 30,
    retry_wider: bool = True,
) -> List[RawNewsRecord]:
    """Google News RSS 수집. 결과 0건이면 날짜 범위를 넓혀 재시도."""
    records = _fetch_rss_inner(query, date_str, lang, country, max_results)
    if not records and retry_wider:
        # 날짜 범위를 +-3일로 넓혀 재시도
        records = _fetch_rss_inner(query, date_str, lang, country, max_results, date_margin=3)
    return records


def _fetch_rss_inner(
    query: str,
    date_str: str,
    lang: str = "ko",
    country: str = "KR",
    max_results: int = 30,
    date_margin: int = 1,
) -> List[RawNewsRecord]:
    """Google News RSS 수집 내부 함수."""
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    before_date = target_date - timedelta(days=date_margin)
    after_date = target_date + timedelta(days=date_margin)

    search_query = query if query else ("뉴스" if lang == "ko" else "news")
    search_query += f" after:{before_date.strftime('%Y-%m-%d')} before:{after_date.strftime('%Y-%m-%d')}"

    encoded_query = quote(search_query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl={lang}&gl={country}&ceid={country}:{lang}"

    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsCollector/1.0"
        })
        with urlopen(req, timeout=20) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.error("RSS 수집 실패: %s", e)
        return []

    records = []
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
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

    return records


# ─────────────────── 파이프라인 실행 ───────────────────

def run_pipeline(
    records: List[RawNewsRecord],
    preset: str = "quality",
    limit: int = 3,
    keywords: Optional[List[str]] = None,
) -> List[NewsWithScores]:
    """정규화 → 중복 제거 → 랭킹."""
    if not records:
        return []

    normalizer = NewsNormalizer()
    normalized = normalizer.normalize_batch(records)

    dedup = DeduplicationEngine(similarity_threshold=0.5)
    unique = dedup.deduplicate(normalized)

    ranker = Ranker()
    results = ranker.rank(unique, preset=preset, limit=limit, keywords=keywords)

    return results


# ─────────────────── 품질 검증 엔진 ───────────────────

class QualityValidator:
    """검색 결과의 품질을 다차원으로 평가하고 문제점을 발견."""

    def validate(
        self,
        query: Dict[str, Any],
        raw_records: List[RawNewsRecord],
        results: List[NewsWithScores],
    ) -> Dict[str, Any]:
        """
        결과 품질 평가.

        Returns:
            {
                "passed": bool,
                "score": float (0~100),
                "issues": [{"severity": str, "check": str, "detail": str}],
                "metrics": {...}
            }
        """
        issues = []
        metrics = {}

        # 1. 수집 성공률
        metrics["raw_count"] = len(raw_records)
        metrics["result_count"] = len(results)
        if len(raw_records) == 0:
            issues.append({
                "severity": "CRITICAL",
                "check": "collection_empty",
                "detail": f"쿼리 '{query['query']}' (날짜: {query['date']})에서 수집 결과 0건",
            })
        elif len(results) == 0 and len(raw_records) > 0:
            issues.append({
                "severity": "HIGH",
                "check": "pipeline_empty",
                "detail": f"수집 {len(raw_records)}건이지만 파이프라인 결과 0건 (전부 필터링됨)",
            })

        if not results:
            return {"passed": False, "score": 0, "issues": issues, "metrics": metrics}

        # 2. 결과 수 검증
        if len(results) < query["limit"] and len(raw_records) >= query["limit"]:
            issues.append({
                "severity": "MEDIUM",
                "check": "insufficient_results",
                "detail": f"요청 {query['limit']}건 중 {len(results)}건만 반환 (과도한 필터링?)",
            })

        # 3. 점수 분포 검증
        scores = [r.final_score for r in results]
        metrics["avg_score"] = round(sum(scores) / len(scores), 1)
        metrics["min_score"] = round(min(scores), 1)
        metrics["max_score"] = round(max(scores), 1)
        metrics["score_range"] = round(max(scores) - min(scores), 1)

        if metrics["avg_score"] < 30:
            issues.append({
                "severity": "HIGH",
                "check": "low_avg_score",
                "detail": f"평균 점수 {metrics['avg_score']}점으로 매우 낮음 (품질 문제)",
            })
        elif metrics["avg_score"] < 50:
            issues.append({
                "severity": "MEDIUM",
                "check": "mediocre_avg_score",
                "detail": f"평균 점수 {metrics['avg_score']}점 (개선 필요)",
            })

        # 4. 관련성 검증 - 제목에 쿼리 키워드 또는 동의어 포함 여부
        from news_collector.ranking.ranker import Ranker
        query_keywords = set(query["query"].lower().split())
        # 동의어 확장
        expanded_keywords = set(query_keywords)
        for kw in query_keywords:
            synonyms = Ranker.KEYWORD_SYNONYMS.get(kw, [])
            expanded_keywords.update(s.lower() for s in synonyms)

        relevance_hits = 0
        for r in results:
            title_lower = r.title.lower()
            body_lower = (r.body or "").lower()
            text = title_lower + " " + body_lower
            if any(kw in text for kw in expanded_keywords):
                relevance_hits += 1
        metrics["relevance_ratio"] = round(relevance_hits / len(results), 2) if results else 0

        if metrics["relevance_ratio"] < 0.3 and len(query_keywords) > 0:
            keyword_str = ", ".join(query_keywords)
            issues.append({
                "severity": "HIGH",
                "check": "low_relevance",
                "detail": f"키워드 '{keyword_str}' 관련 기사 {relevance_hits}/{len(results)}건 ({metrics['relevance_ratio']*100:.0f}%)",
            })

        # 5. 소스 다양성 검증
        source_names = [r.source_name for r in results]
        unique_sources = set(source_names)
        metrics["unique_sources"] = len(unique_sources)
        metrics["diversity_ratio"] = round(len(unique_sources) / len(results), 2) if results else 0

        if len(results) >= 3 and len(unique_sources) == 1:
            issues.append({
                "severity": "MEDIUM",
                "check": "no_diversity",
                "detail": f"모든 결과가 단일 소스: {source_names[0]}",
            })

        # 6. 날짜 검증 - 결과 날짜가 요청 날짜 근처인지
        target = datetime.strptime(query["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        date_matches = 0
        for r in results:
            if r.published_at:
                pub = r.published_at
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                diff_days = abs((pub - target).days)
                if diff_days <= 3:
                    date_matches += 1
        metrics["date_match_ratio"] = round(date_matches / len(results), 2) if results else 0

        if metrics["date_match_ratio"] < 0.5 and len(results) > 0:
            issues.append({
                "severity": "MEDIUM",
                "check": "date_mismatch",
                "detail": f"요청 날짜 {query['date']} 근처 기사 {date_matches}/{len(results)}건",
            })

        # 7. 프리셋별 특성 검증
        preset = query["preset"]
        if preset == "trending" and results:
            # trending은 인기도 점수가 높아야 함
            pop_scores = [r.popularity_score for r in results]
            avg_pop = sum(pop_scores) / len(pop_scores)
            metrics["avg_popularity"] = round(avg_pop, 3)
            if avg_pop < 0.1:
                issues.append({
                    "severity": "LOW",
                    "check": "low_trending_popularity",
                    "detail": f"trending 프리셋이지만 평균 인기도 {avg_pop:.3f}",
                })

        elif preset == "quality" and results:
            # quality는 품질 점수가 높아야 함
            quality_scores = [r.quality_score for r in results]
            avg_quality = sum(quality_scores) / len(quality_scores)
            metrics["avg_quality"] = round(avg_quality, 3)

        elif preset == "credible" and results:
            # credible은 신뢰도 점수가 높아야 함
            cred_scores = [r.credibility_score for r in results]
            avg_cred = sum(cred_scores) / len(cred_scores)
            metrics["avg_credibility"] = round(avg_cred, 3)
            if avg_cred < 0.5:
                issues.append({
                    "severity": "MEDIUM",
                    "check": "low_credibility_in_credible_preset",
                    "detail": f"credible 프리셋이지만 평균 신뢰도 {avg_cred:.3f}",
                })

        # 8. 무결성 검증 - 빈 제목/본문
        empty_count = sum(1 for r in results if not r.title or not r.body)
        if empty_count > 0:
            issues.append({
                "severity": "HIGH",
                "check": "empty_content",
                "detail": f"제목/본문이 비어있는 결과 {empty_count}건",
            })

        # 9. URL 유효성
        no_url = sum(1 for r in results if not r.url)
        if no_url > 0:
            issues.append({
                "severity": "LOW",
                "check": "missing_url",
                "detail": f"URL이 없는 결과 {no_url}건",
            })

        # 10. 점수 일관성 - 순위와 점수가 일치하는지
        for i in range(len(results) - 1):
            if preset != "latest" and results[i].final_score < results[i+1].final_score:
                issues.append({
                    "severity": "CRITICAL",
                    "check": "score_ordering",
                    "detail": f"순위 {i+1}위({results[i].final_score}점)가 {i+2}위({results[i+1].final_score}점)보다 낮음",
                })
                break

        # 종합 점수 계산
        severity_weights = {"CRITICAL": 30, "HIGH": 15, "MEDIUM": 5, "LOW": 2}
        penalty = sum(severity_weights.get(i["severity"], 0) for i in issues)
        final_quality = max(0, 100 - penalty)

        # 기본 품질 보너스
        if metrics["avg_score"] >= 60:
            final_quality = min(100, final_quality + 10)
        if metrics["relevance_ratio"] >= 0.5:
            final_quality = min(100, final_quality + 5)
        if metrics["diversity_ratio"] >= 0.5:
            final_quality = min(100, final_quality + 5)

        passed = final_quality >= 50 and not any(i["severity"] == "CRITICAL" for i in issues)

        return {
            "passed": passed,
            "score": final_quality,
            "issues": issues,
            "metrics": metrics,
        }


# ─────────────────── 자동 테스트 실행기 ───────────────────

class AutoTester:
    """반복적으로 랜덤 테스트를 실행하고 결과를 취합."""

    def __init__(self) -> None:
        self.validator = QualityValidator()
        self.all_results: List[Dict[str, Any]] = []
        self.issue_histogram: Dict[str, int] = {}

    def run_single_test(self, test_num: int) -> Dict[str, Any]:
        """단일 테스트 실행."""
        query = generate_random_query()

        print(f"\n  [{test_num}] 쿼리: '{query['query']}' | 날짜: {query['date']} | "
              f"프리셋: {query['preset']} | {query['lang'].upper()} | limit={query['limit']}")

        try:
            # 수집
            raw_records = fetch_google_news_rss(
                query=query["query"],
                date_str=query["date"],
                lang=query["lang"],
                country=query["country"],
            )
            print(f"       수집: {len(raw_records)}건", end="")

            # 파이프라인
            query_keywords = query["query"].split() if query["query"] else None
            results = run_pipeline(
                raw_records, preset=query["preset"], limit=query["limit"],
                keywords=query_keywords,
            )
            print(f" → 결과: {len(results)}건", end="")

            # 검증
            validation = self.validator.validate(query, raw_records, results)
            status = "PASS" if validation["passed"] else "FAIL"
            print(f" → 품질: {validation['score']}점 [{status}]")

            # 이슈 기록
            for issue in validation["issues"]:
                key = f"{issue['severity']}:{issue['check']}"
                self.issue_histogram[key] = self.issue_histogram.get(key, 0) + 1
                if issue["severity"] in ("CRITICAL", "HIGH"):
                    print(f"       [!] [{issue['severity']}] {issue['detail']}")

            # 상위 결과 요약
            if results:
                for r in results[:2]:
                    title_preview = r.title[:50] + "..." if len(r.title) > 50 else r.title
                    try:
                        print(f"       -> {r.rank_position}: {title_preview} "
                              f"({r.final_score}, {r.source_name})")
                    except UnicodeEncodeError:
                        safe_title = title_preview.encode("ascii", errors="replace").decode("ascii")
                        print(f"       -> {r.rank_position}: {safe_title} "
                              f"({r.final_score}, {r.source_name})")

            return {
                "test_num": test_num,
                "query": query,
                "raw_count": len(raw_records),
                "result_count": len(results),
                "validation": validation,
                "results": results,
            }

        except Exception as e:
            print(f"       [X] 에러: {e}")
            traceback.print_exc()
            return {
                "test_num": test_num,
                "query": query,
                "raw_count": 0,
                "result_count": 0,
                "validation": {"passed": False, "score": 0, "issues": [
                    {"severity": "CRITICAL", "check": "runtime_error", "detail": str(e)}
                ], "metrics": {}},
                "error": str(e),
            }

    def run_batch(self, num_tests: int = 10) -> Dict[str, Any]:
        """배치 테스트 실행."""
        print(f"\n{'='*70}")
        print(f"  자동화 품질 검증 - {num_tests}개 랜덤 쿼리 실행")
        print(f"  시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}")

        results = []
        for i in range(num_tests):
            result = self.run_single_test(i + 1)
            results.append(result)
            self.all_results.append(result)
            # RSS rate limit 방지
            if i < num_tests - 1:
                time.sleep(1.5)

        return self._generate_report(results)

    def _generate_report(self, results: List[Dict]) -> Dict[str, Any]:
        """배치 결과 리포트 생성."""
        total = len(results)
        passed = sum(1 for r in results if r["validation"]["passed"])
        failed = total - passed
        errors = sum(1 for r in results if "error" in r)

        scores = [r["validation"]["score"] for r in results]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        # 이슈 빈도 집계
        issue_freq: Dict[str, int] = {}
        for r in results:
            for issue in r["validation"]["issues"]:
                key = issue["check"]
                issue_freq[key] = issue_freq.get(key, 0) + 1

        # 가장 빈번한 문제 식별
        sorted_issues = sorted(issue_freq.items(), key=lambda x: x[1], reverse=True)

        # 프리셋별 성능
        preset_scores: Dict[str, List[float]] = {}
        for r in results:
            preset = r["query"]["preset"]
            if preset not in preset_scores:
                preset_scores[preset] = []
            preset_scores[preset].append(r["validation"]["score"])

        preset_avgs = {
            k: round(sum(v) / len(v), 1)
            for k, v in preset_scores.items()
        }

        report = {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "pass_rate": round(passed / total * 100, 1) if total else 0,
                "avg_quality_score": avg_score,
            },
            "top_issues": sorted_issues[:10],
            "preset_performance": preset_avgs,
            "issue_histogram": dict(self.issue_histogram),
        }

        # 리포트 출력
        print(f"\n{'='*70}")
        print(f"  검증 리포트")
        print(f"{'='*70}")
        print(f"  총 테스트: {total}건 | 통과: {passed}건 | 실패: {failed}건 | 에러: {errors}건")
        print(f"  통과율: {report['summary']['pass_rate']}% | 평균 품질: {avg_score}점")

        if sorted_issues:
            print(f"\n  빈번한 문제 (상위 5):")
            for issue_name, count in sorted_issues[:5]:
                pct = round(count / total * 100)
                print(f"    - {issue_name}: {count}건 ({pct}%)")

        if preset_avgs:
            print(f"\n  프리셋별 품질:")
            for preset, avg in sorted(preset_avgs.items(), key=lambda x: x[1], reverse=True):
                print(f"    - {preset}: {avg}점")

        print(f"\n{'='*70}")

        return report


# ─────────────────── 메인 ───────────────────

def main():
    """자동화 테스트 실행."""
    num_tests = 10
    if len(sys.argv) > 1:
        try:
            num_tests = int(sys.argv[1])
        except ValueError:
            pass

    tester = AutoTester()
    report = tester.run_batch(num_tests)

    # 심각한 이슈 요약
    critical_issues = [
        k for k, v in report["issue_histogram"].items()
        if k.startswith("CRITICAL:") and v > 0
    ]

    if critical_issues:
        print(f"\n  [!] CRITICAL 이슈 발견:")
        for ci in critical_issues:
            print(f"    - {ci}: {report['issue_histogram'][ci]}건")
        print(f"    → 즉시 수정 필요!")

    return report


if __name__ == "__main__":
    main()
