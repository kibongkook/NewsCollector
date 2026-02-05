# Module 6: Content Integrity QA (콘텐츠 무결성)

## 개요
뉴스 콘텐츠의 무결성을 규칙 기반으로 평가. 스팸, 광고, 선정적 기사 탐지.

## 사용법

```python
from news_collector.integrity import ContentIntegrityChecker

checker = ContentIntegrityChecker()
score, details = checker.assess(news)
# score: 0~1 (1=완전 무결)
# details: {title_body_consistency, contamination_score, spam_score, ...}
```

## 평가 항목 (가중치)

### 1. 제목-본문 일치도 (40%)
- 제목 엔티티가 본문에 존재하는 비율
- 키워드 분산도 (본문 전체에 고르게 분포하는지)

### 2. 다중 토픽 오염 (30%)
- 인접 문단 간 키워드 유사도 (Jaccard)
- 유사도가 낮으면 비관련 토픽 혼재 의심

### 3. 스팸/광고 탐지 (30%)
| 플래그 | 감점 | 조건 |
|--------|------|------|
| repetitive_content | +0.3 | 반복 문장 30% 초과 |
| ad_content | +0.3 | 광고 키워드 포함 |
| illegal_content | +0.5 | 불법 키워드 |
| low_content_quality | +0.2 | 어휘 밀도 40% 미만 |
| sensational_title | +0.1 | 선정적 패턴 매칭 |

## 출력 details
```python
{
    "title_body_consistency": 0.85,
    "contamination_score": 0.0,
    "contamination_flags": [],
    "spam_score": 0.1,
    "spam_flags": ["sensational_title"]
}
```

## 테스트
```bash
pytest news_collector/tests/test_integrity.py -v
```
