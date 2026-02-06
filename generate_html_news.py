#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""뉴스 생성 후 HTML 웹페이지로 출력 (원본 vs 생성 비교)"""

import os
import sys
import random
import time
import html as html_lib
from datetime import datetime
from typing import List, Dict, Optional, Any

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from search_news import search_news
from news_collector.generation import NewsGenerator, NewsFormat, GenerationMode
from news_collector.generation.content_assembler import ContentAssembler
from news_collector.ingestion.content_scraper import ContentScraper
from news_collector.utils.config_manager import ConfigManager


def load_test_keywords(config: ConfigManager) -> List[str]:
    """config에서 테스트 키워드 목록 로드"""
    keywords_section = config.get("test.keywords", {})
    all_keywords = []
    for category_keywords in keywords_section.values():
        if isinstance(category_keywords, list):
            all_keywords.extend(category_keywords)
    return all_keywords


def generate_one(
    keyword: str,
    generator: NewsGenerator,
    scraper: ContentScraper,
    config: ConfigManager,
) -> Optional[Dict[str, Any]]:
    """키워드로 뉴스 생성. 원본 뉴스 + 생성 뉴스 모두 반환"""
    search_limit = config.get("generation.search_limit", 5)
    scrape_min_body = config.get("generation.scrape_min_body_length", 150)
    max_scrape_imgs = config.get("generation.max_scrape_images", 3)

    news_list = search_news(keyword, limit=search_limit)
    if not news_list:
        return None

    # 원본 뉴스 저장
    originals = []
    for news in news_list:
        originals.append({
            "title": news.title or "",
            "body": news.body or "",
            "source": news.source_name or "",
            "url": news.url or "",
            "published": news.published_at.strftime("%Y-%m-%d %H:%M") if news.published_at else "",
        })

    # 본문 스크래핑
    enriched = []
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
        enriched.append(news)

    # 스크래핑 후 원본 업데이트 (본문 + 이미지, 유효성 필터링)
    img_filter = ContentAssembler()
    for i, news in enumerate(enriched):
        if i < len(originals):
            originals[i]["body_scraped"] = news.body or ""
            originals[i]["images"] = [
                img for img in (news.image_urls or [])
                if img_filter._is_valid_news_image(img)
            ]

    result = generator.generate(
        source_news=enriched,
        target_format=NewsFormat.STRAIGHT,
        mode=GenerationMode.SYNTHESIS,
        enrich_content=False,
        search_keywords=[keyword],
    )

    if not result.success or not result.generated_news:
        return None

    sources = result.sources or [n.source_name for n in enriched if n.source_name]
    # 출처명 → URL 매핑 (생성 뉴스 푸터에서 클릭 가능하도록)
    source_url_map = {}
    for n in enriched:
        if n.source_name and n.url:
            source_url_map[n.source_name] = n.url
    # 전체 수집된 이미지 (중복 제거 + 유효성 필터링)
    assembler = ContentAssembler()
    all_images = []
    seen_urls = set()
    for n in enriched:
        for img in (n.image_urls or []):
            if img and img not in seen_urls and assembler._is_valid_news_image(img):
                seen_urls.add(img)
                all_images.append(img)

    # 뉴스 유형 감지 (이미지 배치 결정용)
    news_type = assembler.detect_news_type(enriched)

    return {
        "keyword": keyword,
        "title": result.generated_news.title,
        "body": result.generated_news.body,
        "sources": list(set(sources))[:5],
        "source_urls": source_url_map,
        "char_count": result.generated_news.char_count,
        "gen_time_ms": result.generation_time_ms,
        "originals": originals,
        "images": all_images,
        "news_type": news_type,
    }


def esc(text: str) -> str:
    """HTML 이스케이프"""
    return html_lib.escape(text or "")


