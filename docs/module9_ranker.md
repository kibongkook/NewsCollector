# Module 9: Ranker & Policy Filter (랭킹)

## 개요
Module 6~8 점수를 통합하여 최종 점수 산출, 정책 필터, 다양성 보장, 랭킹.

## 사용법

```python
from news_collector.ranking import Ranker

ranker = Ranker(config=config_manager, registry=source_registry)
results = ranker.rank(news_list, preset="quality", limit=20)
```

## 파이프라인

```
news_list → 점수 산출(M6/M7/M8) → 최종 점수 → 정책 필터 → 정렬 → 다양성 → Top-N
```

## 프리셋 가중치

| 프리셋 | popularity | relevance | quality | credibility |
|--------|-----------|-----------|---------|-------------|
| quality | 0.15 | 0.30 | 0.40 | 0.15 |
| trending | 0.50 | 0.10 | 0.20 | 0.20 |
| credible | 0.10 | 0.20 | 0.20 | 0.50 |
| latest | 0.10 | 0.20 | 0.30 | 0.40 |

최종 점수 = Σ(score × weight) × 100 (0~100)

## 정책 필터

| 조건 | 액션 |
|------|------|
| integrity_score < 0.5 | 제외 |
| credibility_score < 0.6 | 플래그 (유지) |
| spam_score > 0.7 | 제외 |

## 다양성 보장
- 같은 소스 최대 3개 (설정 가능)
- 소스별 카운터로 순서대로 필터링

## 출력: NewsWithScores
NormalizedNews + 모든 점수 필드:
- integrity_score, credibility_score, quality_score, popularity_score
- final_score (0~100), rank_position (1-based)
- policy_flags

## 테스트
```bash
pytest news_collector/tests/test_ranker.py -v
```
