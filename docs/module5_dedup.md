# Module 5: Dedup & Clustering (중복 제거)

## 개요
3단계 파이프라인으로 중복 뉴스 제거 및 유사 뉴스 클러스터링.

## 사용법

```python
from news_collector.dedup import DeduplicationEngine

engine = DeduplicationEngine(similarity_threshold=0.6)
unique_news = engine.deduplicate(news_list)
```

## 3단계 파이프라인

### 1단계: URL 중복 제거
- URL 정규화 (쿼리 파라미터, 프래그먼트, 대소문자, trailing slash 제거)
- 동일 URL → 첫 번째만 유지

### 2단계: 제목 해시 중복 제거
- 제목 lowercase + strip → MD5 해시
- 동일 해시 → 첫 번째만 유지

### 3단계: Jaccard 유사도 클러스터링
- 제목 단어 기반 Jaccard 유사도 계산
- threshold(0.6) 이상이면 같은 클러스터
- 대표 선정: 가장 긴 본문

## 설정
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| similarity_threshold | 0.6 | Jaccard 유사도 임계값 |

## 예시

```
입력: 10건
  → URL 중복 제거: 8건
  → 제목 해시: 7건
  → 클러스터링: 5건 (2개 클러스터)
출력: 5건 (대표 기사)
```

## 테스트
```bash
pytest news_collector/tests/test_dedup.py -v
```
