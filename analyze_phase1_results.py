"""Phase 1 테스트 결과 분석"""
import json
from collections import Counter, defaultdict

# 테스트 리포트 읽기
with open("test_report_20260207_130014.json", "r", encoding="utf-8") as f:
    report = json.load(f)

print("=" * 80)
print("  Phase 1 테스트 결과 상세 분석 (30회)")
print("=" * 80)
print()

# 이미지 개수 통계
image_counts = []
image_by_type = defaultdict(list)

for result in report["results"]:
    img_count = result["images"]["total_count"]
    news_type = result["structure"]["news_type"]

    image_counts.append(img_count)
    image_by_type[news_type].append(img_count)

print("[IMAGE STATS] 이미지 개수 통계")
print("-" * 80)
print(f"  평균 이미지 개수: {sum(image_counts) / len(image_counts):.1f}장")
print(f"  최소: {min(image_counts)}장, 최대: {max(image_counts)}장")
print(f"  이미지 개수 분포: {dict(Counter(image_counts))}")
print()

print("[IMAGE BY TYPE] 타입별 이미지 개수")
print("-" * 80)
for news_type in ["standard", "visual", "data"]:
    if news_type in image_by_type:
        counts = image_by_type[news_type]
        print(f"  {news_type.upper()}:")
        print(f"    - 평균: {sum(counts) / len(counts):.1f}장")
        print(f"    - 범위: {min(counts)}-{max(counts)}장")
        print(f"    - 분포: {dict(Counter(counts))}")
print()

# 중복 이미지 감지 (Phase 1 개선 효과 확인)
# 참고: 실제 중복 여부는 HTML 생성 결과를 봐야 하지만,
# 이미지 개수로 간접 확인 가능 (이전 테스트와 비교)

print("[IMPROVEMENT] Phase 1 개선 효과 분석")
print("-" * 80)

# 이전 테스트 (12:29) 데이터와 비교
try:
    with open("test_report_20260207_122946.json", "r", encoding="utf-8") as f:
        old_report = json.load(f)

    old_image_counts = []
    for result in old_report["results"]:
        old_image_counts.append(result["images"]["total_count"])

    print(f"  이전 테스트 평균 이미지: {sum(old_image_counts) / len(old_image_counts):.1f}장")
    print(f"  Phase 1 후 평균 이미지: {sum(image_counts) / len(image_counts):.1f}장")

    diff = (sum(image_counts) / len(image_counts)) - (sum(old_image_counts) / len(old_image_counts))
    print(f"  차이: {diff:+.1f}장 ({'감소' if diff < 0 else '증가'})")
    print()

except FileNotFoundError:
    print("  (이전 테스트 리포트 없음)")
    print()

# 타입 분포 문제 분석
print("[WARNING] 타입 분포 문제 분석")
print("-" * 80)
type_dist = report["summary"]["type_distribution"]
total = sum(type_dist.values())

print(f"  현재: Standard {type_dist['standard']/total*100:.1f}% | Visual {type_dist['visual']/total*100:.1f}% | Data {type_dist['data']/total*100:.1f}%")
print(f"  목표: Standard 80% | Visual 15% | Data 5%")
print()

# Data 타입 과다 검출 원인 분석
print("  Data 타입 과다 검출 케이스:")
data_cases = [r for r in report["results"] if r["structure"]["news_type"] == "data"]
for case in data_cases[:5]:  # 상위 5개만
    keyword = case["keyword"]
    img_count = case["images"]["total_count"]
    body_len = case["structure"]["body_length"]
    print(f"    - {keyword}: 이미지 {img_count}장, 본문 {body_len}자")

print()

# 품질 문제 분석
print("[WARNING] 품질 문제 케이스")
print("-" * 80)
short_cases = [r for r in report["results"] if "BODY_TOO_SHORT" in str(r["issues"])]
long_cases = [r for r in report["results"] if "BODY_TOO_LONG" in str(r["issues"])]

print(f"  BODY_TOO_SHORT ({len(short_cases)}건):")
for case in short_cases:
    print(f"    - {case['keyword']}: {case['structure']['body_length']}자")

print(f"\n  BODY_TOO_LONG ({len(long_cases)}건):")
for case in long_cases:
    print(f"    - {case['keyword']}: {case['structure']['body_length']}자")

print()
print("=" * 80)
print("  분석 완료")
print("=" * 80)
