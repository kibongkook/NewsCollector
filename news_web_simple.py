"""뉴스 웹 인터페이스 (간소화 버전)

유사 뉴스 그룹핑 + 대표 기사 선정 + 원본/생성 비교
검색 시 스크래핑으로 본문 확보
"""

import os
import sys
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, replace

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from flask import Flask, render_template_string, request, jsonify

from search_news import search_news
from news_collector.models.news import NewsWithScores
from news_collector.generation import NewsGenerator, NewsFormat, GenerationMode
from news_collector.ingestion.content_scraper import ContentScraper

app = Flask(__name__)

# 전역
news_cache: Dict[str, NewsWithScores] = {}
news_groups: List[Dict] = []
last_keywords: List[str] = []
scraper = ContentScraper()


@dataclass
class NewsGroup:
    """유사 뉴스 그룹"""
    representative: NewsWithScores
    members: List[NewsWithScores] = field(default_factory=list)
    similarity_score: float = 0.0


def enrich_news_with_scraping(news_list: List[NewsWithScores], max_scrape: int = 10) -> List[NewsWithScores]:
    """
    검색 결과에 스크래핑으로 본문 확보.

    RSS 본문이 짧으면 (150자 미만) 원본 URL에서 전문 스크래핑.
    """
    enriched = []
    scraped_count = 0

    for news in news_list:
        body_len = len(news.body or "")

        # 본문이 짧고 스크래핑 한도 내라면 스크래핑
        if body_len < 150 and news.url and scraped_count < max_scrape:
            try:
                result = scraper.scrape(news.url)
                if result.success and len(result.full_body) > body_len:
                    # 본문 + 이미지 업데이트
                    new_images = list(news.image_urls or [])
                    for img in result.images:
                        if img and img not in new_images:
                            # 이미지 필터링 적용
                            if is_relevant_news_image(img, news.title or ""):
                                new_images.append(img)

                    news = replace(
                        news,
                        body=result.full_body,
                        image_urls=new_images[:5],
                    )
                    scraped_count += 1
                    print(f"[스크래핑] {news.title[:30]}... ({body_len} -> {len(result.full_body)}자)")
            except Exception as e:
                print(f"[스크래핑 실패] {e}")

        enriched.append(news)

    return enriched


def is_relevant_news_image(img_url: str, title: str) -> bool:
    """뉴스와 관련 있는 이미지인지 확인 (content_scraper.py와 동기화)"""
    if not img_url:
        return False

    # HTTP로 시작해야 함
    if not img_url.startswith('http'):
        return False

    # 플레이스홀더 제외
    if '{{' in img_url or '}}' in img_url:
        return False

    url_lower = img_url.lower()

    # 제외할 확장자 (SVG, ICO, GIF 등)
    excluded_extensions = ('.svg', '.ico', '.cur', '.gif')
    path = url_lower.split('?')[0]
    if any(path.endswith(ext) for ext in excluded_extensions):
        return False

    # 제외 패턴 (광고, 아이콘, 로고 등) - content_scraper.py와 동일
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
        'promo', 'promotion', 'campaign', 'click', 'track',
        # SNS 공유 버튼
        'sns', 'share', 'view_sns', 'social',
        'kakao', 'facebook', 'twitter', 'naver_', 'google_',
        # 작은/썸네일/피드 이미지
        'thumb_s', 'thumb_xs', '_s.', '_xs.', '_t.',
        'small_', '_small', 'mini_', '_mini',
        '/feed/', 'feed_', '_feed',
        # 기자/관련기사 이미지
        'journalist', 'reporter', 'byline', 'author',
        'related_', '_related', 'recommend', 'sidebar',
        # 플레이어/비디오 UI
        'player', 'video_', '_video', 'play_', '_play',
        # 기타 UI
        'loading', 'spinner', 'placeholder', 'default',
        'pixel', 'tracker', 'spacer', 'blank', 'transparent',
        '1x1', '1px', 'sprite', 'emoji', 'avatar', 'profile',
        'nav_', 'menu_', 'comment', 'reply', 'like', 'dislike',
    ]

    for pattern in exclude_patterns:
        if pattern in url_lower:
            return False

    # 크기 추정 (URL에 크기 정보가 있는 경우)
    size_pattern = r'[_-](\d+)x(\d+)'
    size_match = re.search(size_pattern, url_lower)
    if size_match:
        width, height = int(size_match.group(1)), int(size_match.group(2))
        if width < 150 or height < 100:
            return False

    # 유효한 이미지 확장자
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    has_valid_ext = any(path.endswith(ext) for ext in valid_extensions)

    # 이미지 호스트 체크
    image_hosts = ['imgnews', 'img', 'image', 'photo', 'cdn', 'media', 'pimg', 'dimg']
    is_image_host = any(host in url_lower for host in image_hosts)

    return has_valid_ext or is_image_host


