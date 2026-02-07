"""종합 테스트 결과 웹 리포트 생성 - 원본 뉴스 vs 생성 뉴스 비교"""
import html as html_module
import sys
import time
from datetime import datetime
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 테스트 키워드
test_keywords = ['테슬라', '비트코인', 'AI', '삼성전자']

generator = NewsGenerator()
results = []

print("=" * 100)
print("뉴스 생성 테스트 진행 중...")
print("=" * 100)

for i, keyword in enumerate(test_keywords, 1):
    print(f"\n[{i}/{len(test_keywords)}] {keyword} 처리 중...")

    start_time = time.time()
    news_list = search_news(query=keyword, limit=5)

    if not news_list:
        print(f"  !! 뉴스 없음")
        continue

    result = generator.generate(
        source_news=news_list,
        target_format=None,
        style="neutral",
        enrich_content=True,
        search_keywords=[keyword]
    )

    generation_time = time.time() - start_time

    # 원본 뉴스 상세 정보 수집
    source_details = []
    for news in news_list:
        source_details.append({
            'title': news.title,
            'body': news.body or '',
            'source_name': news.source_name or '알 수 없음',
            'url': getattr(news, 'url', ''),
            'published_at': str(news.published_at)[:16] if news.published_at else '',
            'credibility_score': round(getattr(news, 'credibility_score', 0), 1),
            'quality_score': round(getattr(news, 'quality_score', 0), 1),
            'image_urls': getattr(news, 'image_urls', []) or [],
            'category': getattr(news, 'category', '') or '',
        })

    if result.generated_news:
        results.append({
            'keyword': keyword,
            'gen_title': result.generated_news.title,
            'gen_body': result.generated_news.body,
            'format': result.generated_news.format.value,
            'char_count': len(result.generated_news.body),
            'word_count': result.generated_news.word_count,
            'images': result.images if hasattr(result, 'images') and result.images else [],
            'sources': result.sources if hasattr(result, 'sources') and result.sources else [],
            'generation_time': f"{generation_time:.2f}",
            'source_news': source_details,
            'model_used': result.generated_news.model_used or 'template',
        })
        print(f"  OK: {result.generated_news.title[:50]}...")
    else:
        print(f"  FAIL: 생성 실패")


def esc(text):
    """HTML escape"""
    return html_module.escape(str(text)) if text else ''


def truncate(text, length=200):
    """텍스트 자르기"""
    if not text:
        return ''
    text = str(text)
    return text[:length] + '...' if len(text) > length else text


# ============================================================
# HTML 리포트 생성
# ============================================================
now = datetime.now()
total_source_articles = sum(len(r['source_news']) for r in results)
total_gen_chars = sum(r['char_count'] for r in results)
total_source_chars = sum(
    sum(len(s['body']) for s in r['source_news'])
    for r in results
)

html_content = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NewsCollector - 원본 vs 생성 비교 리포트</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans KR",sans-serif;background:#0a0e1a;color:#c9d1d9;line-height:1.6;padding:24px}}
.container{{max-width:1400px;margin:0 auto}}

