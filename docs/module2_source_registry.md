# Module 2: Source Registry (소스 레지스트리)

## 역할
모든 뉴스 소스의 메타데이터 및 수집 정책 중앙 관리

## 파일 구조
```
news_collector/
├── registry/
│   └── source_registry.py         # SourceRegistry 클래스
├── models/
│   └── source.py                  # NewsSource, RateLimit, TierDefinition
├── config/
│   └── sources_registry.yaml      # 소스 및 Tier 정의
└── tests/
    └── test_source_registry.py    # 36개 테스트
```

## 사용법
```python
from news_collector.utils.config_manager import ConfigManager
from news_collector.registry.source_registry import SourceRegistry

config = ConfigManager()
registry = SourceRegistry(config)

# 단일 조회
naver = registry.get("naver_news")
print(naver.tier, naver.credibility_base_score)  # tier1, 88.0

# 목록 조회
active = registry.get_active_sources()        # 활성 소스
tier1 = registry.get_by_tier("tier1")         # Tier별
rss = registry.get_by_ingestion_type("rss")   # 수집방식별
it = registry.get_by_category("IT")           # 카테고리별
verified = registry.get_verified_sources()     # whitelist + tier1

# QuerySpec 조건 기반 선택 (신뢰도순 정렬)
sources = registry.select_sources(
    categories=["경제", "IT"],
    locale="ko_KR",
    verified_only=True,
)

# 상태 관리
registry.record_success("naver_news")   # 성공 기록
registry.record_failure("unknown_blog") # 실패 기록 (5회 연속 시 자동 비활성화)
registry.reactivate("unknown_blog")     # 재활성화

# 통계
stats = registry.get_stats()
# {"total": 8, "active": 7, "by_tier": {...}, "by_type": {...}}
```

## Tier 체계
| Tier | 설명 | 기본 신뢰도 | 가중치 |
|------|------|------------|--------|
| whitelist | 공식 기관, 정부 | 95 | 1.0 |
| tier1 | 주요 신문사, 대형 언론사 | 88 | 0.95 |
| tier2 | 지역 언론사, 중소 매체 | 70 | 0.80 |
| tier3 | 개인 블로그, 소규모 | 45 | 0.60 |
| blacklist | 스팸, 거짓 뉴스 | 0 | 0.0 |

## NewsSource 주요 필드
| 필드 | 설명 |
|------|------|
| id, name | 식별자 |
| tier | 신뢰도 등급 |
| ingestion_type | api / rss / web_crawl |
| credibility_base_score | 기본 신뢰도 (0~100) |
| rate_limit | 요청 제한 (분/시/일) |
| provides_metadata | author/views/shares/comments 제공 여부 |
| is_active | 활성 상태 |
| failure_count | 연속 실패 횟수 |

## 소스 추가/수정
`config/sources_registry.yaml` 편집:
```yaml
sources:
  new_source:
    id: "new_source"
    name: "새 소스"
    tier: "tier2"
    ingestion_type: "rss"
    base_url: "https://example.com/rss"
    credibility_base_score: 72
    supported_categories: ["IT", "과학"]
```

## 테스트
```bash
pytest news_collector/tests/test_source_registry.py -v
```