def calculate_quality_score(news: NewsWithScores) -> float:
    """기사 품질 점수 계산"""
    score = 0.0

    body_len = len(news.body or "")
    if body_len >= 500:
        score += 40
    elif body_len >= 300:
        score += 30
    elif body_len >= 100:
        score += 20
    else:
        score += body_len / 10

    score += (news.final_score or 0) * 20

    if news.image_urls:
        score += min(len(news.image_urls) * 5, 15)

    major_sources = ['연합뉴스', '한겨레', '조선일보', '중앙일보', '동아일보',
                     '매일경제', '한국경제', 'KBS', 'MBC', 'SBS', 'YTN', 'BBC']
    if any(s in (news.source_name or '') for s in major_sources):
        score += 10

    return score


def title_similarity(title1: str, title2: str) -> float:
    """제목 기반 유사도 (Jaccard)"""
    words1 = set(re.findall(r'[가-힣a-zA-Z]{2,}', title1.lower()))
    words2 = set(re.findall(r'[가-힣a-zA-Z]{2,}', title2.lower()))

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0


def group_similar_news(
    news_list: List[NewsWithScores],
    similarity_threshold: float = 0.4,
) -> List[NewsGroup]:
    """
    유사 뉴스 그룹핑 (제목 기반).
    """
    if not news_list:
        return []

    groups: List[NewsGroup] = []
    assigned = set()

    sorted_news = sorted(news_list, key=calculate_quality_score, reverse=True)

    for news in sorted_news:
        if news.id in assigned:
            continue

        group = NewsGroup(representative=news, members=[news])
        assigned.add(news.id)

        for other in sorted_news:
            if other.id in assigned:
                continue

            # 제목 기반 유사도
            similarity = title_similarity(news.title or "", other.title or "")

            if similarity >= similarity_threshold:
                group.members.append(other)
                group.similarity_score = max(group.similarity_score, similarity)
                assigned.add(other.id)

        groups.append(group)

    groups.sort(key=lambda g: (len(g.members), calculate_quality_score(g.representative)), reverse=True)

    return groups


def detect_news_type(news: NewsWithScores) -> str:
    """뉴스 유형 감지"""
    if news.image_urls and len(news.image_urls) >= 2:
        return "visual"

    visual_keywords = ['포토', '화보', '현장', '사진', '갤러리', '직캠', '공개', '포착']
    text = f"{news.title or ''}"
    if any(kw in text for kw in visual_keywords):
        return "visual"

    return "standard"


