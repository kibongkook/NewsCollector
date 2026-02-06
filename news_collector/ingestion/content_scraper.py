"""원본 URL에서 전체 본문 스크래핑

trafilatura를 사용하여 원본 기사 URL에서 전체 본문을 추출합니다.
RSS 피드의 요약(37-119자)을 전체 본문(500-3000자)으로 확장합니다.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import ssl

from news_collector.utils.logger import get_logger

logger = get_logger(__name__)


# 스크래핑 설정
MIN_BODY_LENGTH_FOR_SCRAPE = 150  # 본문이 이 길이 미만이면 스크래핑 시도
DEFAULT_TIMEOUT = 10  # 초
REQUEST_DELAY = 0.5  # 요청 간 지연 (초)
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@dataclass
class ScrapedContent:
    """스크래핑된 콘텐츠"""
    url: str
    full_body: str
    title: Optional[str] = None
    images: List[str] = field(default_factory=list)  # 이미지 URL 목록
    success: bool = False
    error: Optional[str] = None
    response_time_ms: int = 0


@dataclass
class ContentScraperConfig:
    """스크래퍼 설정"""
    min_body_length_for_scrape: int = MIN_BODY_LENGTH_FOR_SCRAPE
    timeout: int = DEFAULT_TIMEOUT
    request_delay: float = REQUEST_DELAY
    user_agent: str = USER_AGENT
    max_retries: int = 2
    # 캐시 설정
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600  # 1시간


class ContentScraper:
    """
    원본 URL에서 전체 본문을 스크래핑하는 엔진.

    주요 기능:
    - trafilatura를 사용한 본문 추출
    - 다양한 한국 뉴스 사이트 지원
    - 요청 지연 및 재시도 처리
    - 결과 캐싱

    사용법:
        scraper = ContentScraper()
        content = scraper.scrape("https://news.example.com/article/123")
        if content.success:
            print(content.full_body)
    """

    def __init__(self, config: Optional[ContentScraperConfig] = None):
        self.config = config or ContentScraperConfig()
        self._cache: Dict[str, Tuple[ScrapedContent, float]] = {}
        self._last_request_time: float = 0.0
        self._trafilatura_available: Optional[bool] = None

    def _check_trafilatura(self) -> bool:
        """trafilatura 사용 가능 여부 확인"""
        if self._trafilatura_available is None:
            try:
                import trafilatura
                self._trafilatura_available = True
            except ImportError:
                logger.warning(
                    "trafilatura 미설치. 본문 스크래핑 불가. "
                    "설치: pip install trafilatura"
                )
                self._trafilatura_available = False
        return self._trafilatura_available

    def scrape(self, url: str) -> ScrapedContent:
        """
        URL에서 전체 본문 스크래핑.

        Args:
            url: 스크래핑할 URL

        Returns:
            ScrapedContent 객체
        """
        if not url:
            return ScrapedContent(url=url, full_body="", error="URL이 비어있음")

        # 캐시 확인
        if self.config.enable_cache:
            cached = self._get_from_cache(url)
            if cached:
                logger.debug("캐시 히트: %s", url[:50])
                return cached

        # trafilatura 확인
        if not self._check_trafilatura():
            return ScrapedContent(
                url=url,
                full_body="",
                error="trafilatura 미설치"
            )

        # 요청 지연
        self._wait_if_needed()

        # 스크래핑 시도
        start_time = time.time()
        result = self._do_scrape(url)
        result.response_time_ms = int((time.time() - start_time) * 1000)

        # 캐시 저장
        if self.config.enable_cache and result.success:
            self._save_to_cache(url, result)

        return result

    def scrape_batch(
        self,
        urls: List[str],
        skip_if_body_long: Optional[Dict[str, str]] = None,
    ) -> Dict[str, ScrapedContent]:
        """
        여러 URL 일괄 스크래핑.

        Args:
            urls: URL 리스트
            skip_if_body_long: {url: 기존_본문} - 본문이 충분히 길면 스킵

        Returns:
            {url: ScrapedContent} 딕셔너리
        """
        results: Dict[str, ScrapedContent] = {}
        skip_if_body_long = skip_if_body_long or {}

        for url in urls:
            # 기존 본문이 충분하면 스킵
            existing_body = skip_if_body_long.get(url, "")
            if len(existing_body) >= self.config.min_body_length_for_scrape:
                results[url] = ScrapedContent(
                    url=url,
                    full_body=existing_body,
                    success=True,
                    error="기존 본문 충분함",
                )
                continue

            results[url] = self.scrape(url)

        return results

    def should_scrape(self, body: str) -> bool:
        """본문 스크래핑이 필요한지 판단"""
        return len(body.strip()) < self.config.min_body_length_for_scrape

    def _resolve_redirect_url(self, url: str) -> str:
        """리다이렉트 URL을 실제 URL로 변환 (Google News 등)"""
        # Google News 리다이렉트 URL 패턴
        if "news.google.com/rss/articles/" in url or "news.google.com/articles/" in url:
            try:
                from googlenewsdecoder import new_decoderv1
                result = new_decoderv1(url)
                if result.get("status") and result.get("decoded_url"):
                    decoded_url = result["decoded_url"]
                    logger.debug("Google News URL 디코딩: %s -> %s", url[:50], decoded_url[:50])
                    return decoded_url
            except ImportError:
                logger.warning(
                    "googlenewsdecoder 미설치. Google News URL 디코딩 불가. "
                    "설치: pip install googlenewsdecoder"
                )
            except Exception as e:
                logger.debug("Google News URL 디코딩 실패: %s - %s", url[:50], e)
        return url

    def _do_scrape(self, url: str) -> ScrapedContent:
        """실제 스크래핑 수행"""
        import trafilatura

        # Google News 등 리다이렉트 URL 해석
        resolved_url = self._resolve_redirect_url(url)

        for attempt in range(self.config.max_retries):
            try:
                # trafilatura로 다운로드 및 추출
                downloaded = trafilatura.fetch_url(resolved_url)

                if not downloaded:
                    if attempt < self.config.max_retries - 1:
                        time.sleep(1)  # 재시도 전 대기
                        continue
                    return ScrapedContent(
                        url=url,
                        full_body="",
                        error="페이지 다운로드 실패",
                    )

                # 본문 추출
                full_body = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=True,
                    include_links=False,
                    favor_precision=True,  # 정확도 우선
                )

                if not full_body:
                    return ScrapedContent(
                        url=url,
                        full_body="",
                        error="본문 추출 실패",
                    )

                # 정제
                full_body = self._clean_body(full_body)

                # 제목 및 이미지 추출
                title = None
                images: List[str] = []
                try:
                    metadata = trafilatura.extract_metadata(downloaded)
                    if metadata:
                        title = getattr(metadata, 'title', None)
                        # 메타데이터에서 대표 이미지 추출
                        image = getattr(metadata, 'image', None)
                        if image:
                            images.append(image)
                except Exception:
                    pass

                # HTML에서 추가 이미지 추출
                extracted_images = self._extract_images_from_html(downloaded, resolved_url)
                for img in extracted_images:
                    if img not in images:
                        images.append(img)

                # 최대 5개 이미지로 제한
                images = images[:5]

                logger.debug(
                    "스크래핑 성공: %s (%d자, 이미지 %d개)",
                    url[:50],
                    len(full_body),
                    len(images)
                )

                return ScrapedContent(
                    url=url,
                    full_body=full_body,
                    title=title,
                    images=images,
                    success=True,
                )

            except Exception as e:
                logger.debug("스크래핑 실패 (시도 %d/%d): %s - %s",
                            attempt + 1, self.config.max_retries, url[:50], e)
                if attempt < self.config.max_retries - 1:
                    time.sleep(1)
                    continue
                return ScrapedContent(
                    url=url,
                    full_body="",
                    error=str(e),
                )

        return ScrapedContent(url=url, full_body="", error="최대 재시도 초과")

    def _extract_images_from_html(self, html: str, base_url: str) -> List[str]:
        """HTML에서 뉴스 관련 이미지 URL 추출"""
        images: List[str] = []
        try:
            # 정규식으로 img 태그의 src 추출
            img_patterns = [
                r'<img[^>]+src=["\']([^"\']+)["\']',
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ]

            for pattern in img_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for match in matches:
                    img_url = self._normalize_image_url(match, base_url)
                    if img_url and self._is_valid_news_image(img_url):
                        if img_url not in images:
                            images.append(img_url)

        except Exception as e:
            logger.debug("이미지 추출 실패: %s", e)

        return images

    def _normalize_image_url(self, img_url: str, base_url: str) -> Optional[str]:
        """이미지 URL 정규화 (상대 경로 → 절대 경로)"""
        if not img_url:
            return None

        # 이미 절대 URL인 경우
        if img_url.startswith('http://') or img_url.startswith('https://'):
            return img_url

        # 프로토콜 상대 URL
        if img_url.startswith('//'):
            return 'https:' + img_url

        # 상대 경로 → 절대 경로
        try:
            from urllib.parse import urljoin
            return urljoin(base_url, img_url)
        except Exception:
            return None

    def _is_valid_news_image(self, img_url: str) -> bool:
        """뉴스 관련 유효한 이미지인지 확인"""
        if not img_url:
            return False

        # URL 형식 체크 (플레이스홀더 제외: {{IMAGE}}, {image} 등)
        if not img_url.startswith('http'):
            return False
        if '{{' in img_url or '}}' in img_url or '{%' in img_url:
            return False

        # 확장자 확인 (SVG/ICO/GIF는 보통 아이콘/UI/애니메이션이므로 제외)
        valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
        excluded_extensions = ('.svg', '.ico', '.cur', '.gif')
        url_lower = img_url.lower()

        # SVG, ICO 등 제외
        path = url_lower.split('?')[0]
        if any(path.endswith(ext) for ext in excluded_extensions):
            return False

        # 쿼리 파라미터 제거 후 확장자 확인
        path = url_lower.split('?')[0]
        has_valid_ext = any(path.endswith(ext) for ext in valid_extensions)

        # 이미지 호스팅 도메인 확인 (확장자 없어도 허용)
        image_hosts = ['imgnews', 'img', 'image', 'photo', 'cdn', 'media', 'pimg', 'dimg']
        is_image_host = any(host in url_lower for host in image_hosts)

        if not has_valid_ext and not is_image_host:
            return False

        # 제외할 패턴 (아이콘, 로고, 광고, SNS 버튼 등)
        exclude_patterns = [
            # 아이콘/로고/버튼/UI 요소
            'icon', 'logo', 'btn', 'button', 'badge',
            'util_', '_util', 'view_util', 'view_btn', 'view_bt',
            'tool-', '-tool', 'bookmark', 'print', 'copy', 'font',
            # 배경/장식/정보 이미지
            '_bg', 'bg_', '_bg.', 'series_', 'header_', 'footer_',
            '_info', 'info_', 'notice_', 'popup_', 'modal_',
            # 광고 관련
            'banner', 'ad_', 'ads_', '/ad/', '/ads/', 'adsense', 'advert', 'sponsor',
            # 트래커/기술적 이미지
            'pixel', 'tracker', 'spacer', 'blank', 'loading', 'spinner',
            '1x1', '1px', 'transparent', 'sprite', 'emoji', 'placeholder', 'default',
            # 프로필/아바타/기자
            'avatar', 'profile', 'journalist', 'reporter', 'writer', 'byline',
            # 썸네일 (다양한 패턴)
            'thumbnail_small', 'thumb_', '.thumb.', '_thumb', '/thumb/', '_t.',
            'thumb_s', 'thumb_xs', '_s.', '_xs.', 'small_', '_small', 'mini_', '_mini',
            # SNS 공유 버튼
            'sns', 'share', 'view_sns', 'social',
            'kakao', 'facebook', 'twitter', 'naver_', 'google_',
            'instagram', 'youtube', 'tiktok', 'linkedin',
            # 댓글/좋아요/반응 버튼
            'comment', 'reply', 'like', 'dislike', 'vote', 'reaction',
            # 경로 기반 (관련 기사, 광고 영역)
            '/feed/', '/carriage/', '/company/', '/partner/',
            '/related/', '/recommend/', '/popular/',
        ]

        for pattern in exclude_patterns:
            if pattern in url_lower:
                return False

        # 최소 크기 추정 (URL에 크기 정보가 있는 경우)
        size_pattern = r'[_-](\d+)x(\d+)'
        size_match = re.search(size_pattern, url_lower)
        if size_match:
            width, height = int(size_match.group(1)), int(size_match.group(2))
            if width < 100 or height < 100:
                return False

        return True

    def _clean_body(self, text: str) -> str:
        """본문 정제"""
        if not text:
            return ""

        # 1. 연속 공백/개행 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # 2. 기자 이름/이메일 패턴 제거
        text = re.sub(r'[가-힣]{2,4}\s*기자\s*[\w.]*@[\w.]+', '', text)
        text = re.sub(r'[\w.]+@[\w.]+\.[\w.]+', '', text)
        text = re.sub(r'\n[가-힣]{2,4}\s*기자\s*$', '', text, flags=re.MULTILINE)

        # 3. 사이드바/추천 기사 목록 제거 (- 로 시작하는 기사 제목들)
        # 연속된 "- 제목 - 언론사" 패턴 제거
        text = re.sub(r'(?:\n\s*-\s*[^\n]+){2,}', '', text)

        # 4. 보일러플레이트 텍스트 제거
        boilerplate_patterns = [
            r'전체\s*맥락을\s*이해하기\s*위해서는\s*본문\s*보기를\s*권장합니다\.?',
            r'본문\s*내용은\s*.*?참조하세요\.?',
            r'자세한\s*내용은\s*.*?확인하세요\.?',
            r'인공지능이\s*자동으로\s*줄인.*?기술을\s*사용합니다\.?',
            r'AI가\s*요약한\s*내용입니다\.?',
            r'더\s*자세한\s*내용은\s*원문에서\s*확인.*',
        ]
        for pattern in boilerplate_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # 5. 광고/관련기사/저작권 태그 제거
        ad_patterns = [
            r'\[관련기사\].*$',
            r'\[ⓒ.*?\]',
            r'\[출처:\s*[^\]]+\]',
            r'Copyright\s*©.*$',
            r'무단\s*전재.*금지.*$',
            r'ⓒ\s*\d{4}.*$',
            r'All\s*[Rr]ights\s*[Rr]eserved.*$',
            r'저작권자\s*\([cC©]\).*$',
            r'<저작권자.*?(?:>|$)',
            r'저작권\s*(?:ⓒ|©).*$',
            r'\(끝\)\s*$',
            r'▶\s*.*$',
            r'☞\s*.*$',
        ]
        for pattern in ad_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

        # 6. 연속된 줄바꿈으로 끝나는 기사 목록 제거 (하이퍼링크 텍스트)
        lines = text.split('\n')
        cleaned_lines = []
        skip_section = False

        for line in lines:
            line_stripped = line.strip()

            # 기사 목록 시작 감지 (- 또는 · 로 시작하고 언론사명 포함)
            if re.match(r'^[-·•]\s*.+[-–]\s*(아시아경제|연합뉴스|한겨레|조선일보|중앙일보|동아일보|매일경제|한국경제|머니투데이|뉴시스|뉴스1|YTN|MBC|KBS|SBS)', line_stripped):
                skip_section = True
                continue

            # 빈 줄이면 섹션 종료
            if not line_stripped:
                skip_section = False

            if not skip_section:
                cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # 7. 마지막 정리
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'^\s*\n', '', text)

        return text.strip()

    def _wait_if_needed(self) -> None:
        """요청 간 지연"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.config.request_delay:
            time.sleep(self.config.request_delay - elapsed)
        self._last_request_time = time.time()

    def _get_from_cache(self, url: str) -> Optional[ScrapedContent]:
        """캐시에서 조회"""
        if url not in self._cache:
            return None

        content, timestamp = self._cache[url]
        if time.time() - timestamp > self.config.cache_ttl_seconds:
            del self._cache[url]
            return None

        return content

    def _save_to_cache(self, url: str, content: ScrapedContent) -> None:
        """캐시에 저장"""
        self._cache[url] = (content, time.time())

    def clear_cache(self) -> None:
        """캐시 비우기"""
        self._cache.clear()


