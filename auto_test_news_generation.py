#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
뉴스 생성 자동 테스트 스크립트

랜덤 뉴스 검색 → 뉴스 생성 → 구조/내용/이미지 분석 → 문제점 리포트
반복 실행하며 문제점 패턴 파악 및 자동 수정 지원

Usage:
    python auto_test_news_generation.py [num_tests]
    python auto_test_news_generation.py 100  # 100회 테스트
"""

import os
import sys
import random
import time
import json
import re
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple
from collections import Counter

# 환경 변수로 UTF-8 설정 (Windows)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from search_news import search_news
from news_collector.generation import NewsGenerator, NewsFormat, GenerationMode
from news_collector.ingestion.content_scraper import ContentScraper
from news_collector.utils.config_manager import ConfigManager


def _load_test_keywords(config: ConfigManager) -> List[str]:
    """config에서 테스트 키워드 목록 로드"""
    keywords_section = config.get("test.keywords", {})
    all_keywords = []
    for category_keywords in keywords_section.values():
        if isinstance(category_keywords, list):
            all_keywords.extend(category_keywords)
    return all_keywords


# ==============================================================================
# 데이터 클래스
# ==============================================================================

@dataclass
class ImageAnalysis:
    """이미지 분석 결과"""
    total_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    invalid_urls: List[str] = field(default_factory=list)
    invalid_reasons: List[str] = field(default_factory=list)


@dataclass
class StructureAnalysis:
    """뉴스 구조 분석 결과"""
    news_type: str = ""  # standard, visual, data
    has_title: bool = False
    has_summary: bool = False
    has_lead: bool = False
    has_body: bool = False
    has_closing: bool = False
    has_images: bool = False

    title_length: int = 0
    summary_length: int = 0
    body_length: int = 0
    total_length: int = 0

    # 구조 문제점
    issues: List[str] = field(default_factory=list)


@dataclass
class TestResult:
    """개별 테스트 결과"""
    test_id: int
    keyword: str
    timestamp: str

    # 검색 결과
    search_count: int = 0
    search_time_ms: int = 0

    # 생성 결과
    generation_success: bool = False
    generation_time_ms: int = 0
    generated_char_count: int = 0
    source_count: int = 0

    # 분석 결과
    structure: Optional[StructureAnalysis] = None
    images: Optional[ImageAnalysis] = None

    # 종합 점수
    score: float = 0.0
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "test_id": self.test_id,
            "keyword": self.keyword,
            "timestamp": self.timestamp,
            "search_count": self.search_count,
            "search_time_ms": self.search_time_ms,
            "generation_success": self.generation_success,
            "generation_time_ms": self.generation_time_ms,
            "generated_char_count": self.generated_char_count,
            "source_count": self.source_count,
            "score": self.score,
            "issues": self.issues,
        }
        if self.structure:
            result["structure"] = asdict(self.structure)
        if self.images:
            result["images"] = {
                "total_count": self.images.total_count,
                "valid_count": self.images.valid_count,
                "invalid_count": self.images.invalid_count,
                "invalid_reasons": self.images.invalid_reasons[:5],  # 최대 5개만
            }
        return result


@dataclass
class TestSummary:
    """테스트 요약"""
    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0

    avg_score: float = 0.0
    avg_char_count: float = 0.0
    avg_generation_time_ms: float = 0.0

    # 이슈 통계
    issue_counts: Dict[str, int] = field(default_factory=dict)

    # 뉴스 유형 분포
    type_distribution: Dict[str, int] = field(default_factory=dict)


# ==============================================================================
# 이미지 검증 (content_scraper와 동일한 로직)
# ==============================================================================

# 제외 패턴 (광고/아이콘/로고)
IMAGE_EXCLUDE_PATTERNS = [
    # 아이콘/로고/버튼/UI 요소
    'icon', 'logo', 'btn', 'button', 'badge',
    'util_', '_util', 'view_util', 'view_btn', 'view_bt',
    'tool-', '-tool', 'bookmark', 'print', 'copy', 'font',
    # 배경/장식/정보 이미지
    '_bg', 'bg_', '_bg.', 'series_', 'header_', 'footer_',
    '_info', 'info_', 'notice_', 'popup_', 'modal_',
    # 광고 관련
    'banner', 'ad_', 'ads_', '/ad/', '/ads/', 'adsense', 'advert', 'sponsor',
    'promo', 'promotion', 'campaign', 'click', 'track',
    # SNS 공유 버튼
    'sns', 'share', 'view_sns', 'social',
    'kakao', 'facebook', 'twitter', 'naver_', 'google_',
    # 작은/썸네일/피드 이미지
    'thumb_s', 'thumb_xs', '_s.', '_xs.', '_t.',
    'small_', '_small', 'mini_', '_mini', 'thumbnail_small', '.thumb.',
    '/feed/', 'feed_', '_feed', '_thumb', '/thumb/',
    # 기자/관련기사 이미지
    'journalist', 'reporter', 'byline', 'author',
    'related_', '_related', 'recommend', 'sidebar',
    # 플레이어/비디오 UI
    'player', 'video_', '_video', 'play_', '_play',
    # 기타 UI/플레이스홀더
    'loading', 'spinner', 'placeholder', 'default', 'no-image', 'noimage',
    'pixel', 'tracker', 'spacer', 'blank', 'transparent',
    '1x1', '1px', 'sprite', 'emoji', 'avatar', 'profile',
    # 확장자 기반
    '.svg', '.ico', '.cur', '.gif',
]


def validate_image_url(img_url: str) -> Tuple[bool, str]:
    """이미지 URL 유효성 검증"""
    if not img_url:
        return False, "empty_url"

    # HTTP로 시작해야 함
    if not img_url.startswith('http'):
        return False, "invalid_protocol"

    # 플레이스홀더 제외
    if '{{' in img_url or '}}' in img_url:
        return False, "placeholder"

    url_lower = img_url.lower()

    # 제외 패턴 체크
    for pattern in IMAGE_EXCLUDE_PATTERNS:
        if pattern in url_lower:
            return False, f"pattern:{pattern}"

    # 크기 체크 (URL에 크기 정보 있으면)
    size_pattern = r'[_-](\d+)x(\d+)'
    size_match = re.search(size_pattern, url_lower)
    if size_match:
        width, height = int(size_match.group(1)), int(size_match.group(2))
        if width < 150 or height < 100:
            return False, f"too_small:{width}x{height}"

    return True, "valid"


def analyze_images(image_urls: List[str]) -> ImageAnalysis:
    """이미지 목록 분석"""
    analysis = ImageAnalysis(total_count=len(image_urls))

    for url in image_urls:
        is_valid, reason = validate_image_url(url)
        if is_valid:
            analysis.valid_count += 1
        else:
            analysis.invalid_count += 1
            analysis.invalid_urls.append(url)
            analysis.invalid_reasons.append(reason)

    return analysis


# ==============================================================================
# 뉴스 구조 분석
# ==============================================================================

def analyze_structure(
    generated_news,
    result,
    news_type: str,
    config: ConfigManager = None,
) -> StructureAnalysis:
    """생성된 뉴스 구조 분석"""
    analysis = StructureAnalysis(news_type=news_type)

    # 제목 분석
    title = generated_news.title or ""
    analysis.has_title = len(title) > 0
    analysis.title_length = len(title)

    if analysis.title_length == 0:
        analysis.issues.append("MISSING_TITLE")
    elif analysis.title_length > 60:
        analysis.issues.append(f"TITLE_TOO_LONG:{analysis.title_length}")

    # 본문 분석
    body = generated_news.body or ""
    analysis.body_length = len(body)
    analysis.total_length = analysis.title_length + analysis.body_length

    # 본문 섹션 분석 (리드/본문/마무리)
    body_parts = body.split('\n\n') if body else []

    if len(body_parts) >= 1:
        analysis.has_lead = len(body_parts[0]) > 30
        analysis.summary_length = len(body_parts[0])

    if len(body_parts) >= 2:
        analysis.has_body = True

    if len(body_parts) >= 3:
        analysis.has_closing = len(body_parts[-1]) > 20

    # 이미지 분석
    images = result.images or []
    analysis.has_images = len(images) > 0

    # 뉴스 유형별 검증 (config에서 길이 기준 로드)
    body_cfg = config.get("generation.body_length", {}) if config else {}
    std_cfg = body_cfg.get("standard", {})
    vis_cfg = body_cfg.get("visual", {})
    dat_cfg = body_cfg.get("data", {})

    if news_type == "standard":
        std_min = std_cfg.get("min", 400)
        std_max = std_cfg.get("max", 800)
        if analysis.body_length < std_min:
            analysis.issues.append(f"BODY_TOO_SHORT:{analysis.body_length}")
        elif analysis.body_length > std_max:
            analysis.issues.append(f"BODY_TOO_LONG:{analysis.body_length}")

        if len(images) > 1:
            analysis.issues.append(f"TOO_MANY_IMAGES_FOR_STANDARD:{len(images)}")

    elif news_type == "visual":
        vis_min = vis_cfg.get("min", 200)
        if analysis.body_length < vis_min:
            analysis.issues.append(f"BODY_TOO_SHORT:{analysis.body_length}")

        if len(images) < 2:
            analysis.issues.append(f"NOT_ENOUGH_IMAGES_FOR_VISUAL:{len(images)}")

    elif news_type == "data":
        dat_min = dat_cfg.get("min", 300)
        if analysis.body_length < dat_min:
            analysis.issues.append(f"BODY_TOO_SHORT:{analysis.body_length}")

        # 숫자 패턴 체크
        number_patterns = [r'\d+%', r'\d+억', r'\d+만', r'\d+조']
        has_numbers = any(re.search(p, body) for p in number_patterns)
        if not has_numbers:
            analysis.issues.append("NO_NUMBERS_IN_DATA_TYPE")

    # 공통 검증
    if not analysis.has_lead:
        analysis.issues.append("MISSING_LEAD")

    if analysis.body_length < 100:
        analysis.issues.append("CONTENT_TOO_SHORT")

    return analysis


# ==============================================================================
# 뉴스 유형 감지 (content_assembler와 동일)
# ==============================================================================

def detect_news_type(text: str, title: str, image_count: int) -> str:
    """뉴스 유형 감지"""
    combined = f"{title} {text}".lower()

    # 비주얼형: 이미지 2개 이상 또는 비주얼 키워드
    visual_keywords = ['포토', '화보', '현장', '모습', '사진', '갤러리',
                       '인터뷰', '직캠', '스냅', '공개', '포착']
    if image_count >= 2 or any(kw in combined for kw in visual_keywords):
        return "visual"

    # 데이터형: 숫자 밀도 높음 또는 데이터 키워드
    numeric_chars = sum(1 for c in combined if c.isdigit())
    density = numeric_chars / len(combined) if combined else 0
    data_keywords = ['통계', '지표', '수치', '조사', '분석', '전망', '순위', '증감']

    if density >= 0.03 or any(kw in combined for kw in data_keywords):
        number_patterns = [r'\d+%', r'\d+억', r'\d+조', r'\d+만']
        pattern_matches = sum(1 for p in number_patterns if re.search(p, combined))
        if pattern_matches >= 2:
            return "data"

    # 기본: 일반형
    return "standard"


# ==============================================================================
# 테스트 실행
# ==============================================================================

def run_single_test(
    test_id: int,
    keyword: str,
    generator: NewsGenerator,
    scraper: ContentScraper,
    config: ConfigManager = None,
) -> TestResult:
    """단일 테스트 실행"""
    result = TestResult(
        test_id=test_id,
        keyword=keyword,
        timestamp=datetime.now().isoformat(),
    )

    try:
        search_limit = config.get("generation.search_limit", 5) if config else 5
        scrape_min_body = config.get("generation.scrape_min_body_length", 150) if config else 150
        max_scrape_imgs = config.get("generation.max_scrape_images", 3) if config else 3

        # 1. 뉴스 검색
        search_start = time.time()
        news_list = search_news(keyword, limit=search_limit)
        result.search_time_ms = int((time.time() - search_start) * 1000)
        result.search_count = len(news_list)

        if not news_list:
            result.issues.append("NO_SEARCH_RESULTS")
            return result

        # 2. 본문 스크래핑 (필요시)
        enriched_news = []
        for news in news_list:
            if len(news.body or "") < scrape_min_body and news.url:
                try:
                    scraped = scraper.scrape(news.url)
                    if scraped.success and len(scraped.full_body) > len(news.body or ""):
                        from dataclasses import replace
                        news = replace(
                            news,
                            body=scraped.full_body,
                            image_urls=list(news.image_urls or []) + scraped.images[:max_scrape_imgs],
                        )
                except Exception:
                    pass
            enriched_news.append(news)

        # 3. 뉴스 생성
        gen_start = time.time()
        gen_result = generator.generate(
            source_news=enriched_news,
            target_format=NewsFormat.STRAIGHT,
            mode=GenerationMode.SYNTHESIS,
            enrich_content=False,  # 이미 스크래핑함
            search_keywords=[keyword],
        )
        result.generation_time_ms = int((time.time() - gen_start) * 1000)

        if not gen_result.success or not gen_result.generated_news:
            result.issues.append("GENERATION_FAILED")
            return result

        result.generation_success = True
        result.generated_char_count = gen_result.generated_news.char_count
        result.source_count = len(enriched_news)

        # 4. 뉴스 유형 감지
        news_type = detect_news_type(
            text=gen_result.generated_news.body or "",
            title=gen_result.generated_news.title or "",
            image_count=len(gen_result.images or []),
        )

        # 5. 구조 분석
        result.structure = analyze_structure(
            gen_result.generated_news,
            gen_result,
            news_type,
            config,
        )
        result.issues.extend(result.structure.issues)

        # 6. 이미지 분석
        result.images = analyze_images(gen_result.images or [])
        if result.images.invalid_count > 0:
            result.issues.append(f"INVALID_IMAGES:{result.images.invalid_count}")

        # 7. 점수 계산
        result.score = calculate_score(result, config)

    except Exception as e:
        result.issues.append(f"ERROR:{str(e)[:50]}")

    return result


def calculate_score(result: TestResult, config: ConfigManager = None) -> float:
    """테스트 결과 점수 계산 (0-100)"""
    scoring = config.get("test.scoring", {}) if config else {}

    base = scoring.get("base_score", 100)
    thresholds = scoring.get("length_thresholds", {})
    penalties = scoring.get("length_penalties", {})
    issue_penalty = scoring.get("issue_penalty", 5)
    slow_ms = scoring.get("slow_generation_ms", 10000)
    slow_pen = scoring.get("slow_generation_penalty", 10)
    mod_ms = scoring.get("moderate_generation_ms", 5000)
    mod_pen = scoring.get("moderate_generation_penalty", 5)
    img_pen = scoring.get("invalid_image_penalty", 3)

    score = float(base)

    if not result.generation_success:
        return 0.0

    # 본문 길이
    char_count = result.generated_char_count
    good_threshold = thresholds.get("good", 400)
    fair_threshold = thresholds.get("fair", 300)
    poor_threshold = thresholds.get("poor", 200)

    if char_count >= good_threshold:
        pass
    elif char_count >= fair_threshold:
        score -= penalties.get("fair", 10)
    elif char_count >= poor_threshold:
        score -= penalties.get("poor", 20)
    else:
        score -= penalties.get("bad", 30)

    # 이슈 수에 따른 감점
    score -= len(result.issues) * issue_penalty

    # 생성 시간
    if result.generation_time_ms > slow_ms:
        score -= slow_pen
    elif result.generation_time_ms > mod_ms:
        score -= mod_pen

    # 이미지 검증 실패 감점
    if result.images and result.images.invalid_count > 0:
        score -= result.images.invalid_count * img_pen

    return max(0.0, min(100.0, score))


# ==============================================================================
# 메인 실행
# ==============================================================================

def run_tests(num_tests: int = 10) -> TestSummary:
    """테스트 실행"""
    config = ConfigManager()
    test_keywords = _load_test_keywords(config)
    delay = config.get("generation.api_delay_seconds", 0.5)

    if not test_keywords:
        print("config에 test.keywords가 없습니다.")
        return TestSummary()

    print(f"\n{'='*60}")
    print(f"  뉴스 생성 자동 테스트 ({num_tests}회)")
    print(f"{'='*60}\n")

    generator = NewsGenerator()
    scraper = ContentScraper()

    results: List[TestResult] = []
    summary = TestSummary()

    issue_counter = Counter()
    type_counter = Counter()

    for i in range(num_tests):
        # 랜덤 키워드 선택
        keyword = random.choice(test_keywords)

        print(f"[{i+1}/{num_tests}] 키워드: {keyword}", end=" ")

        # 테스트 실행
        result = run_single_test(i + 1, keyword, generator, scraper, config)
        results.append(result)

        # 결과 출력
        if result.generation_success:
            print(f"-> {result.generated_char_count}자, {result.score:.0f}점", end="")
            if result.issues:
                print(f" (이슈: {', '.join(result.issues[:3])})")
            else:
                print(" OK")
        else:
            print(f"-> 실패 ({', '.join(result.issues[:2])})")

        # 통계 수집
        if result.generation_success:
            summary.successful_tests += 1
        else:
            summary.failed_tests += 1

        for issue in result.issues:
            issue_counter[issue.split(':')[0]] += 1

        if result.structure:
            type_counter[result.structure.news_type] += 1

        # 잠시 대기 (API 부하 방지)
        time.sleep(delay)

    # 요약 계산
    summary.total_tests = num_tests
    summary.issue_counts = dict(issue_counter.most_common(20))
    summary.type_distribution = dict(type_counter)

    successful_results = [r for r in results if r.generation_success]
    if successful_results:
        summary.avg_score = sum(r.score for r in successful_results) / len(successful_results)
        summary.avg_char_count = sum(r.generated_char_count for r in successful_results) / len(successful_results)
        summary.avg_generation_time_ms = sum(r.generation_time_ms for r in successful_results) / len(successful_results)

    # 요약 출력
    print(f"\n{'='*60}")
    print("  테스트 요약")
    print(f"{'='*60}")
    print(f"  총 테스트: {summary.total_tests}")
    print(f"  성공: {summary.successful_tests} ({summary.successful_tests/summary.total_tests*100:.1f}%)")
    print(f"  실패: {summary.failed_tests}")
    print(f"  평균 점수: {summary.avg_score:.1f}")
    print(f"  평균 길이: {summary.avg_char_count:.0f}자")
    print(f"  평균 생성시간: {summary.avg_generation_time_ms:.0f}ms")

    print(f"\n  뉴스 유형 분포:")
    for news_type, count in summary.type_distribution.items():
        print(f"    - {news_type}: {count} ({count/summary.total_tests*100:.1f}%)")

    print(f"\n  주요 이슈:")
    for issue, count in list(summary.issue_counts.items())[:10]:
        print(f"    - {issue}: {count}건")

    # 결과 저장
    report_path = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump({
            "summary": {
                "total_tests": summary.total_tests,
                "successful_tests": summary.successful_tests,
                "failed_tests": summary.failed_tests,
                "avg_score": summary.avg_score,
                "avg_char_count": summary.avg_char_count,
                "avg_generation_time_ms": summary.avg_generation_time_ms,
                "issue_counts": summary.issue_counts,
                "type_distribution": summary.type_distribution,
            },
            "results": [r.to_dict() for r in results],
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  리포트 저장: {report_path}")

    return summary


if __name__ == "__main__":
    _config = ConfigManager()
    default_count = _config.get("test.default_count", 10)
    num_tests = int(sys.argv[1]) if len(sys.argv) > 1 else default_count
    run_tests(num_tests)