# HTML 템플릿
HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NewsCollector</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Malgun Gothic', sans-serif;
            background: #f5f5f5;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }
        .header h1 { font-size: 1.8em; margin-bottom: 5px; }
        .header p { opacity: 0.9; font-size: 0.9em; }

        .search-bar {
            background: white;
            padding: 15px 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            display: flex;
            gap: 10px;
            justify-content: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .search-bar input {
            padding: 12px 20px;
            border: 2px solid #667eea;
            border-radius: 25px;
            font-size: 1em;
            width: 300px;
        }
        .search-bar button {
            padding: 12px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 1em;
            cursor: pointer;
        }

        .main { max-width: 1400px; margin: 0 auto; padding: 20px; }

        .news-group {
            background: white;
            border-radius: 12px;
            margin-bottom: 15px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }
        .group-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 15px 20px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .group-header:hover { background: #f8f9ff; }
        .group-header.selected { background: #e8edff; border-left: 4px solid #667eea; }

        .group-representative { flex: 1; }
        .group-representative .title {
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
            font-size: 1.05em;
            line-height: 1.4;
        }
        .group-representative .preview {
            color: #666;
            font-size: 0.9em;
            line-height: 1.5;
            margin-bottom: 8px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .group-representative .meta {
            font-size: 0.85em;
            color: #888;
        }
        .group-badge {
            background: #667eea;
            color: white;
            padding: 4px 10px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: 600;
            margin-left: 10px;
            white-space: nowrap;
        }
        .group-badge.single { background: #aaa; }

        .group-members {
            display: none;
            background: #fafafa;
            border-top: 1px solid #eee;
        }
        .group-members.expanded { display: block; }
        .member-item {
            padding: 12px 20px 12px 40px;
            border-bottom: 1px solid #eee;
            cursor: pointer;
            transition: background 0.2s;
        }
        .member-item:hover { background: #f0f4ff; }
        .member-item:last-child { border-bottom: none; }
        .member-item .title { font-size: 0.95em; color: #555; margin-bottom: 3px; }
        .member-item .meta { font-size: 0.8em; color: #999; }
        .member-item.is-representative { background: #f0f4ff; }
        .member-item.is-representative .title::before { content: "★ "; color: #667eea; }

        .expand-toggle {
            color: #667eea;
            font-size: 0.85em;
            cursor: pointer;
            padding: 8px 20px;
            text-align: center;
            background: #f5f7ff;
        }

        .comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 20px;
        }
        @media (max-width: 900px) { .comparison { grid-template-columns: 1fr; } }

        .panel {
            background: white;
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }
        .panel-header {
            padding: 15px 20px;
            font-weight: 700;
            font-size: 1.1em;
        }
        .panel.original .panel-header { background: #e3f2fd; color: #1976d2; }
        .panel.generated .panel-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }

        .panel-content { padding: 20px; }
        .article-title {
            font-size: 1.25em;
            font-weight: 700;
            color: #333;
            margin-bottom: 15px;
            line-height: 1.4;
        }

        .article-body {
            line-height: 1.9;
            color: #444;
            font-size: 0.95em;
        }
        .article-body p { margin-bottom: 12px; }

        .layout-standard .article-image-section {
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px dashed #ddd;
        }
        .layout-visual .article-image-section { margin-bottom: 20px; }

        .article-image {
            width: 100%;
            max-height: 350px;
            object-fit: cover;
            border-radius: 10px;
            margin-bottom: 10px;
        }

        .article-gallery {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
            gap: 8px;
            margin-top: 10px;
        }
        .article-gallery img {
            width: 100%;
            height: 80px;
            object-fit: cover;
            border-radius: 6px;
        }

        .article-meta {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #eee;
            font-size: 0.85em;
            color: #888;
        }
        .article-sources {
            background: #f5f5f5;
            padding: 10px 15px;
            border-radius: 8px;
            margin-top: 10px;
        }

        .stats { display: flex; gap: 20px; margin-top: 10px; flex-wrap: wrap; }
        .stat { display: flex; align-items: center; gap: 5px; }
        .stat-label { color: #888; }
        .stat-value { font-weight: 600; color: #667eea; }

        .news-type-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75em;
            margin-left: 8px;
        }
        .news-type-badge.standard { background: #e3f2fd; color: #1976d2; }
        .news-type-badge.visual { background: #fff3e0; color: #ef6c00; }

        .loading { text-align: center; padding: 50px; color: #888; }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .empty { text-align: center; padding: 50px; color: #888; }
        .empty-icon { font-size: 3em; margin-bottom: 10px; }

        /* 생성된 뉴스 구조화 스타일 */
        .gen-section { margin-bottom: 15px; }
        .gen-section-label {
            font-size: 0.75em;
            color: #667eea;
            font-weight: 600;
            margin-bottom: 5px;
            text-transform: uppercase;
        }
        .gen-lead {
            font-size: 1.05em;
            font-weight: 500;
            color: #333;
            line-height: 1.7;
            border-left: 3px solid #667eea;
            padding-left: 12px;
            margin-bottom: 15px;
        }
        .gen-body { line-height: 1.9; color: #444; }
        .gen-closing {
            font-style: italic;
            color: #666;
            padding-top: 10px;
            border-top: 1px solid #eee;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>NewsCollector</h1>
        <p>검색 시 자동 스크래핑으로 충실한 원본 확보 | 유사 뉴스 그룹화 | AI 뉴스 생성</p>
    </div>

    <div class="search-bar">
        <input type="text" id="keyword" placeholder="검색어 입력 (예: 경제, 반도체, 연예)" value="경제">
        <button onclick="searchNews()">검색</button>
    </div>

    <div class="main">
        <div id="news-groups">
            <div class="empty">
                <div class="empty-icon">📰</div>
                <p>검색어를 입력하고 검색 버튼을 누르세요</p>
            </div>
        </div>

        <div id="comparison" class="comparison" style="display: none;">
            <div class="panel original">
                <div class="panel-header">📄 원본 뉴스</div>
                <div class="panel-content" id="original-content"></div>
            </div>
            <div class="panel generated">
                <div class="panel-header">✨ AI 생성 뉴스</div>
                <div class="panel-content" id="generated-content"></div>
            </div>
        </div>
    </div>

    <script>
        let groupsData = [];
        let selectedGroupIdx = null;

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function searchNews() {
            const keyword = document.getElementById('keyword').value.trim();
            if (!keyword) return alert('검색어를 입력하세요');

            document.getElementById('news-groups').innerHTML = '<div class="loading"><div class="spinner"></div><p>뉴스 검색 + 스크래핑 중... (10초 소요)</p></div>';
            document.getElementById('comparison').style.display = 'none';

            try {
                const res = await fetch('/api/search?keyword=' + encodeURIComponent(keyword) + '&limit=12');
                const data = await res.json();

                if (data.success && data.groups && data.groups.length > 0) {
                    groupsData = data.groups;
                    renderNewsGroups();
                } else {
                    document.getElementById('news-groups').innerHTML = '<div class="empty"><div class="empty-icon">🔍</div><p>검색 결과가 없습니다</p></div>';
                }
            } catch (e) {
                document.getElementById('news-groups').innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div><p>검색 중 오류 발생</p></div>';
            }
        }

        function renderNewsGroups() {
            let html = '';

            groupsData.forEach((group, idx) => {
                const rep = group.representative;
                const memberCount = group.members.length;
                const isSelected = idx === selectedGroupIdx;
                const bodyPreview = (rep.body || '').substring(0, 150);

                html += `
                    <div class="news-group">
                        <div class="group-header ${isSelected ? 'selected' : ''}" onclick="selectGroup(${idx})">
                            <div class="group-representative">
                                <div class="title">${escapeHtml(rep.title)}</div>
                                <div class="preview">${escapeHtml(bodyPreview)}${bodyPreview.length >= 150 ? '...' : ''}</div>
                                <div class="meta">
                                    ${rep.source_name || '알 수 없음'} · 본문 ${(rep.body || '').length}자 · 이미지 ${(rep.image_urls || []).length}개
                                </div>
                            </div>
                            <span class="group-badge ${memberCount === 1 ? 'single' : ''}">${memberCount}개 기사</span>
                        </div>
                        ${memberCount > 1 ? `
                            <div class="expand-toggle" onclick="toggleGroup(event, ${idx})">
                                ▼ 유사 기사 ${memberCount - 1}개 더보기
                            </div>
                            <div class="group-members" id="group-members-${idx}">
                                ${group.members.map(m => `
                                    <div class="member-item ${m.id === rep.id ? 'is-representative' : ''}"
                                         onclick="selectMember(${idx}, '${m.id}')">
                                        <div class="title">${escapeHtml(m.title)}</div>
                                        <div class="meta">${m.source_name || ''} · ${(m.body || '').length}자</div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                `;
            });

            document.getElementById('news-groups').innerHTML = html;
        }

        function toggleGroup(event, idx) {
            event.stopPropagation();
            const members = document.getElementById('group-members-' + idx);
            const toggle = event.target;
            if (members.classList.contains('expanded')) {
                members.classList.remove('expanded');
                toggle.innerHTML = `▼ 유사 기사 ${groupsData[idx].members.length - 1}개 더보기`;
            } else {
                members.classList.add('expanded');
                toggle.innerHTML = '▲ 접기';
            }
        }

        function selectGroup(idx) {
            selectedGroupIdx = idx;
            const rep = groupsData[idx].representative;
            renderNewsGroups();
            showComparison(rep, groupsData[idx].members);
        }

        function selectMember(groupIdx, newsId) {
            selectedGroupIdx = groupIdx;
            const member = groupsData[groupIdx].members.find(m => m.id === newsId);
            if (member) {
                renderNewsGroups();
                showComparison(member, groupsData[groupIdx].members);
            }
        }

        async function showComparison(news, groupMembers) {
            const newsType = news.news_type || 'standard';
            const layoutClass = 'layout-' + newsType;

            // 원본 표시
            let originalHtml = `<div class="${layoutClass}">`;
            originalHtml += `<div class="article-title">${escapeHtml(news.title)}</div>`;

            if (newsType === 'visual' && news.image_urls && news.image_urls.length > 0) {
                originalHtml += buildImageSection(news.image_urls);
            }

            // 본문을 문단으로 분리
            const bodyParagraphs = (news.body || '(본문 없음)').split(/\\n\\n+/).filter(p => p.trim());
            originalHtml += '<div class="article-body">';
            bodyParagraphs.forEach(p => {
                originalHtml += `<p>${escapeHtml(p.trim())}</p>`;
            });
            originalHtml += '</div>';

            if (newsType === 'standard' && news.image_urls && news.image_urls.length > 0) {
                originalHtml += buildImageSection(news.image_urls);
            }

            originalHtml += `
                <div class="article-meta">
                    <div class="article-sources">📰 출처: ${escapeHtml(news.source_name || '알 수 없음')}</div>
                    <div class="stats">
                        <div class="stat"><span class="stat-label">본문</span><span class="stat-value">${(news.body || '').length}자</span></div>
                        <div class="stat"><span class="stat-label">이미지</span><span class="stat-value">${(news.image_urls || []).length}개</span></div>
                    </div>
                </div>
            </div>`;

            document.getElementById('original-content').innerHTML = originalHtml;
            document.getElementById('generated-content').innerHTML = '<div class="loading"><div class="spinner"></div><p>AI가 뉴스를 생성 중...</p></div>';
            document.getElementById('comparison').style.display = 'grid';

            try {
                const res = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        news_id: news.id,
                        group_member_ids: groupMembers.map(m => m.id),
                        format: 'straight',
                        enrich_content: false  // 이미 스크래핑됨
                    })
                });
                const data = await res.json();

                if (data.success && data.generated) {
                    const gen = data.generated;
                    const genType = gen.news_type || 'standard';

                    let genHtml = `<div class="layout-${genType}">`;
                    genHtml += `<div class="article-title">${escapeHtml(gen.title)}</div>`;

                    if (genType === 'visual' && gen.images && gen.images.length > 0) {
                        genHtml += buildImageSection(gen.images);
                    }

                    // 구조화된 본문 표시
                    if (gen.sections) {
                        genHtml += '<div class="article-body">';
                        if (gen.sections.lead) {
                            genHtml += `<div class="gen-lead">${escapeHtml(gen.sections.lead)}</div>`;
                        }
                        if (gen.sections.body) {
                            genHtml += `<div class="gen-body">${escapeHtml(gen.sections.body).split(/\\n+/).map(p => '<p>' + p + '</p>').join('')}</div>`;
                        }
                        if (gen.sections.closing) {
                            genHtml += `<div class="gen-closing">${escapeHtml(gen.sections.closing)}</div>`;
                        }
                        genHtml += '</div>';
                    } else {
                        // 일반 본문
                        const genParagraphs = (gen.body || '').split(/\\n\\n+/).filter(p => p.trim());
                        genHtml += '<div class="article-body">';
                        genParagraphs.forEach(p => {
                            genHtml += `<p>${escapeHtml(p.trim())}</p>`;
                        });
                        genHtml += '</div>';
                    }

                    if (genType === 'standard' && gen.images && gen.images.length > 0) {
                        genHtml += buildImageSection(gen.images);
                    }

                    genHtml += `
                        <div class="article-meta">
                            <div class="article-sources">📰 출처: ${gen.sources ? gen.sources.map(s => escapeHtml(s)).join(', ') : '없음'}</div>
                            <div class="stats">
                                <div class="stat"><span class="stat-label">본문</span><span class="stat-value">${gen.char_count}자</span></div>
                                <div class="stat"><span class="stat-label">생성시간</span><span class="stat-value">${gen.generation_time_ms}ms</span></div>
                                <div class="stat"><span class="stat-label">소스</span><span class="stat-value">${gen.source_count}개</span></div>
                            </div>
                        </div>
                    </div>`;

                    document.getElementById('generated-content').innerHTML = genHtml;
                } else {
                    document.getElementById('generated-content').innerHTML = `<div class="empty"><div class="empty-icon">⚠️</div><p>생성 실패: ${escapeHtml(data.error || '알 수 없음')}</p></div>`;
                }
            } catch (e) {
                document.getElementById('generated-content').innerHTML = `<div class="empty"><div class="empty-icon">⚠️</div><p>오류: ${e.message}</p></div>`;
            }
        }

        function buildImageSection(images) {
            if (!images || images.length === 0) return '';
            let html = '<div class="article-image-section">';
            html += `<img class="article-image" src="${escapeHtml(images[0])}" onerror="this.style.display='none'" alt="">`;
            if (images.length > 1) {
                html += '<div class="article-gallery">';
                images.slice(1, 5).forEach(img => {
                    html += `<img src="${escapeHtml(img)}" onerror="this.style.display='none'" alt="">`;
                });
                html += '</div>';
            }
            html += '</div>';
            return html;
        }

        document.getElementById('keyword').addEventListener('keypress', e => {
            if (e.key === 'Enter') searchNews();
        });

        window.onload = () => searchNews();
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/search")
def api_search():
    global news_cache, news_groups, last_keywords

    keyword = request.args.get("keyword", "").strip()
    limit = int(request.args.get("limit", 12))

    if not keyword:
        return jsonify({"success": False, "error": "키워드 필요", "groups": []})

    try:
        last_keywords = [keyword]
        results = search_news(keyword, limit=limit)

        # 스크래핑으로 본문 확보
        print(f"\n=== '{keyword}' 검색 결과 {len(results)}건 스크래핑 시작 ===")
        results = enrich_news_with_scraping(results, max_scrape=10)

        news_cache.clear()
        for news in results:
            news_cache[news.id] = news

        # 그룹핑
        groups = group_similar_news(results)

        # JSON 변환
        groups_json = []
        for group in groups:
            rep = group.representative
            rep_type = detect_news_type(rep)

            members_json = []
            for m in group.members:
                m_type = detect_news_type(m)
                members_json.append({
                    "id": m.id,
                    "title": m.title,
                    "body": m.body,
                    "url": m.url,
                    "source_name": m.source_name,
                    "published_at": m.published_at.isoformat() if m.published_at else None,
                    "final_score": m.final_score,
                    "quality_score": calculate_quality_score(m),
                    "image_urls": list(m.image_urls or []),
                    "news_type": m_type,
                })

            groups_json.append({
                "representative": {
                    "id": rep.id,
                    "title": rep.title,
                    "body": rep.body,
                    "url": rep.url,
                    "source_name": rep.source_name,
                    "published_at": rep.published_at.isoformat() if rep.published_at else None,
                    "final_score": rep.final_score,
                    "quality_score": calculate_quality_score(rep),
                    "image_urls": list(rep.image_urls or []),
                    "news_type": rep_type,
                },
                "members": members_json,
                "similarity_score": group.similarity_score,
            })

        return jsonify({
            "success": True,
            "count": len(results),
            "group_count": len(groups),
            "groups": groups_json,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e), "groups": []})


@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        data = request.get_json()
        news_id = data.get("news_id")
        group_member_ids = data.get("group_member_ids", [])
        enrich = data.get("enrich_content", False)  # 이미 스크래핑됨

        if news_id not in news_cache:
            return jsonify({"success": False, "error": "뉴스를 찾을 수 없습니다"})

        source_news = []
        for mid in group_member_ids:
            if mid in news_cache:
                source_news.append(news_cache[mid])

        if not source_news:
            source_news = [news_cache[news_id]]

        generator = NewsGenerator()
        result = generator.generate(
            source_news=source_news,
            target_format=NewsFormat.STRAIGHT,
            mode=GenerationMode.SYNTHESIS,
            enrich_content=enrich,
            search_keywords=last_keywords,
        )

        if result.success and result.generated_news:
            gen = result.generated_news

            news_type = "standard"
            if result.images and len(result.images) >= 2:
                news_type = "visual"

            # 이미지 필터링
            filtered_images = []
            if result.images:
                for img in result.images:
                    if is_relevant_news_image(img, gen.title or ""):
                        filtered_images.append(img)
                        if len(filtered_images) >= 5:
                            break

            # 섹션 분리 (있으면)
            sections = None
            body_text = gen.body or ""

            # 본문에서 섹션 추출 시도
            if "\n\n" in body_text:
                parts = body_text.split("\n\n")
                if len(parts) >= 2:
                    sections = {
                        "lead": parts[0].strip(),
                        "body": "\n\n".join(parts[1:-1]).strip() if len(parts) > 2 else "",
                        "closing": parts[-1].strip() if len(parts) > 1 else "",
                    }

            return jsonify({
                "success": True,
                "generated": {
                    "id": gen.id,
                    "title": gen.title,
                    "body": gen.body,
                    "char_count": gen.char_count,
                    "generation_time_ms": result.generation_time_ms,
                    "source_count": len(source_news),
                    "sources": result.sources or [n.source_name for n in source_news if n.source_name],
                    "images": filtered_images,
                    "news_type": news_type,
                    "sections": sections,
                }
            })
        else:
            return jsonify({"success": False, "error": result.error_message or "생성 실패"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  NewsCollector 웹 인터페이스")
    print("=" * 60)
    print("\n  http://localhost:9001")
    print("  - 검색 시 자동 스크래핑 (10개까지)")
    print("  - 제목 기반 유사 뉴스 그룹화")
    print("  - 이미지 필터링 강화")
    print("\n  종료: Ctrl+C\n")
    app.run(host="0.0.0.0", port=9001, debug=True)
