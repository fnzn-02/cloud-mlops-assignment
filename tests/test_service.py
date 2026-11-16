"""
test_service.py — Lambda handler 로컬 테스트

AWS 연결 없이 handler 함수를 직접 호출해 입력 검증과 예측을 테스트한다.
로컬에서는 모델을 직접 로드해 _cache에 주입한다.
"""

import json
import sys
from pathlib import Path

import joblib
import yaml

# 경로 설정
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "service"))
sys.path.insert(0, str(ROOT / "src"))

import app as service

# ── 로컬 모델 직접 주입 (S3 없이 테스트) ────────────────────────────────────
cfg_path = ROOT / "config" / "config.yaml"
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)

model_path = ROOT / cfg["paths"]["model"]
if not model_path.exists():
    print("❌ 모델 파일 없음 — 먼저 `make train` 실행")
    sys.exit(1)

payload = joblib.load(model_path)
service._cache["model"]    = payload["model"]
service._cache["features"] = payload["features"]
service._cache["version"]  = "local-test"
service._cache["baseline_mean"] = payload["baseline_mean"]

# ── 테스트 케이스 ─────────────────────────────────────────────────────────────
test_cases = [
    ("정상 입력 01", "tests/test_inputs/normal_01.json", 200),
    ("정상 입력 02", "tests/test_inputs/normal_02.json", 200),
    ("정상 입력 03", "tests/test_inputs/normal_03.json", 200),
    ("오류: 필드 누락", "tests/test_inputs/error_missing.json", 400),
    ("오류: 범위 초과", "tests/test_inputs/error_range.json",   400),
    ("오류: 타입 오류", "tests/test_inputs/error_type.json",    400),
    ("오류: 정수 필드에 소수", "tests/test_inputs/error_float_int.json",   400),
    ("오류: 정답 필드 포함",   "tests/test_inputs/error_extra_field.json", 400),
    ("오류: 객체가 아닌 입력", "tests/test_inputs/error_not_object.json",  400),
]

passed = 0
failed = 0

print("\n" + "=" * 60)
print("로컬 Lambda 핸들러 테스트")
print("=" * 60)

for name, input_file, expected_status in test_cases:
    with open(ROOT / input_file) as f:
        event = json.load(f)

    result = service.handler(event, None)
    actual_status = result.get("statusCode", 500)

    ok = actual_status == expected_status
    icon = "✅" if ok else "❌"

    print(f"\n{icon} [{name}]")
    print(f"   기대: {expected_status} | 실제: {actual_status}")
    if actual_status == 200:
        print(f"   예측값: {result.get('predicted_cnt')} 대/시간")
    else:
        print(f"   에러: {result.get('errors', result.get('error', ''))}")

    if ok:
        passed += 1
    else:
        failed += 1

print("\n" + "=" * 60)
print(f"결과: {passed}개 통과 / {failed}개 실패")
print("=" * 60)

if failed > 0:
    sys.exit(1)