def build_html(articles: List[Dict[str, Any]]) -> str:
    """원본 vs 생성 비교 HTML"""
    now = datetime.now().strftime("%Y년 %m월 %d일 %H:%M")

    sections_html = ""
    for idx, art in enumerate(articles, 1):
        # 원본 뉴스 카드들
        orig_cards = ""
        for j, orig in enumerate(art["originals"], 1):
            body_text = orig.get("body_scraped", "") or orig["body"]
            body_preview = esc(body_text[:300]) + ("..." if len(body_text) > 300 else "")
            orig_images = orig.get("images", [])
            img_thumb = ""
            if orig_images:
                img_thumb = f'<img class="orig-thumb" src="{esc(orig_images[0])}" alt="" onerror="this.style.display=\'none\'">'
            img_count_badge = f'<span class="orig-img-count">{len(orig_images)}장</span>' if orig_images else ''
            orig_cards += f"""
                <div class="orig-card">
                    <div class="orig-num">{j}</div>
                    <div class="orig-content">
                        <div class="orig-title">
                            {'<a href="' + esc(orig['url']) + '" target="_blank" rel="noopener">' + esc(orig['title']) + '</a>' if orig.get('url') else esc(orig['title'])}
                        </div>
                        <div class="orig-body">{body_preview}</div>
                        <div class="orig-meta">
                            <span class="orig-source">{esc(orig['source'])}</span>
                            <span class="orig-date">{esc(orig['published'])}</span>
                            <span class="orig-len">{len(body_text)}자</span>
                            {img_count_badge}
                            {'<a href="' + esc(orig['url']) + '" target="_blank" rel="noopener" class="orig-link" title="' + esc(orig['url']) + '">원문</a>' if orig.get('url') else ''}
                        </div>
                    </div>
                    {img_thumb}
                </div>"""

        # 생성된 뉴스 본문 + 뉴스유형별 이미지 배치
        news_type = art.get("news_type", "standard")
        images = art.get("images", [])

        # 유형별 이미지 배치
        primary_image_html = ""
        gallery_html = ""
        inline_image_html = ""

        if news_type == "visual" and images:
            # 비주얼형: 대표 이미지 본문 위, 갤러리 본문 아래
            primary_image_html = f'<div class="gen-primary-image"><img src="{esc(images[0])}" alt="" onerror="this.parentElement.style.display=\'none\'"></div>'
            if len(images) > 1:
                gallery_imgs = "".join(
                    f'<img src="{esc(img)}" alt="" onerror="this.parentElement.removeChild(this)">'
                    for img in images[1:7]
                )
                gallery_html = f'<div class="gen-images"><div class="gen-images-title">갤러리 ({len(images) - 1}장)</div><div class="gen-images-grid">{gallery_imgs}</div></div>'
        elif news_type == "standard" and images:
            # 일반형: 본문 뒤 보조 이미지 1장
            inline_image_html = f'<div class="gen-inline-image"><img src="{esc(images[0])}" alt="" onerror="this.parentElement.style.display=\'none\'"></div>'
        elif news_type == "data" and images:
            # 데이터형: 차트/그래프 이미지 본문 위
            primary_image_html = f'<div class="gen-primary-image gen-chart-image"><img src="{esc(images[0])}" alt="" onerror="this.parentElement.style.display=\'none\'"></div>'

        gen_body = ""
        for p in art["body"].split("\n\n"):
            p = p.strip()
            # 출처 라인은 본문에서 제외 (footer에서 별도 표시)
            if p and not p.startswith("---") and not p.startswith("출처:"):
                gen_body += f"<p>{esc(p)}</p>\n"

        # 뉴스 유형 배지
        type_labels = {"standard": "일반", "visual": "비주얼", "data": "데이터"}
        type_badge = f'<span class="type-badge type-{news_type}">{type_labels.get(news_type, "일반")}</span>'

        source_urls = art.get("source_urls", {})
        sources_html = " ".join(
            f'<a href="{esc(source_urls[s])}" target="_blank" rel="noopener" class="tag tag-link">{esc(s)}</a>'
            if s in source_urls
            else f'<span class="tag">{esc(s)}</span>'
            for s in art["sources"]
        )

        sections_html += f"""
        <section class="compare-section">
            <div class="section-header">
                <span class="kw-badge">{esc(art['keyword'])}</span>
                {type_badge}
                <span class="section-meta">원본 {len(art['originals'])}건 → 생성 1건 | {art['char_count']}자 | {art['gen_time_ms']}ms</span>
            </div>

            <div class="compare-grid">
                <div class="panel panel-left">
                    <div class="panel-title">
                        <span class="dot dot-blue"></span> 원본 뉴스 ({len(art['originals'])}건)
                    </div>
                    <div class="orig-list">
                        {orig_cards}
                    </div>
                </div>

                <div class="panel-arrow">→</div>

                <div class="panel panel-right">
                    <div class="panel-title">
                        <span class="dot dot-green"></span> 생성된 뉴스
                    </div>
                    <div class="gen-card">
                        <h3>{esc(art['title'])}</h3>
                        {primary_image_html}
                        <div class="gen-body">
                            {gen_body}
                        </div>
                        {inline_image_html}
                        {gallery_html}
                        <div class="gen-footer">
                            출처: {sources_html}
                        </div>
                    </div>
                </div>
            </div>
        </section>"""

    total_originals = sum(len(a["originals"]) for a in articles)
    total_images = sum(len(a.get("images", [])) for a in articles)
    avg_chars = sum(a["char_count"] for a in articles) // len(articles) if articles else 0
    avg_time = sum(a["gen_time_ms"] for a in articles) // len(articles) if articles else 0

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NewsCollector - 원본 vs 생성 비교</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f0f2f5;
            color: #1a1a2e;
            line-height: 1.7;
        }}
        header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            color: white;
            padding: 2.5rem 1rem;
            text-align: center;
        }}
        header h1 {{ font-size: 2rem; font-weight: 700; margin-bottom: 0.3rem; }}
        header p {{ font-size: 0.9rem; opacity: 0.8; }}
        .container {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
        .stats-bar {{
            background: white; border-radius: 12px; padding: 1rem 1.5rem;
            margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            display: flex; justify-content: space-around; text-align: center;
        }}
        .stats-bar .stat .num {{ font-size: 1.5rem; font-weight: 700; color: #0f3460; }}
        .stats-bar .stat .label {{ font-size: 0.75rem; color: #888; }}
        .compare-section {{ margin-bottom: 2.5rem; }}
        .section-header {{
            display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;
        }}
        .kw-badge {{
            background: #0f3460; color: white; padding: 0.3rem 1rem;
            border-radius: 20px; font-size: 0.9rem; font-weight: 600;
        }}
        .section-meta {{ font-size: 0.8rem; color: #888; }}
        .compare-grid {{
            display: grid; grid-template-columns: 1fr 40px 1fr; gap: 0; align-items: start;
        }}
        .panel-arrow {{
            display: flex; align-items: center; justify-content: center;
            font-size: 1.5rem; color: #0f3460; font-weight: 700; padding-top: 3rem;
        }}
        .panel {{
            background: white; border-radius: 12px; padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .panel-title {{
            font-size: 0.85rem; font-weight: 700; color: #555;
            margin-bottom: 1rem; display: flex; align-items: center; gap: 0.4rem;
        }}
        .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
        .dot-blue {{ background: #3b82f6; }}
        .dot-green {{ background: #22c55e; }}
        .panel-left {{ border-top: 3px solid #3b82f6; }}
        .orig-card {{
            display: flex; gap: 0.8rem; padding: 0.8rem 0; border-bottom: 1px solid #f0f0f0;
        }}
        .orig-card:last-child {{ border-bottom: none; }}
        .orig-num {{
            width: 24px; height: 24px; background: #e8f0fe; color: #3b82f6;
            border-radius: 50%; display: flex; align-items: center; justify-content: center;
            font-size: 0.75rem; font-weight: 700; flex-shrink: 0; margin-top: 2px;
        }}
        .orig-title {{
            font-size: 0.85rem; font-weight: 600; color: #1a1a2e;
            margin-bottom: 0.3rem; line-height: 1.4;
        }}
        .orig-body {{ font-size: 0.78rem; color: #666; line-height: 1.5; margin-bottom: 0.3rem; }}
        .orig-meta {{ display: flex; gap: 0.5rem; font-size: 0.7rem; color: #aaa; }}
        .orig-source {{ background: #f5f5f5; padding: 0.1rem 0.4rem; border-radius: 3px; }}
        .orig-link {{
            background: #e8f0fe; color: #1a73e8; padding: 0.1rem 0.4rem;
            border-radius: 3px; text-decoration: none; font-weight: 500;
        }}
        .orig-link:hover {{ background: #d2e3fc; }}
        .orig-title a {{
            color: #1a1a2e; text-decoration: none; border-bottom: 1px solid transparent;
        }}
        .orig-title a:hover {{ color: #1a73e8; border-bottom-color: #1a73e8; }}
        .tag-link {{ text-decoration: none; cursor: pointer; }}
        .tag-link:hover {{ background: #dcfce7; }}
        .orig-thumb {{
            width: 60px; height: 60px; object-fit: cover; border-radius: 6px;
            flex-shrink: 0; align-self: center;
        }}
        .orig-img-count {{
            background: #fef3c7; color: #92400e; padding: 0.1rem 0.4rem;
            border-radius: 3px; font-size: 0.7rem;
        }}
        .type-badge {{
            padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600;
        }}
        .type-standard {{ background: #f3f4f6; color: #374151; }}
        .type-visual {{ background: #fef3c7; color: #92400e; }}
        .type-data {{ background: #dbeafe; color: #1e40af; }}
        .gen-primary-image {{
            margin-bottom: 1rem; border-radius: 8px; overflow: hidden;
        }}
        .gen-primary-image img {{
            width: 100%; max-height: 300px; object-fit: cover; display: block;
        }}
        .gen-chart-image img {{ max-height: 250px; object-fit: contain; background: #f9fafb; }}
        .gen-inline-image {{
            margin: 0.8rem 0; text-align: center;
        }}
        .gen-inline-image img {{
            max-width: 80%; max-height: 200px; object-fit: cover; border-radius: 6px;
        }}
        .gen-images {{ margin-top: 1rem; padding-top: 0.8rem; border-top: 1px solid #eee; }}
        .gen-images-title {{
            font-size: 0.8rem; font-weight: 600; color: #555; margin-bottom: 0.5rem;
        }}
        .gen-images-grid {{
            display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem;
        }}
        .gen-images-grid img {{
            width: 100%; height: 100px; object-fit: cover; border-radius: 6px;
            cursor: pointer; transition: transform 0.2s;
        }}
        .gen-images-grid img:hover {{ transform: scale(1.05); }}
        .panel-right {{ border-top: 3px solid #22c55e; }}
        .gen-card h3 {{
            font-size: 1.1rem; font-weight: 700; color: #1a1a2e;
            margin-bottom: 1rem; line-height: 1.5;
        }}
        .gen-body p {{ margin-bottom: 0.7rem; font-size: 0.9rem; color: #333; line-height: 1.8; }}
        .gen-footer {{
            margin-top: 1rem; padding-top: 0.8rem; border-top: 1px solid #eee;
            font-size: 0.8rem; color: #888;
        }}
        .tag {{
            background: #f0fdf4; color: #166534; padding: 0.1rem 0.5rem;
            border-radius: 4px; font-size: 0.75rem; margin-right: 0.2rem;
        }}
        @media (max-width: 768px) {{
            .compare-grid {{ grid-template-columns: 1fr; gap: 1rem; }}
            .panel-arrow {{ transform: rotate(90deg); padding: 0; }}
        }}
        footer.page-footer {{ text-align: center; padding: 2rem; color: #aaa; font-size: 0.8rem; }}
    </style>
</head>
<body>
    <header>
        <h1>NewsCollector</h1>
        <p>원본 뉴스 vs 생성 뉴스 비교 | {now}</p>
    </header>
    <div class="container">
        <div class="stats-bar">
            <div class="stat"><div class="num">{len(articles)}</div><div class="label">생성 기사</div></div>
            <div class="stat"><div class="num">{total_originals}</div><div class="label">원본 수집</div></div>
            <div class="stat"><div class="num">{total_images}</div><div class="label">수집 이미지</div></div>
            <div class="stat"><div class="num">{avg_chars}</div><div class="label">평균 글자수</div></div>
            <div class="stat"><div class="num">{avg_time}ms</div><div class="label">평균 생성시간</div></div>
        </div>
        {sections_html}
    </div>
    <footer class="page-footer">
        NewsCollector &copy; 2026
    </footer>
</body>
</html>"""


def main():
    config = ConfigManager()

    num = int(sys.argv[1]) if len(sys.argv) > 1 else config.get("test.default_count", 10)
    delay = config.get("generation.api_delay_seconds", 0.5)

    generator = NewsGenerator()
    scraper = ContentScraper()

    all_keywords = load_test_keywords(config)
    if not all_keywords:
        print("config에 test.keywords가 없습니다.")
        return

    keywords = random.sample(all_keywords, min(num, len(all_keywords)))
    articles: List[Dict[str, Any]] = []

    for i, kw in enumerate(keywords):
        print(f"[{i+1}/{num}] {kw} 생성 중...", end=" ", flush=True)
        art = generate_one(kw, generator, scraper, config)
        if art:
            articles.append(art)
            print(f"OK ({art['char_count']}자, 원본 {len(art['originals'])}건)")
        else:
            print("실패")
        time.sleep(delay)

    html = build_html(articles)
    out_path = os.path.join(os.path.dirname(__file__), "news_output.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n생성 완료: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