/* Header */
.header{{text-align:center;padding:48px 40px;background:linear-gradient(135deg,#161b22 0%,#1c2333 100%);border-radius:16px;margin-bottom:28px;border:1px solid #30363d}}
.header h1{{font-size:36px;color:#f0f6fc;margin-bottom:6px}}
.header .sub{{color:#7d8590;font-size:15px}}

/* Stats */
.stats-grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:28px}}
.stat-box{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;text-align:center}}
.stat-box .num{{font-size:36px;font-weight:800;margin-bottom:4px}}
.stat-box .lbl{{font-size:12px;color:#7d8590;text-transform:uppercase;letter-spacing:1px}}
.c-blue .num{{color:#58a6ff}}
.c-green .num{{color:#3fb950}}
.c-purple .num{{color:#bc8cff}}
.c-yellow .num{{color:#d29922}}
.c-pink .num{{color:#f778ba}}

/* Comparison Section */
.compare-section{{margin-bottom:40px}}
.compare-header{{background:linear-gradient(135deg,#161b22,#1a2233);border:1px solid #30363d;border-radius:14px 14px 0 0;padding:28px 32px;display:flex;justify-content:space-between;align-items:center}}
.compare-header .kw{{font-size:13px;background:#30363d;color:#7d8590;padding:4px 14px;border-radius:20px}}
.compare-header h2{{font-size:24px;color:#f0f6fc;margin-top:8px}}
.compare-header .meta{{display:flex;gap:16px;font-size:13px;color:#7d8590;margin-top:6px}}
.compare-header .meta span{{display:flex;align-items:center;gap:4px}}

.compare-body{{border:1px solid #30363d;border-top:none;border-radius:0 0 14px 14px;overflow:hidden}}

/* Two-column layout */
.two-col{{display:grid;grid-template-columns:1fr 1fr;min-height:200px}}
.col-source{{background:#0d1117;border-right:2px solid #f7846450;padding:0}}
.col-generated{{background:#0d1117;padding:0}}

.col-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;padding:14px 24px;display:flex;align-items:center;gap:8px}}
.col-source .col-label{{background:#1a1208;color:#d29922;border-bottom:1px solid #30363d}}
.col-generated .col-label{{background:#0a1a0d;color:#3fb950;border-bottom:1px solid #30363d}}

/* Source articles list */
.source-article{{padding:20px 24px;border-bottom:1px solid #21262d}}
.source-article:last-child{{border-bottom:none}}
.source-article .sa-header{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}}
.source-article .sa-title{{font-size:15px;font-weight:600;color:#c9d1d9;line-height:1.4}}
.source-article .sa-meta{{font-size:11px;color:#7d8590;margin-bottom:8px;display:flex;gap:12px;flex-wrap:wrap}}
.source-article .sa-meta .badge{{background:#30363d;padding:2px 8px;border-radius:10px;font-size:10px}}
.source-article .sa-body{{font-size:13px;color:#8b949e;line-height:1.7;white-space:pre-wrap;word-break:break-all}}
.source-article .sa-img{{margin-top:10px}}
.source-article .sa-img img{{max-width:100%;max-height:180px;border-radius:8px;object-fit:cover}}

/* Generated result */
.gen-result{{padding:24px}}
.gen-title{{font-size:22px;font-weight:700;color:#f0f6fc;margin-bottom:16px;line-height:1.3;border-left:3px solid #3fb950;padding-left:14px}}
.gen-body{{font-size:14px;color:#c9d1d9;line-height:1.9;white-space:pre-wrap;word-break:break-all}}
.gen-images{{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}}
.gen-images img{{max-height:200px;border-radius:8px;object-fit:cover}}
.gen-sources{{margin-top:20px;padding-top:14px;border-top:1px solid #21262d}}
.gen-sources .gs-label{{font-size:11px;color:#7d8590;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}}
.gen-sources .gs-item{{font-size:12px;color:#58a6ff;padding:3px 0}}

/* Analysis chips */
.analysis-bar{{background:#161b22;border:1px solid #30363d;border-top:none;padding:16px 24px;display:flex;gap:20px;flex-wrap:wrap;font-size:13px}}
.chip{{display:flex;align-items:center;gap:6px;color:#7d8590}}
.chip .dot{{width:8px;height:8px;border-radius:50%}}
.dot-green{{background:#3fb950}}
.dot-yellow{{background:#d29922}}
.dot-blue{{background:#58a6ff}}
.dot-purple{{background:#bc8cff}}
.dot-red{{background:#f85149}}

/* Footer */
.footer{{text-align:center;padding:30px;color:#30363d;font-size:12px;margin-top:20px}}

@media(max-width:900px){{
    .stats-grid{{grid-template-columns:repeat(2,1fr)}}
    .two-col{{grid-template-columns:1fr}}
    .col-source{{border-right:none;border-bottom:2px solid #f7846450}}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
    <h1>NewsCollector Comparison Report</h1>
    <div class="sub">{now.strftime("%Y-%m-%d %H:%M")} | {len(results)} keywords | Source vs Generated</div>
</div>

<div class="stats-grid">
    <div class="stat-box c-blue"><div class="num">{len(results)}</div><div class="lbl">Keywords</div></div>
    <div class="stat-box c-yellow"><div class="num">{total_source_articles}</div><div class="lbl">Source Articles</div></div>
    <div class="stat-box c-green"><div class="num">{len(results)}</div><div class="lbl">Generated</div></div>
    <div class="stat-box c-purple"><div class="num">{total_gen_chars:,}</div><div class="lbl">Gen Chars</div></div>
    <div class="stat-box c-pink"><div class="num">{total_source_chars:,}</div><div class="lbl">Source Chars</div></div>
</div>
'''

# 각 키워드별 비교 섹션
for idx, r in enumerate(results, 1):
    source_total_chars = sum(len(s['body']) for s in r['source_news'])
    compression = round(r['char_count'] / source_total_chars * 100, 1) if source_total_chars > 0 else 0

    # 원본 기사 카드 HTML
    sources_html = ""
    for si, src in enumerate(r['source_news'], 1):
        src_img_html = ""
        if src['image_urls']:
            src_img_html = f'<div class="sa-img"><img src="{esc(src["image_urls"][0])}" loading="lazy" alt=""></div>'

        body_preview = esc(truncate(src['body'], 300))

        sources_html += f'''
        <div class="source-article">
            <div class="sa-title">[{si}] {esc(src['title'])}</div>
            <div class="sa-meta">
                <span class="badge">{esc(src['source_name'])}</span>
                <span>{esc(src['published_at'])}</span>
                <span>Credibility: {src['credibility_score']}</span>
                <span>Quality: {src['quality_score']}</span>
                <span>{len(src['body']):,}chars</span>
            </div>
            <div class="sa-body">{body_preview}</div>
            {src_img_html}
        </div>'''

    # 생성 결과 이미지
    gen_img_html = ""
    if r['images']:
        gen_img_html = '<div class="gen-images">'
        for img_url in r['images'][:3]:
            gen_img_html += f'<img src="{esc(img_url)}" loading="lazy" alt="">'
        gen_img_html += '</div>'

    # 생성 출처
    gen_sources_html = ""
    if r['sources']:
        gen_sources_html = '<div class="gen-sources"><div class="gs-label">Sources Used</div>'
        for gs in r['sources']:
            gen_sources_html += f'<div class="gs-item">{esc(gs)}</div>'
        gen_sources_html += '</div>'

    html_content += f'''
<div class="compare-section">
    <div class="compare-header">
        <div>
            <div class="kw">#{idx} {esc(r['keyword'])}</div>
            <h2>{esc(r['gen_title'])}</h2>
            <div class="meta">
                <span>Format: {esc(r['format'])}</span>
                <span>Model: {esc(r['model_used'])}</span>
                <span>Time: {r['generation_time']}s</span>
                <span>Sources: {len(r['source_news'])}</span>
            </div>
        </div>
    </div>

    <div class="compare-body">
        <div class="two-col">
            <div class="col-source">
                <div class="col-label">SOURCE ARTICLES ({len(r['source_news'])} articles, {source_total_chars:,} chars)</div>
                {sources_html}
            </div>
            <div class="col-generated">
                <div class="col-label">GENERATED RESULT ({r['char_count']:,} chars)</div>
                <div class="gen-result">
                    <div class="gen-title">{esc(r['gen_title'])}</div>
                    <div class="gen-body">{esc(r['gen_body'])}</div>
                    {gen_img_html}
                    {gen_sources_html}
                </div>
            </div>
        </div>
    </div>

    <div class="analysis-bar">
        <div class="chip"><span class="dot dot-green"></span> Gen: {r['char_count']:,} chars</div>
        <div class="chip"><span class="dot dot-yellow"></span> Source Total: {source_total_chars:,} chars</div>
        <div class="chip"><span class="dot dot-blue"></span> Ratio: {compression}%</div>
        <div class="chip"><span class="dot dot-purple"></span> Format: {esc(r['format'])}</div>
        <div class="chip"><span class="dot dot-red"></span> Images: {len(r['images'])}</div>
    </div>
</div>
'''

html_content += '''
<div class="footer">NewsCollector Comparison Report | Auto-generated</div>
</div>
</body>
</html>
'''

# 파일 저장
output_file = r"d:\Claude\NewsCollector\test_results_report.html"
with open(output_file, "w", encoding="utf-8") as f:
    f.write(html_content)

print("\n" + "=" * 100)
print(f"OK: 비교 리포트 생성 완료: {output_file}")
print("=" * 100)
print(f"\n  - Keywords: {len(results)}")
print(f"  - Source articles: {total_source_articles}")
print(f"  - Generated chars: {total_gen_chars:,}")
print(f"  - Source chars: {total_source_chars:,}")
print()
