"""뉴스 수집 vs 생성 비교 페이지 생성"""
import sys
import os
import json
from datetime import datetime

# 환경 변수 설정
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, "d:\\Claude\\NewsCollector")

from search_news import search_news
from news_collector.generation import NewsGenerator

def generate_comparison_html(keyword: str):
    """수집된 뉴스와 생성된 뉴스를 비교하는 HTML 생성"""

    print(f"[1/3] 뉴스 검색 중: '{keyword}'...")
    collected_news = search_news(query=keyword, limit=5)

    print(f"[2/3] 뉴스 생성 중...")
    generator = NewsGenerator()
    result = generator.generate(
        source_news=collected_news,
        target_format=None,
        style="neutral"
    )

    print(f"[3/3] HTML 생성 중...")

    # HTML 생성
    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>뉴스 수집 vs 생성 비교 - {keyword}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 20px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header h1 {{
            font-size: 2rem;
            margin-bottom: 10px;
        }}
        .header p {{
            opacity: 0.9;
        }}
        .container {{
            max-width: 1600px;
            margin: 30px auto;
            padding: 0 20px;
        }}
        .comparison-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }}
        @media (max-width: 1200px) {{
            .comparison-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        .panel {{
            background: white;
            border-radius: 10px;
            padding: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .panel h2 {{
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
            font-size: 1.5rem;
        }}
        .news-item {{
            background: #f8f9fa;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .news-item h3 {{
            color: #333;
            font-size: 1.1rem;
            margin-bottom: 10px;
        }}
        .news-item .meta {{
            color: #666;
            font-size: 0.85rem;
            margin-bottom: 10px;
        }}
        .news-item .body {{
            color: #555;
            line-height: 1.8;
            white-space: pre-wrap;
        }}
        .news-item .images {{
            margin-top: 15px;
        }}
        .news-item .images img {{
            max-width: 150px;
            max-height: 100px;
            margin: 5px;
            border-radius: 5px;
            object-fit: cover;
        }}
        .generated-news {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .generated-news h2 {{
            color: #764ba2;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #764ba2;
            font-size: 1.8rem;
        }}
        .generated-news .title {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
        }}
        .generated-news .body {{
            color: #444;
            line-height: 1.9;
            font-size: 1.05rem;
            white-space: pre-wrap;
            margin-bottom: 20px;
        }}
        .generated-news .images {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .generated-news .images img {{
            width: 100%;
            height: 150px;
            object-fit: cover;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stats {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }}
        .stat-item {{
            text-align: center;
        }}
        .stat-item .label {{
            font-size: 0.9rem;
            opacity: 0.9;
            margin-bottom: 5px;
        }}
        .stat-item .value {{
            font-size: 1.8rem;
            font-weight: bold;
        }}
        .badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            margin: 5px 5px 5px 0;
        }}
        .badge-success {{
            background: #d4edda;
            color: #155724;
        }}
        .badge-info {{
            background: #d1ecf1;
            color: #0c5460;
        }}
        .badge-warning {{
            background: #fff3cd;
            color: #856404;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 뉴스 수집 vs 생성 비교</h1>
        <p>키워드: <strong>{keyword}</strong> | 생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>

    <div class="container">
        <!-- 통계 -->
        <div class="stats">
            <div class="stat-item">
                <div class="label">수집된 뉴스</div>
                <div class="value">{len(collected_news)}</div>
            </div>
            <div class="stat-item">
                <div class="label">생성된 뉴스 길이</div>
                <div class="value">{len(result.generated_news.body if result.generated_news else '')}자</div>
            </div>
            <div class="stat-item">
                <div class="label">생성 성공</div>
                <div class="value">{'✓' if result.success else '✗'}</div>
            </div>
            <div class="stat-item">
                <div class="label">이미지 개수</div>
                <div class="value">{len(result.images)}</div>
            </div>
        </div>

        <!-- 비교 그리드 -->
        <div class="comparison-grid">
            <!-- 좌측: 수집된 뉴스들 -->
            <div class="panel">
                <h2>📰 수집된 원본 뉴스 ({len(collected_news)}개)</h2>
"""

    # 수집된 뉴스 추가
    for idx, news in enumerate(collected_news, 1):
        images_html = ""
        if news.image_urls:
            imgs = [f'<img src="{url}" alt="Image {i+1}" onerror="this.style.display=\'none\'">'
                   for i, url in enumerate(news.image_urls[:5])]
            images_html = f'<div class="images">{"".join(imgs)}</div>'

        html += f"""
                <div class="news-item">
                    <h3>{idx}. {news.title or 'No Title'}</h3>
                    <div class="meta">
                        <span class="badge badge-info">{news.source_name}</span>
                        <span class="badge badge-success">{len(news.image_urls)} images</span>
                        <span class="badge badge-warning">{len(news.body or '')} chars</span>
                    </div>
                    <div class="body">{(news.body or '')[:300]}{'...' if len(news.body or '') > 300 else ''}</div>
                    {images_html}
                </div>
"""

    html += """
            </div>

            <!-- 우측: 생성된 뉴스 -->
            <div class="panel">
                <h2>✨ AI가 생성한 최종 뉴스</h2>
                <div class="generated-news" style="background: #f8f9fa; padding: 25px;">
"""

    # 생성된 뉴스 추가
    if result.generated_news:
        title = result.generated_news.title or 'No Title'
        body = result.generated_news.body or 'No Body'
    else:
        title = 'Generation Failed'
        body = result.error_message

    images_html = ""
    if result.images:
        imgs = [f'<img src="{url}" alt="Generated Image {i+1}" onerror="this.style.display=\'none\'">'
               for i, url in enumerate(result.images)]
        images_html = f'<div class="images">{"".join(imgs)}</div>'

    html += f"""
                    <div class="title">{title}</div>
                    <div class="body">{body}</div>
                    {images_html}
                </div>
            </div>
        </div>

        <!-- 전체 생성된 뉴스 (하단) -->
        <div class="generated-news">
            <h2>📝 생성된 뉴스 전문</h2>
            <div class="title">{title}</div>
            <div class="body">{body}</div>
            {images_html}
        </div>
    </div>
</body>
</html>
"""

    # HTML 파일 저장
    filename = f"news_comparison_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ 비교 페이지 생성 완료: {filename}")
    return filename

if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "인공지능"
    filename = generate_comparison_html(keyword)

    # 브라우저에서 열기
    import os
    os.system(f'start "{filename}"')
