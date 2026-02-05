# Module 1: Request Parser (의도 이해 모듈)

## 역할
사용자 입력(자연어 또는 파라미터)을 해석하여 구조화된 `QuerySpec` 생성

## 파일 구조
```
news_collector/
├── parsers/
│   ├── request_parser.py          # 오케스트레이터 (입력 감지 → 서브파서 위임)
│   ├── natural_language_parser.py # 한국어 자연어 파싱
│   ├── parameter_parser.py        # dict/JSON 파라미터 파싱
│   └── date_parser.py             # 한국어 날짜 표현 파싱
├── models/
│   └── query_spec.py              # QuerySpec dataclass
├── config/
│   ├── config.yaml                # 기본값, 검증 제약
│   └── natural_language_mapping.yaml  # 의도/날짜/카테고리 패턴
└── tests/
    ├── test_request_parser.py     # E2E 테스트
    ├── test_natural_language_parser.py
    ├── test_parameter_parser.py
    ├── test_date_parser.py
    └── test_query_spec.py
```

## 사용법
```python
from news_collector.utils.config_manager import ConfigManager
from news_collector.parsers.request_parser import RequestParser

config = ConfigManager()
parser = RequestParser(config)

# 자연어 입력
query = parser.parse("어제 정치 뉴스 Top 10")
# → QuerySpec(date_from=어제, category=["정치"], limit=10)

# 파라미터 입력
query = parser.parse({"keywords": ["AI"], "category": "IT", "limit": 20})
```

## QuerySpec 필드
| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| date_from / date_to | Optional[datetime] | None | 검색 기간 |
| locale | str | "ko_KR" | 로케일 |
| timezone | str | "Asia/Seoul" | 타임존 |
| category | Optional[List[str]] | None | 카테고리 필터 |
| keywords | Optional[List[str]] | None | 포함 키워드 |
| exclude_keywords | Optional[List[str]] | None | 제외 키워드 |
| popularity_type | str | "latest" | trending/popular/latest/quality |
| group_by | str | "none" | day/source/none |
| limit | int | 20 | 결과 수 (1~100) |
| offset | int | 0 | 페이징 오프셋 |
| verified_sources_only | bool | False | 검증 소스만 |
| diversity | bool | True | 소스 다양성 |

## 자연어 파싱 지원
- **의도**: 트렌딩/인기/최신/품질 키워드 매칭
- **날짜**: 어제, 오늘, 지난 N일/주, M월 D일~D일, YYYY-MM-DD
- **카테고리**: 정치/경제/사회/IT/과학/문화/스포츠/국제/연예
- **키워드**: "X 관련", "X에 대한" 패턴
- **제외**: "X 제외", "X 빼고" 패턴
- **결과 수**: "Top N", "N개", "N건"

## 설정 변경
- 패턴 추가/수정: `config/natural_language_mapping.yaml`
- 기본값 변경: `config/config.yaml` → `defaults` 섹션

## 테스트
```bash
pytest news_collector/tests/test_request_parser.py -v
pytest news_collector/tests/test_natural_language_parser.py -v
pytest news_collector/tests/test_date_parser.py -v
```
