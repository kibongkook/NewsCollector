"""HTML 레이아웃 테스트"""
import sys
sys.path.insert(0, r'd:\Claude\NewsCollector')

from search_news import search_news
from news_collector.generation.news_generator import NewsGenerator

# 테슬라로 테스트
news_list = search_news(query='테슬라', limit=3)

generator = NewsGenerator()

result = generator.generate(
    source_news=news_list,
    target_format=None,
    style="neutral",
    enrich_content=True,
    search_keywords=['테슬라']
)

if result.generated_news:
    # HTML 생성
    from news_collector.generation.template_engine import TemplateEngine
    engine = TemplateEngine()

    html_content = engine.render(
        result.generated_news.format,
        {
            "title": result.generated_news.title,
            "body": result.generated_news.body,
            "images": result.images if hasattr(result, 'images') and result.images else [],
        }
    )

    # HTML 파일로 저장
    with open("test_output.html", "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{result.generated_news.title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #333; }}
        .content {{ white-space: pre-wrap; }}
        .images {{ margin: 20px 0; }}
        .images img {{ max-width: 100%; height: auto; margin: 10px 0; }}
    </style>
</head>
<body>
    {html_content}
    <div class="images">
        <h3>이미지 ({len(result.images if hasattr(result, 'images') and result.images else [])}개)</h3>
        {"".join(f'<img src="{img}" alt="뉴스 이미지">' for img in (result.images if hasattr(result, 'images') and result.images else []))}
    </div>
</body>
</html>""")

    print("✓ HTML 파일 생성: test_output.html")
    print(f"  제목: {result.generated_news.title}")
    print(f"  본문 길이: {len(result.generated_news.body)}자")
    print(f"  이미지 개수: {len(result.images if hasattr(result, 'images') and result.images else [])}개")
else:
    print("✗ 생성 실패")
