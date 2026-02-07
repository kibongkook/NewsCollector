"""지능형 뉴스 생성기 - 표절 없는 재작성"""
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from collections import Counter

from news_collector.models.news import NewsWithScores


@dataclass
class ExtractedFacts:
    """추출된 핵심 정보"""
    main_topic: str = ""
    entities: List[str] = None  # 기업명, 인물명, 지명 등
    numbers: List[Tuple[str, str]] = None  # (숫자, 단위/의미)
    dates: List[str] = None
    key_actions: List[str] = None  # 주요 행동/사건

    def __post_init__(self):
        if self.entities is None:
            self.entities = []
        if self.numbers is None:
            self.numbers = []
        if self.dates is None:
            self.dates = []
        if self.key_actions is None:
            self.key_actions = []


class IntelligentNewsGenerator:
    """표절 없는 지능형 뉴스 생성기"""

    def __init__(self):
        # 뉴스 스타일 템플릿 (직접 복사 방지)
        self.title_templates = [
            "{entity}, {action}",
            "{entity} {number} {action}",
            "{topic} {action}",
        ]

        self.lead_templates = [
            "{entity}가 {action}했다.",
            "{entity}는 {number}를 {action}하며 {topic} 분야에서 주목받고 있다.",
            "{date} {entity}는 {action}을 발표했다.",
        ]

    def extract_facts(self, news_list: List[NewsWithScores]) -> ExtractedFacts:
        """뉴스들에서 핵심 정보만 추출 (문장 복사 안 함)"""
        facts = ExtractedFacts()

        all_text = " ".join([
            (news.title or "") + " " + (news.body or "")
            for news in news_list
        ])

        # 제목 텍스트 (우선순위 높음)
        all_titles = " ".join([news.title or "" for news in news_list])

        # 1. 주요 엔티티 추출 (기업명, 인물명) - 제목 우선
        facts.entities = self._extract_entities(all_text, title_text=all_titles)

        # 2. 숫자 정보 추출
        facts.numbers = self._extract_numbers(all_text)

        # 3. 날짜 정보 추출
        facts.dates = self._extract_dates(all_text)

        # 4. 주요 액션 추출
        facts.key_actions = self._extract_actions(all_text, news_list)

        # 5. 메인 토픽 결정
        facts.main_topic = self._determine_main_topic(facts.entities, all_text)

        return facts

    def _extract_entities(self, text: str, title_text: str = "") -> List[str]:
        """주요 엔티티 추출 (기업명, 인물명, 지명) - 제목 우선순위 기반"""
        entities = []
        entity_scores = {}  # 엔티티별 점수

        # 1. 유명 브랜드/기업명 (한글) - 직접 매칭
        well_known_brands = [
            '삼성', '삼성전자', 'LG', 'SK', '현대', '현대차', '기아',
            '네이버', '카카오', '쿠팡', '배달의민족', '토스',
            '테슬라', '애플', '구글', '메타', '아마존', '마이크로소프트', '엔비디아',
            '비트코인', '이더리움', '도지코인', '리비안', '루시드'
        ]
        for brand in well_known_brands:
            if brand in text:
                entities.append(brand)
                # 유명 브랜드 가중치 +10
                entity_scores[brand] = entity_scores.get(brand, 0) + 10
                # 제목에 있으면 추가 가중치 +20
                if brand in title_text:
                    entity_scores[brand] += 20

        # 2. 한국 기업명 패턴 (접미사 기반)
        company_pattern = r'[가-힣A-Z][가-힣a-zA-Z0-9]*(?:전자|그룹|엔터|모빌리티|바이오|화학|증권|생명|카드|물산|중공업|자동차|건설|디스플레이|에너지|헬스케어|테크|소프트|시스템)'
        companies = re.findall(company_pattern, text)
        for company in companies:
            if company not in entities:
                entities.append(company)
            entity_scores[company] = entity_scores.get(company, 0) + 5
            if company in title_text:
                entity_scores[company] += 15

        # 3. 외국 기업명 (영문, 대문자로 시작)
        foreign_companies = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        for company in foreign_companies:
            if len(company) > 2 and company not in entities:
                entities.append(company)
                entity_scores[company] = entity_scores.get(company, 0) + 5
                if company in title_text:
                    entity_scores[company] += 15

        # 4. 빈도 기반 추가 점수
        entity_counts = Counter(entities)
        for entity, count in entity_counts.items():
            entity_scores[entity] = entity_scores.get(entity, 0) + count

        # 5. 점수 순으로 정렬
        sorted_entities = sorted(entity_scores.items(), key=lambda x: x[1], reverse=True)

        # 6. 상위 엔티티 반환
        result = [entity for entity, score in sorted_entities[:5] if score >= 2]

        # 엔티티가 없으면 일반 명사에서 빈도 높은 것 사용
        if not result:
            general_nouns = re.findall(r'[가-힣]{2,}', text)
            noun_counts = Counter(general_nouns)
            stopwords = {'이번', '올해', '내년', '기자', '관계자', '시장', '업계', '오늘', '어제', '도어', '손잡이'}
            result = [
                word for word, count in noun_counts.most_common(5)
                if word not in stopwords and count >= 2
            ]

        return result[:5]  # 최대 5개

    def _extract_numbers(self, text: str) -> List[Tuple[str, str]]:
        """의미있는 숫자 정보 추출 (중복 제거, 우선순위 기반)"""
        numbers = []
        seen_values = set()  # 숫자 값 중복 방지

        # 숫자 + 단위 패턴 (우선순위 순서: 큰 단위부터)
        patterns = [
            # 시가총액/매출 등 (조 단위)
            (r'시가?총액\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*조\s*(원|달러)', '시총', 100),
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*조\s*(원|달러)', '금액_조', 90),

            # 억 단위
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*억\s*(원|달러)', '금액_억', 80),

            # 만원 단위 (주가)
            (r'주가?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*만\s*(원|달러)', '주가', 85),
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*만\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(원|달러)', '금액_만원', 70),

            # 비율 (%)
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*%', '비율', 60),

            # 수량
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(명|개|건|회|대)', '수량', 50),

            # 배수/점수
            (r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(배|점|등급)', '배수', 40),
        ]

        number_with_priority = []

        for pattern, category, priority in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # 튜플을 문자열로 변환
                if isinstance(match, tuple):
                    number_str = "".join(str(m) for m in match if m).strip()
                else:
                    number_str = match.strip()

                # 숫자 값 추출 (중복 체크용)
                number_value = re.findall(r'\d+(?:,\d{3})*(?:\.\d+)?', number_str)
                if number_value:
                    main_value = number_value[0].replace(',', '')

                    # 중복 체크 (같은 값은 우선순위 높은 것만)
                    if main_value not in seen_values:
                        seen_values.add(main_value)

                        # 카테고리 정리
                        if category.startswith('금액_') or category == '시총' or category == '주가':
                            final_category = '금액'
                        elif category == '비율':
                            final_category = '비율'
                        elif category == '수량':
                            final_category = '수량'
                        else:
                            final_category = category

                        number_with_priority.append((number_str, final_category, priority))

        # 우선순위 순으로 정렬
        number_with_priority.sort(key=lambda x: x[2], reverse=True)

        # 카테고리별 최대 1개씩, 최대 3개
        seen_categories = set()
        for number_str, category, _ in number_with_priority:
            if category not in seen_categories and len(numbers) < 3:
                numbers.append((number_str, category))
                seen_categories.add(category)

        return numbers

    def _extract_dates(self, text: str) -> List[str]:
        """날짜 정보 추출"""
        dates = []

        # 날짜 패턴
        date_patterns = [
            r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일',
            r'\d{1,2}월\s*\d{1,2}일',
            r'오늘|어제|내일|이번주|다음달|올해|내년',
        ]

        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches[:2])

        return dates[:3]

    def _extract_actions(self, text: str, news_list: List[NewsWithScores]) -> List[str]:
        """주요 행동/사건 추출 (동사 기반)"""
        actions = []

        # 뉴스에서 자주 쓰이는 주요 동사 패턴
        action_keywords = [
            '발표', '달성', '기록', '돌파', '상승', '하락', '증가', '감소',
            '출시', '공개', '확대', '축소', '투자', '인수', '합병', '협력',
            '개발', '생산', '판매', '수출', '진출', '철수', '중단', '재개',
        ]

        for keyword in action_keywords:
            if keyword in text:
                # 해당 동사 주변 맥락 추출 (동사만 저장, 전체 문장 복사 안 함)
                actions.append(keyword)

        return actions[:5]

    def _determine_main_topic(self, entities: List[str], text: str) -> str:
        """메인 토픽 결정"""
        if entities:
            return entities[0]

        # 엔티티가 없으면 주요 키워드로 결정
        keywords = re.findall(r'[가-힣]{2,}', text)
        keyword_counts = Counter(keywords)

        # 불용어 제외
        stopwords = {'이번', '올해', '내년', '기자', '관계자', '시장', '업계'}
        for word in stopwords:
            keyword_counts.pop(word, None)

        if keyword_counts:
            return keyword_counts.most_common(1)[0][0]

        return "최신 뉴스"

    def generate_title(self, facts: ExtractedFacts) -> str:
        """팩트 기반으로 새로운 제목 생성"""
        # 엔티티와 액션 조합
        if facts.entities and facts.key_actions:
            entity = facts.entities[0]
            action = facts.key_actions[0]

            # 숫자가 있으면 포함 (가장 중요한 숫자만)
            if facts.numbers:
                number, category = facts.numbers[0]
                # 금액인 경우
                if category == '금액':
                    return f"{entity}, {number} {action}"
                # 비율인 경우
                elif category == '비율':
                    return f"{entity}, {number} {action}"
                else:
                    return f"{entity}, {action}"

            return f"{entity}, {action}"

        # 엔티티만 있는 경우
        if facts.entities:
            entity = facts.entities[0]
            if facts.numbers:
                number, category = facts.numbers[0]
                return f"{entity}, {number} 기록"
            return f"{entity} 최신 동향"

        # 토픽만 있는 경우
        return f"{facts.main_topic} 업계 동향"

    def generate_lead(self, facts: ExtractedFacts) -> str:
        """리드 문단 생성 (5W1H)"""
        # Who + What (핵심)
        if facts.entities and facts.key_actions:
            entity = facts.entities[0]
            action = facts.key_actions[0]

            # When 추가
            when_part = ""
            if facts.dates:
                when_part = f"{facts.dates[0]} "

            # 숫자 정보 추가
            number_part = ""
            if facts.numbers:
                number, category = facts.numbers[0]
                if category == '금액':
                    number_part = f" {number}의"
                elif category == '비율':
                    number_part = f" {number}"

            # 문장 조합
            if action in ['발표', '공개', '출시']:
                lead = f"{when_part}{entity}가{number_part} {action}를 진행했다."
            elif action in ['달성', '기록', '돌파']:
                lead = f"{when_part}{entity}가{number_part} {action}했다."
            elif action in ['상승', '증가', '확대']:
                lead = f"{when_part}{entity}의 실적이{number_part} {action}했다."
            else:
                lead = f"{when_part}{entity}가 {action} 관련 소식을 전했다."

            return lead

        # 엔티티만 있는 경우
        if facts.entities:
            entity = facts.entities[0]
            if facts.numbers:
                number, category = facts.numbers[0]
                return f"{entity}가 {number}를 기록하며 업계의 주목을 받고 있다."
            return f"{entity} 관련 최신 동향이 전해졌다."

        return f"{facts.main_topic} 분야의 새로운 소식이 전해졌다."

    def generate_body(
        self,
        facts: ExtractedFacts,
        news_list: List[NewsWithScores]
    ) -> str:
        """본문 생성 (팩트 기반 재작성)"""
        paragraphs = []

        # 1단락: 핵심 내용 (숫자 정보)
        if facts.numbers:
            para = self._generate_number_paragraph(facts)
            if para:
                paragraphs.append(para)

        # 2단락: 배경 정보
        para = self._generate_background_paragraph(facts)
        if para:
            paragraphs.append(para)

        # 3단락: 추가 상세 (엔티티별)
        if len(facts.entities) > 1:
            para = self._generate_details_paragraph(facts)
            if para:
                paragraphs.append(para)

        # 4단락: 전망
        para = self._generate_outlook_paragraph(facts)
        if para:
            paragraphs.append(para)

        return " ".join(paragraphs)

    def _generate_number_paragraph(self, facts: ExtractedFacts) -> str:
        """숫자 정보 기반 문단 생성 (개선된 버전)"""
        if not facts.numbers:
            return ""

        # 가장 중요한 숫자 1-2개만 사용
        primary_numbers = facts.numbers[:2]

        # 숫자별로 다른 표현 사용
        parts = []
        for i, (number, category) in enumerate(primary_numbers):
            if category == '금액':
                if i == 0:
                    parts.append(f"{number} 규모를 기록했다")
                else:
                    parts.append(f"추가로 {number}의 성과를 달성했다")
            elif category == '비율':
                if i == 0:
                    parts.append(f"{number}의 성장률을 보였다")
                else:
                    parts.append(f"{number} 개선되었다")
            elif category == '수량':
                parts.append(f"{number}를 달성했다")

        if len(parts) == 1:
            action = facts.key_actions[0] if facts.key_actions else "이번 실적"
            return f"{action}에서 {parts[0]}."
        elif len(parts) == 2:
            return f"{parts[0]}. {parts[1]}."

        return ""

    def _generate_background_paragraph(self, facts: ExtractedFacts) -> str:
        """배경 정보 문단 (개선된 버전)"""
        if facts.entities:
            entity = facts.entities[0]

            # entity와 main_topic이 같거나 유사한 경우 방지
            if entity.lower() == facts.main_topic.lower() or entity in facts.main_topic:
                # 다른 관련 키워드 찾기
                if facts.key_actions:
                    return f"{entity}는 최근 {facts.key_actions[0]} 등의 성과를 이어가고 있다."
                return f"{entity}는 관련 분야에서 지속적인 발전을 보이고 있다."
            else:
                return f"{entity}는 {facts.main_topic} 분야에서 두각을 나타내고 있다."

        return f"{facts.main_topic} 시장이 주목받고 있다."

    def _generate_details_paragraph(self, facts: ExtractedFacts) -> str:
        """상세 정보 문단"""
        if len(facts.entities) > 1:
            entities_str = ", ".join(facts.entities[:3])
            return f"{entities_str} 등 주요 기업들이 관련 분야에 참여하고 있다."

        return ""

    def _generate_outlook_paragraph(self, facts: ExtractedFacts) -> str:
        """전망 문단"""
        if facts.key_actions and '증가' in facts.key_actions or '상승' in facts.key_actions:
            return "업계에서는 이러한 추세가 당분간 이어질 것으로 전망하고 있다."
        elif facts.key_actions and '감소' in facts.key_actions or '하락' in facts.key_actions:
            return "전문가들은 향후 상황을 주의 깊게 지켜보고 있다."

        return "관련 업계의 향후 움직임이 주목된다."

    def generate_news(
        self,
        news_list: List[NewsWithScores],
        sources: List[str]
    ) -> Dict[str, str]:
        """전체 뉴스 생성 (표절 없는 재작성)"""
        # 1. 팩트 추출
        facts = self.extract_facts(news_list)

        # 2. 제목 생성
        title = self.generate_title(facts)

        # 3. 리드 생성
        lead = self.generate_lead(facts)

        # 4. 본문 생성
        body = self.generate_body(facts, news_list)

        # 5. 전체 조합
        full_body = f"{lead}\n\n{body}"

        # 6. 출처 추가
        sources_text = f"\n\n---\n\n참고: {', '.join(sources[:5])}"

        return {
            "title": title,
            "body": full_body,
            "sources": sources_text,
            "full_text": f"{title}\n\n{full_body}{sources_text}"
        }


# 사용 예시
if __name__ == "__main__":
    generator = IntelligentNewsGenerator()

    # 테스트용 뉴스 생성
    from news_collector.models.news import NewsWithScores

    test_news = [
        NewsWithScores(
            id="1",
            title="삼성전자 시총 1000조 돌파",
            body="삼성전자가 시가총액 1000조원을 돌파했다. 4월 유가증권시장에서 전 거래일 대비 0.96% 오른 16만9000원에 거래를 마쳤다.",
            source_name="테스트뉴스"
        )
    ]

    result = generator.generate_news(test_news, ["테스트뉴스"])
    print(result["full_text"])