# ============================================================
# 유사 뉴스 감지 및 병합
# ============================================================

@dataclass
class SimilarNewsGroup:
    """유사 뉴스 그룹"""
    primary_news_id: str
    similar_news_ids: List[str]
    similarity_scores: Dict[str, float]  # news_id -> similarity


class NewsSimilarityDetector:
    """
    유사 뉴스 감지기.

    제목과 본문을 비교하여 유사한 뉴스를 그룹화합니다.
    """

    def __init__(
        self,
        title_threshold: float = 0.6,
        body_threshold: float = 0.5,
        combined_threshold: float = 0.55,
    ):
        """
        Args:
            title_threshold: 제목 유사도 임계값
            body_threshold: 본문 유사도 임계값
            combined_threshold: 종합 유사도 임계값
        """
        self.title_threshold = title_threshold
        self.body_threshold = body_threshold
        self.combined_threshold = combined_threshold

    def find_similar_groups(
        self,
        news_list: List,  # List[NewsWithScores]
        min_group_size: int = 2,
    ) -> List[SimilarNewsGroup]:
        """
        유사 뉴스 그룹 찾기.

        Args:
            news_list: 뉴스 리스트
            min_group_size: 최소 그룹 크기

        Returns:
            SimilarNewsGroup 리스트
        """
        if len(news_list) < 2:
            return []

        # 유사도 행렬 계산
        n = len(news_list)
        similarity_matrix: Dict[str, Dict[str, float]] = {}

        for i in range(n):
            news_i = news_list[i]
            similarity_matrix[news_i.id] = {}

            for j in range(i + 1, n):
                news_j = news_list[j]
                sim = self._calculate_similarity(news_i, news_j)

                if sim >= self.combined_threshold:
                    similarity_matrix[news_i.id][news_j.id] = sim

        # 그룹 구성 (가장 긴 본문을 가진 뉴스가 primary)
        groups: List[SimilarNewsGroup] = []
        used_ids: set = set()

        # 본문 길이 순으로 정렬
        sorted_news = sorted(
            news_list,
            key=lambda n: len(n.body or ""),
            reverse=True
        )

        for news in sorted_news:
            if news.id in used_ids:
                continue

            # 이 뉴스와 유사한 뉴스 찾기
            similar_ids = []
            scores = {}

            for other_id, sim in similarity_matrix.get(news.id, {}).items():
                if other_id not in used_ids:
                    similar_ids.append(other_id)
                    scores[other_id] = sim

            # 역방향 검색 (다른 뉴스에서 이 뉴스를 유사하다고 한 경우)
            for primary_id, sim_dict in similarity_matrix.items():
                if news.id in sim_dict and primary_id not in used_ids:
                    if primary_id not in similar_ids:
                        similar_ids.append(primary_id)
                        scores[primary_id] = sim_dict[news.id]

            if len(similar_ids) >= min_group_size - 1:  # primary 포함해서 min_group_size
                groups.append(SimilarNewsGroup(
                    primary_news_id=news.id,
                    similar_news_ids=similar_ids,
                    similarity_scores=scores,
                ))
                used_ids.add(news.id)
                used_ids.update(similar_ids)

        return groups

    def _calculate_similarity(self, news1, news2) -> float:
        """두 뉴스 간 유사도 계산"""
        # 제목 유사도 (Jaccard)
        title_sim = self._jaccard_similarity(
            news1.title or "",
            news2.title or "",
        )

        # 본문 유사도 (Jaccard)
        body_sim = self._jaccard_similarity(
            news1.body or "",
            news2.body or "",
        )

        # 가중 평균 (제목 60%, 본문 40%)
        combined = title_sim * 0.6 + body_sim * 0.4

        return combined

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Jaccard 유사도"""
        words1 = set(self._tokenize(text1))
        words2 = set(self._tokenize(text2))

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2

        return len(intersection) / len(union) if union else 0.0

    def _tokenize(self, text: str) -> List[str]:
        """간단한 토큰화"""
        # 한글, 영어, 숫자만 추출
        words = re.findall(r'[가-힣]+|[a-zA-Z]+|[0-9]+', text.lower())
        # 너무 짧은 단어 제외
        return [w for w in words if len(w) >= 2]


class NewsMerger:
    """
    유사 뉴스 병합기.

    여러 유사 뉴스의 본문을 합쳐서 더 풍부한 콘텐츠를 생성합니다.
    """

    def __init__(self, similarity_detector: Optional[NewsSimilarityDetector] = None):
        self.similarity_detector = similarity_detector or NewsSimilarityDetector()

    def merge_similar_news(
        self,
        news_list: List,  # List[NewsWithScores]
        target_body_length: int = 500,
    ) -> List:  # List[NewsWithScores]
        """
        유사 뉴스 병합.

        본문이 짧은 뉴스를 유사한 뉴스와 병합하여 본문을 확장합니다.

        Args:
            news_list: 원본 뉴스 리스트
            target_body_length: 목표 본문 길이

        Returns:
            병합된 뉴스 리스트 (원본도 포함, 병합된 것은 body가 확장됨)
        """
        if not news_list:
            return []

        # 유사 그룹 찾기
        groups = self.similarity_detector.find_similar_groups(news_list)

        if not groups:
            return news_list

        # 뉴스 ID -> 뉴스 객체 매핑
        news_by_id = {n.id: n for n in news_list}
        merged_ids: set = set()
        result = []

        for group in groups:
            primary = news_by_id.get(group.primary_news_id)
            if not primary:
                continue

            # primary 본문이 이미 충분하면 스킵
            if len(primary.body or "") >= target_body_length:
                result.append(primary)
                merged_ids.add(primary.id)
                merged_ids.update(group.similar_news_ids)
                continue

            # 유사 뉴스들의 본문 수집
            all_bodies = [primary.body or ""]
            for similar_id in group.similar_news_ids:
                similar_news = news_by_id.get(similar_id)
                if similar_news and similar_news.body:
                    all_bodies.append(similar_news.body)

            # 본문 병합
            merged_body = self._merge_bodies(all_bodies)

            # 새 객체 생성 (dataclass의 불변성 유지를 위해)
            from dataclasses import replace
            merged_news = replace(
                primary,
                body=merged_body,
            )

            result.append(merged_news)
            merged_ids.add(primary.id)
            merged_ids.update(group.similar_news_ids)

            logger.debug(
                "뉴스 병합: %s (%d건, %d -> %d자)",
                primary.title[:30] if primary.title else "제목없음",
                len(group.similar_news_ids) + 1,
                len(primary.body or ""),
                len(merged_body),
            )

        # 병합되지 않은 뉴스 추가
        for news in news_list:
            if news.id not in merged_ids:
                result.append(news)

        return result

    def _merge_bodies(self, bodies: List[str]) -> str:
        """여러 본문을 하나로 병합 (중복 문장 제거)"""
        all_sentences: List[str] = []
        seen_normalized: set = set()

        for body in bodies:
            sentences = re.split(r'(?<=[.!?])\s+', body)
            for sent in sentences:
                sent = sent.strip()
                if not sent or len(sent) < 10:
                    continue

                # 정규화
                normalized = re.sub(r'\s+', ' ', sent.lower())
                normalized = re.sub(r'[^\w\s가-힣]', '', normalized)

                # 중복 체크
                if normalized not in seen_normalized:
                    # 유사도 체크
                    is_duplicate = False
                    for seen in seen_normalized:
                        if self._jaccard_similarity(normalized, seen) >= 0.7:
                            is_duplicate = True
                            break

                    if not is_duplicate:
                        all_sentences.append(sent)
                        seen_normalized.add(normalized)

        return " ".join(all_sentences)

    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Jaccard 유사도"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union) if union else 0.0


# ============================================================
# 편의 함수
# ============================================================

def scrape_full_content(url: str) -> ScrapedContent:
    """단일 URL 스크래핑 (편의 함수)"""
    scraper = ContentScraper()
    return scraper.scrape(url)


def enrich_news_with_full_body(
    news_list: List,  # List[NewsWithScores]
    min_body_length: int = MIN_BODY_LENGTH_FOR_SCRAPE,
) -> List:
    """
    본문이 짧은 뉴스를 스크래핑하여 확장.

    Args:
        news_list: 뉴스 리스트
        min_body_length: 최소 본문 길이 (이 미만이면 스크래핑)

    Returns:
        확장된 뉴스 리스트
    """
    if not news_list:
        return []

    scraper = ContentScraper(
        config=ContentScraperConfig(min_body_length_for_scrape=min_body_length)
    )

    from dataclasses import replace
    result = []

    for news in news_list:
        body_len = len(news.body or "")

        if body_len >= min_body_length or not news.url:
            result.append(news)
            continue

        # 스크래핑 시도
        scraped = scraper.scrape(news.url)

        if scraped.success and len(scraped.full_body) > body_len:
            enriched = replace(news, body=scraped.full_body)
            result.append(enriched)
            logger.debug(
                "본문 확장: %s (%d -> %d자)",
                (news.title or "")[:30],
                body_len,
                len(scraped.full_body),
            )
        else:
            result.append(news)

    return result
