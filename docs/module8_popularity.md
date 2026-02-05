# Module 8: Popularity Engine (인기도)

## 개요
조회/공유/댓글 기반 인기도 점수 및 트렌딩 속도 산출.

## 사용법

```python
from news_collector.scoring import PopularityScorer

scorer = PopularityScorer()
result = scorer.score(news, all_news)
# {"popularity_score": 0.75, "trending_velocity": 0.3}
```

## 점수 산출

### popularity_score (가중 합산)
| 지표 | 가중치 | 정규화 |
|------|--------|--------|
| 조회수 (view_count) | 40% | 전체 최대값 대비 비율 |
| 공유수 (share_count) | 35% | 전체 최대값 대비 비율 |
| 댓글수 (comment_count) | 25% | 전체 최대값 대비 비율 |

- 인기도 메트릭이 없으면 **신선도** 기반 추정

### 신선도 (freshness)
- 지수 감쇠: `0.5^(hours_ago / half_life)`
- 반감기 기본값: 24시간
- 날짜 없으면 기본 0.3

### trending_velocity
- `total_engagement / hours_since_publish`
- engagement = views + shares×3 + comments×2
- 정규화: 10000/h = 1.0

## 설정
| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| view_weight | 0.4 | 조회수 가중치 |
| share_weight | 0.35 | 공유수 가중치 |
| comment_weight | 0.25 | 댓글수 가중치 |
| freshness_half_life_hours | 24.0 | 신선도 반감기 |

## 테스트
```bash
pytest news_collector/tests/test_popularity.py -v
```
