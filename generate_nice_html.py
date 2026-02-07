"""개선된 HTML 뉴스 생성"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 여러 키워드로 테스트
keywords = ['테슬라', '삼성전자']

generator = NewsGenerator()

html_parts = []

for keyword in keywords:
    news_list = search_news(query=keyword, limit=3)

    if not news_list:
        continue

    result = generator.generate(
        source_news=news_list,
        target_format=None,
        style="neutral",
        enrich_content=True,
        search_keywords=[keyword]
    )

    if result.generated_news:
        # 이미지 HTML 생성
        images_html = ""
        if result.images:
            images_html = '<div class="images">\n'
            for img in result.images:
                images_html += f'  <img src="{img}" alt="뉴스 이미지" loading="lazy">\n'
            images_html += '</div>\n'

        # 뉴스 카드 생성
        body_formatted = result.generated_news.body.replace('\n', '<br>\n')

        html_parts.append(f'''
<article class="news-card">
    <h2>{result.generated_news.title}</h2>
    {images_html}
    <div class="content">
        {body_formatted}
    </div>
    <div class="meta">
        <span>포맷: {result.generated_news.format.value}</span> |
        <span>본문 길이: {len(result.generated_news.body)}자</span> |
        <span>이미지: {len(result.images) if result.images else 0}개</span>
    </div>
</article>
''')

# 최종 HTML 생성
final_html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>생성된 뉴스</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.8;
            background: #f5f5f5;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .news-card {{
            background: white;
            margin-bottom: 30px;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .news-card h2 {{
            font-size: 28px;
            color: #222;
            margin-bottom: 24px;
            line-height: 1.4;
        }}
        .images {{
            margin: 24px 0;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
        }}
        .images img {{
            width: 100%;
            height: auto;
            border-radius: 4px;
            object-fit: cover;
            max-height: 400px;
        }}
        .content {{
            color: #333;
            font-size: 16px;
            line-height: 1.8;
            margin-bottom: 24px;
        }}
        .meta {{
            padding-top: 16px;
            border-top: 1px solid #eee;
            font-size: 14px;
            color: #666;
        }}
        .meta span {{
            margin-right: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1 style="text-align: center; margin-bottom: 40px; color: #333;">AI 생성 뉴스</h1>
        {''.join(html_parts)}
    </div>
</body>
</html>'''

# 파일 저장
with open("news_output_nice.html", "w", encoding="utf-8") as f:
    f.write(final_html)

print("✓ HTML 파일 생성: news_output_nice.html")
print(f"  총 뉴스: {len(html_parts)}개")
