# 뉴스 생성 품질 개선 진행 보고서
**날짜**: 2026-02-07
**세션**: 교차 기사 혼합 방지 + Visual/Data 빌더 구현

---

## 완료된 작업 (Task 1-3)

### Task 1: 본문 품질 개선 - 교차 기사 문장 혼합 방지
**문제**: 여러 기사 검색 시 (예: "외교" 키워드로 5개 기사 수집) 모든 기사의 문장이 중요도만으로 섞여 무관한 내용 혼합

**해결**:
- `_get_primary_source()`: 키워드 매칭과 중요도로 가장 관련성 높은 primary source 기사 식별
- `_source_preferred_select()`: primary source 문장 우선 선택, 부족 시에만 secondary source 보충
- `_build_straight()` 전면 개선: 리드/본문/마무리 모든 섹션에서 primary source 우선 적용

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py)

### Task 2: Visual/Data 빌더 구현
**문제**: config에 3가지 뉴스 유형(standard/visual/data) 정의되어 있으나 코드는 `_build_straight()`만 구현됨

**해결**:
- `_build_visual_straight()`: 짧은 본문(200-500자) + 이미지 중심 구성
- `_build_data_straight()`: 숫자/통계 우선 선택 + 분석 중심 본문(300-600자)
- `_build_sections()` 개선: news_type 매개변수 추가, 유형별 빌더 분기
- `AssembledContent`에 `news_type` 필드 추가, 전체 파이프라인 연결

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py), [news_generator.py](news_collector/generation/news_generator.py)

### Task 3: 이미지를 기사 구조 안에 배치
**문제**: 이미지가 본문 하단에 갤러리로만 덤프됨

**해결**:
- **Visual 유형**: 대표 이미지 본문 위 크게 표시, 갤러리 본문 아래 그리드 배치
- **Standard 유형**: 본문 뒤 보조 이미지 1장 작게 표시
- **Data 유형**: 차트/그래프 이미지 본문 위 표시
- CSS 스타일 추가: `.gen-primary-image`, `.gen-inline-image`, `.gen-chart-image`
- 유형별 배지 표시: type-standard/visual/data

**파일**: [generate_html_news.py](generate_html_news.py)

---

## 반복 테스트 및 문제 수정 (Round 1-4)

### Round 1 문제
1. ❌ **모든 기사 "visual" 감지**: 5개 기사 이미지 합계로 판단하여 항상 3장 초과
2. ❌ **SNS 아이콘 이미지 누출**: `ico_face.png`, `g_circle_blog.png`
3. ❌ **템플릿 플레이스홀더**: `${img_url}`, `${data.IMG2_URL}`
4. ❌ **"---\n출처:" 텍스트 본문 포함**

### Round 1 수정
- `detect_news_type()`: 합계 대신 **기사당 평균 이미지 수** 사용
- 이미지 필터: `ico_`, `g_circle`, `${` 패턴 추가
- HTML 렌더링: `---`, `출처:` 시작 라인 본문에서 제외

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py), [generate_html_news.py](generate_html_news.py)

### Round 2 결과
- ✅ 유형 분포 개선: data(3), standard(1), visual(1)
- ❌ 기자 바이라인 잔존: `[디지털투데이 AI공시팀]`, `[대구=뉴시스] 박준 기자 =`
- ❌ 사진 캡션 잔존: `| 치매환자 돌봄가족을 위한 '휴레스토랑' 행사 현장 [사진=산림청] |`
- ❌ 원문 불릿 포인트: `○` 기호 본문에 남음

### Round 2 수정
- 바이라인 패턴 추가: `^\[.{2,20}(기자|특파원|팀)\]`, `^\[.{2,10}=.{2,10}\].*기자`
- 사진 캡션 패턴: `^\|.*\|$`, `\[사진[=:].{2,30}\]`
- 문장 추출 시 불릿 기호 제거: `^[○●◎▶▷►◆◇■□★☆·•※→\-]\s*`

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py)

### Round 3 결과 (**심각한 문제 발견**)
- ❌ **"외교" 기사에 다른 기사 헤드라인 혼입**:
  - "조현 외교, 美 상원의원들에 "핵잠·원자력 협력 지지 요청" 뉴스1"
  - "외교전략정보본부장, 'AI의 책임 있는 군사적 이용' 회의 참석 뉴스1"
  - → 원본 기사 내 "관련 기사" 섹션의 헤드라인이 본문으로 스크래핑됨

### Round 3 수정
- 관련 기사 헤드라인 패턴 추가: `.{10,}(뉴스1|연합뉴스|조선일보|중앙일보|...|전자신문)$`
- 도메인 포함 문장 필터: `\w+\.(com|co\.kr|net|or\.kr|go\.kr)`

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py)

