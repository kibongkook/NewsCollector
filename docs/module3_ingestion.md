# Module 3: Ingestion Engine (수집 엔진)

## 개요
다중 소스(RSS/API)에서 뉴스를 병렬 수집하는 엔진.

## 아키텍처

```
QuerySpec → IngestionEngine → [RSSConnector, APIConnector] → List[RawNewsRecord]
                  ↓
          SourceRegistry (소스 선택)
```

## 핵심 클래스

### BaseConnector (ABC)
모든 커넥터의 추상 베이스.

```python
class BaseConnector(ABC):
    async def fetch(self, keywords=None, limit=20) -> List[RawNewsRecord]: ...
```

### RSSConnector
RSS 2.0 / Atom 피드 파싱.

```python
connector = RSSConnector(source)
records = await connector.fetch(keywords=["AI"], limit=10)
```

- RSS 2.0 `<item>` 및 Atom `<entry>` 지원
- 키워드 필터링 (제목+설명)
- HTML 태그 자동 제거

### APIConnector
REST API 기반 수집 (네이버 API 등).

```python
connector = APIConnector(source, api_key="...", api_secret="...")
records = await connector.fetch(keywords=["경제"], limit=20)
```

### IngestionEngine (오케스트레이터)
```python
engine = IngestionEngine(registry, api_credentials={"naver_news": {...}})
records = engine.collect(query_spec)
```

- QuerySpec 기반 소스 자동 선택
- asyncio 병렬 수집
- 성공/실패 자동 기록

## 출력: RawNewsRecord
| 필드 | 타입 | 설명 |
|------|------|------|
| id | str | MD5(source_id:url) |
| source_id | str | 소스 ID |
| raw_html | str | 원본 HTML |
| raw_data | dict | 파싱된 원본 데이터 |
| extracted_text | str | 텍스트 추출 |
| url | str | 기사 URL |
| http_status | int | HTTP 상태 코드 |
| response_time_ms | int | 응답 시간 |

## 테스트
```bash
pytest news_collector/tests/test_ingestion.py -v
```
