# Module 7: Credibility & Quality Scoring (신뢰도/품질)

## 개요
소스 Tier 기반 신뢰도, 크로스 소스 검증, 증거 기반 품질, 선정성 감점.

## 사용법

```python
from news_collector.scoring import CredibilityScorer

scorer = CredibilityScorer(registry=source_registry)
result = scorer.score(news, all_news)
# {"credibility_score": 0.9, "quality_score": 0.7, "evidence_score": 0.6, "sensationalism_penalty": 0.15}
```

## 점수 산출

### credibility_score = source_trust + cross_bonus

**소스 Tier 신뢰도:**
| Tier | 점수 |
|------|------|
| whitelist | 0.95 |
| tier1 | 0.85 |
| tier2 | 0.65 |
| tier3 | 0.40 |
| blacklist | 0.0 |

**크로스 소스 보너스:**
- Jaccard 유사도 ≥ 0.5인 다른 소스 기사 수
- 1~2개: +0.05, 3개 이상: +0.15

### quality_score = evidence - sensationalism

**증거 점수 (EVIDENCE_PATTERNS):**
- 통계 (`\d+%`, `\d+억`)
- 직접 인용 (`"..."`)
- 공식 발표 (`관계자는`, `대변인`)
- 참조 (`보고서`, `연구 결과`)
- 참고 링크 (`https://...`)
- 본문 길이 보너스 (max 0.2)

**선정성 감점:**
- 선정적 단어: 충격, 경악, 대박, 역대급 등 (각 -0.15, max -0.5)
- 과도한 특수문자: `!!`, `??`, `ㅋㅋ` 등 (각 -0.1, max -0.2)

## 테스트
```bash
pytest news_collector/tests/test_credibility.py -v
```