### Round 4 결과
- ✅ 유형 분포: visual(2), standard(3)
- ❌ 지역 바이라인: "(부산=연합뉴스) 박성제 기자", "뉴욕=박신영 특파원"
- ❌ 방송 마커: "◀ 앵커", "◀ 리포트"
- ❌ 타임스탬프: "입력 2026-02-07 07:12", "수정 2026-02-07 07:28"
- ❌ 전화번호: "전화 02-784-4000"
- ❌ 저작권 표시: "ⓒ 한경닷컴"
- ❌ 프로그램명+기자: "뉴스투데이 정상빈"

### Round 4 수정
- 지역 바이라인: `^\(.{2,10}=.{2,20}\)\s*.{2,20}\s*기자`, `.{2,20}[=＝].{2,20}(기자|특파원)`
- 방송 마커: `^[◀◁◀◀▶▷]\s*(앵커|기자|리포터|리포트|진행|출연)`
- 타임스탬프: `(입력|수정|작성|게재|발행)\s*[:：]?\s*\d{4}[-./]\d{1,2}[-./]\d{1,2}`
- 연락처: `(전화|팩스|이메일|메일|Tel|Fax|Email)\s*[:：]?\s*[\d\-\(\)]+`
- 저작권: `[ⓒⒸ©]\s*.{2,20}(닷컴|뉴스|일보|미디어|방송)`
- 프로그램+기자: `(뉴스투데이|뉴스9|뉴스데스크|아침뉴스|저녁뉴스)\s+.{2,10}$`

**파일**: [content_assembler.py](news_collector/generation/content_assembler.py)

---

## 핵심 개선 사항 요약

### 1. Primary Source 우선 선택 로직 (Task 1)
```python
def _get_primary_source(self, sentences) -> Optional[str]:
    """키워드 매칭 + 중요도로 primary source 식별"""
    source_scores = {}
    for s in sentences:
        score = s.importance + len(s.matched_keywords) * 0.3
        source_scores[s.source_news_id] += score
    return max(source_scores, key=lambda x: source_scores[x])

def _source_preferred_select(self, candidates, primary_source, max_count):
    """Primary source 문장 우선 선택"""
    primary = [s for s in candidates if s.source_news_id == primary_source]
    secondary = [s for s in candidates if s.source_news_id != primary_source]
    result = primary[:max_count]
    if len(result) < max_count:
        result.extend(secondary[:max_count - len(result)])
    return result
```

### 2. 뉴스 유형별 빌더 (Task 2)
- **Visual**: 200-500자, 상황 설명 + 장면 묘사, 이미지 중심
- **Data**: 300-600자, 통계 우선 + 분석 중심, 숫자 포함 문장 우선 선택
- **Standard**: 400-800자, 역피라미드 구조

### 3. Boilerplate 필터링 강화
현재 **25개 패턴** 운영 중:
- 저작권/면책 (9개)
- 기자 바이라인 (5개)
- 사진 캡션 (2개)
- 광고/구독 (1개)
- 관련 기사 헤드라인 (2개)
- 타임스탬프 (1개)
- 연락처 (1개)
- 저작권 심볼 (1개)
- 방송 마커 (1개)
- 프로그램명+기자 (1개)
- 도메인 (1개)

### 4. 이미지 필터링 강화
**50+ 제외 패턴** 운영 중:
- 광고: `banner`, `ad_`, `sponsor`
- 로고: `logo`, `symbol`, `emblem`
- 아이콘: `icon`, `ico_`, `g_circle`
- UI 요소: `bul_`, `bullet`, `dot_`, `arr_`
- 썸네일: `thumbnail/custom/`, `_120.jpg`
- SNS: `/member/`
- 플레이스홀더: `{{`, `}}`, `{%`, `${`

---

## 다음 단계

1. **Round 5 테스트**: 최신 boilerplate 패턴 효과 검증
2. **원본 vs 생성 비교**: 내용 일관성, 정보 정확도 확인
3. **대규모 테스트**: 20-30개 랜덤 키워드로 안정성 검증
4. **성능 최적화**: 생성 시간 단축 (현재 평균 473ms)

---

## 변경된 파일 목록

1. `news_collector/generation/content_assembler.py` (핵심 변경)
   - Primary source 선택 로직 추가
   - Visual/Data 빌더 구현
   - Boilerplate 패턴 25개로 확장
   - 이미지 필터 50+ 패턴

2. `news_collector/generation/news_generator.py`
   - FallbackGeneratorResult에 news_type 추가
   - news_type 파이프라인 연결

3. `generate_html_news.py`
   - 뉴스 유형 감지 추가
   - 유형별 이미지 배치 구현
   - CSS 스타일 추가

4. `config/news_format_spec.yaml` (이전 세션에서 수정)
   - Visual 감지: high/low confidence keywords 분리
   - Data 감지: keyword_threshold 추가
