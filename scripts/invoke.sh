#!/usr/bin/env bash
# invoke.sh — 배포된 Lambda를 테스트 입력으로 실제 호출하고 결과를 기록
#
# 사용: bash scripts/invoke.sh                       (tests/test_inputs/*.json 전부)
#       bash scripts/invoke.sh tests/test_inputs/normal_01.json ...   (일부만)
#
# 기대 결과: normal_*.json → statusCode 200, error_*.json → statusCode 400
# 결과 위치:
#   runs/<RUN_ID>/<케이스>.request.json   보낸 입력
#   runs/<RUN_ID>/<케이스>.response.json  Lambda 응답
#   runs/<RUN_ID>/<케이스>.log.txt        해당 요청의 CloudWatch 로그 끝부분 (--log-type Tail)
#   runs/<RUN_ID>_invoke.json             요약 (케이스별 기대/실제, 함수 설정, 성공 여부)
#   s3://<버킷>/runs/<RUN_ID>/             위 파일 사본
# 하나라도 기대와 다르면 status=failed 로 기록하고 종료 코드 1 (다음 처리 중단)

set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
REGION="${AWS_REGION:-ap-northeast-2}"
BUCKET="${BUCKET_NAME:?.env 에 BUCKET_NAME 필요}"
FUNCTION="${FUNCTION_NAME:-bike-demand-2022100185}"
PY="${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)}"

NOW_EPOCH=$(date -u +%s)
STARTED_AT="$(date -u -r "$NOW_EPOCH" +%Y-%m-%dT%H:%M:%S+00:00)"
RUN_ID="$(date -u -r "$NOW_EPOCH" +%Y%m%dT%H%M%SZ)_invoke"   # run_log 기록 이름과 같은 시각
OUT_DIR="runs/${RUN_ID}"
mkdir -p "$OUT_DIR"

if [ $# -gt 0 ]; then INPUTS=("$@"); else INPUTS=(tests/test_inputs/*.json); fi

mask() { sed -E 's/[0-9]{12}/<ACCOUNT_ID>/g'; }

echo "=============================="
echo "Lambda 호출 — 함수: $FUNCTION / 리전: $REGION / 입력 ${#INPUTS[@]}건"
echo "=============================="

# 호출 시점의 함수 설정 (어떤 이미지·환경변수로 실행됐는지)
aws lambda get-function-configuration --function-name "$FUNCTION" --region "$REGION" \
  --query '{last_modified:LastModified, code_sha256:CodeSha256, environment:Environment.Variables, state:State}' \
  --output json | mask > "$OUT_DIR/_function_config.json"

for input in "${INPUTS[@]}"; do
  name="$(basename "$input" .json)"
  case "$name" in normal_*) expected=200 ;; *) expected=400 ;; esac

  cp "$input" "$OUT_DIR/${name}.request.json"
  meta=$(aws lambda invoke --function-name "$FUNCTION" --region "$REGION" \
    --cli-binary-format raw-in-base64-out --payload "fileb://${input}" \
    --log-type Tail --output json "$OUT_DIR/${name}.response.json")
  echo "$meta" | "$PY" -c 'import json,sys,base64; print(base64.b64decode(json.load(sys.stdin).get("LogResult","")).decode())' \
    | mask > "$OUT_DIR/${name}.log.txt"
  echo "$meta" | "$PY" -c 'import json,sys; m=json.load(sys.stdin); print(json.dumps({"lambda_status": m.get("StatusCode"), "function_error": m.get("FunctionError")}))' \
    > "$OUT_DIR/${name}.meta.json"

  actual=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("statusCode","none"))' "$OUT_DIR/${name}.response.json" 2>/dev/null || echo none)
  if [ "$actual" = "$expected" ]; then icon="✅"; else icon="❌"; fi
  printf "%s %-20s 기대 %s / 실제 %s  " "$icon" "$name" "$expected" "$actual"
  "$PY" -c 'import json,sys; r=json.load(open(sys.argv[1])); print(r.get("predicted_cnt", r.get("errors", r.get("error", r))))' "$OUT_DIR/${name}.response.json" 2>/dev/null || echo
  echo "$expected" > "$OUT_DIR/${name}.expected"
done

# 요약 기록
SUMMARY_EXTRA="$(mktemp)"
set +e   # 불일치(종료 코드 3)여도 요약 기록은 남긴다
"$PY" - "$OUT_DIR" "$SUMMARY_EXTRA" "$FUNCTION" "$REGION" "$BUCKET" "$RUN_ID" <<'PYEOF'
import json, sys
from pathlib import Path
out_dir, extra_path, function, region, bucket, run_id = sys.argv[1:7]
d = Path(out_dir)
cases = []
for req in sorted(d.glob("*.request.json")):
    name = req.name[: -len(".request.json")]
    resp = json.loads((d / f"{name}.response.json").read_text())
    meta = json.loads((d / f"{name}.meta.json").read_text())
    expected = int((d / f"{name}.expected").read_text())
    actual = resp.get("statusCode") if isinstance(resp, dict) else None
    cases.append({
        "case": name,
        "expected_status": expected,
        "actual_status": actual,
        "ok": actual == expected,
        "predicted_cnt": resp.get("predicted_cnt") if isinstance(resp, dict) else None,
        "model_version": resp.get("model_version") if isinstance(resp, dict) else None,
        "request_id": resp.get("request_id") if isinstance(resp, dict) else None,
        "lambda_status": meta["lambda_status"],
        "function_error": meta["function_error"],
    })
    (d / f"{name}.expected").unlink()
n_ok = sum(c["ok"] for c in cases)
extra = {
    "function_name": function,
    "region": region,
    "function_config": json.loads((d / "_function_config.json").read_text()),
    "n_cases": len(cases),
    "n_ok": n_ok,
    "cases": cases,
    "outputs": [str(d), f"s3://{bucket}/runs/{run_id}/"],
}
json.dump(extra, open(extra_path, "w"), ensure_ascii=False)
print(f"\n결과: {n_ok}/{len(cases)} 기대와 일치")
sys.exit(0 if n_ok == len(cases) else 3)
PYEOF
rc=$?
set -e

STATUS=success; ERR_ARGS=()
if [ $rc -ne 0 ]; then STATUS=failed; ERR_ARGS=(--error "기대와 다른 응답이 있음 (runs/${RUN_ID}/ 참고)"); fi

"$PY" src/run_log.py --stage invoke --status "$STATUS" --started-at "$STARTED_AT" \
  --extra-file "$SUMMARY_EXTRA" ${ERR_ARGS[@]+"${ERR_ARGS[@]}"}
rm -f "$SUMMARY_EXTRA"

# S3에 결과 사본 업로드 (요약 기록 포함)
aws s3 cp "$OUT_DIR" "s3://${BUCKET}/runs/${RUN_ID}/" --recursive --region "$REGION" --only-show-errors
aws s3 cp "runs/${RUN_ID}.json" "s3://${BUCKET}/runs/${RUN_ID}/_summary.json" --region "$REGION" --only-show-errors
echo "결과 업로드: s3://${BUCKET}/runs/${RUN_ID}/"

[ "$STATUS" = success ] || { echo "❌ 일부 호출이 기대와 다름 — 다음 처리 중단"; exit 1; }
