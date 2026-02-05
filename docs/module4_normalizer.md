# Module 4: News Normalizer (뉴스 정규화)

## 개요
RawNewsRecord → NormalizedNews 변환. HTML 정제, 날짜 파싱, 카테고리 매핑.

## 사용법

```python
from news_collector.normalizer import NewsNormalizer

normalizer = NewsNormalizer()

# 단건 정규화
normalized = normalizer.normalize(raw_record, source=news_source)

# 배치 정규화
results = normalizer.normalize_batch(records, source_map={"src_id": source})
```

## 처리 파이프라인

1. **HTML 정제**: `<script>`, `<style>` 제거, 태그 스트립, 엔티티 디코딩
2. **날짜 파싱**: ISO, RFC2822 등 다양한 형식 (dateutil)
3. **카테고리 추론**: hint + 제목 키워드 매칭 (9개 카테고리)
4. **이미지 URL 추출**: `<img src="...">` 패턴
5. **메타데이터 매핑**: author, tags, view/share/comment count

## 카테고리 매핑
| 카테고리 | 키워드 |
|----------|--------|
| 정치 | politics, 국회, 대통령, 정당 |
| 경제 | economy, 기업, 주식, 금융 |
| IT | tech, 기술, AI, 인공지능 |
| 과학 | science, 연구, 우주, 바이오 |
| 사회 | society, 범죄, 교육, 복지 |
| 문화 | culture, 예술, 영화, 음악 |
| 스포츠 | sports, 축구, 야구 |
| 국제 | world, 세계, 외교 |
| 연예 | entertainment, 아이돌, 드라마 |

## 출력: NormalizedNews
주요 필드: id, source_id, title, body, author, published_at, category, tags, url, image_urls, view_count, share_count, comment_count

## 테스트
```bash
pytest news_collector/tests/test_normalizer.py -v
```
