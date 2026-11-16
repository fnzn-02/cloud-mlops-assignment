#!/usr/bin/env bash
# cleanup.sh — 이 과제에서 만든 클라우드 자원 삭제 후 상태 재조회
#
# 사용: bash scripts/cleanup.sh          (삭제 전 확인 질문)
#       bash scripts/cleanup.sh --yes    (질문 없이 진행)
#
# 삭제 대상 (모두 .env 의 이름, 학번이 붙은 본인 자원만):
#   Lambda 함수, CloudWatch 로그 그룹, ECR 저장소(이미지 포함), S3 버킷(모델 보관본·호출 결과 사본 포함)
# 삭제하지 않는 것: 학교 제공 IAM 역할(yeonsung-lambda-basic-role) 등 공용 자원
#
# 기록:
#   runs/<시각>_cleanup/before.txt   삭제 전 자원 목록과 크기
#   runs/<시각>_cleanup/after.txt    삭제 후 재조회 결과
#   runs/<시각>_cleanup.json         요약 (자원별 삭제 후 존재 여부)
# 로컬 runs/ 의 실행 기록은 Git에 남으므로 S3 사본을 지워도 증거는 보존된다.

set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then set -a; . ./.env; set +a; fi
REGION="${AWS_REGION:-ap-northeast-2}"
BUCKET="${BUCKET_NAME:?.env 에 BUCKET_NAME 필요}"
FUNCTION="${FUNCTION_NAME:-bike-demand-2022100185}"
ECR_REPO="${ECR_REPO_NAME:-bike-demand-2022100185}"
LOG_GROUP="/aws/lambda/${FUNCTION}"
PY="${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)}"

NOW_EPOCH=$(date -u +%s)
STARTED_AT="$(date -u -r "$NOW_EPOCH" +%Y-%m-%dT%H:%M:%S+00:00)"
RUN_ID="$(date -u -r "$NOW_EPOCH" +%Y%m%dT%H%M%SZ)_cleanup"
OUT_DIR="runs/${RUN_ID}"
mask() { sed -E 's/[0-9]{12}/<ACCOUNT_ID>/g'; }

echo "삭제 대상 (리전 $REGION):"
echo "  Lambda      $FUNCTION"
echo "  로그 그룹   $LOG_GROUP"
echo "  ECR 저장소  $ECR_REPO (이미지 포함)"
echo "  S3 버킷     $BUCKET (객체 포함)"
if [ "${1:-}" != "--yes" ]; then
  read -r -p "정말 삭제할까요? (yes 입력) " ans
  [ "$ans" = "yes" ] || { echo "취소"; exit 1; }
fi
mkdir -p "$OUT_DIR"

# ── 삭제 전 목록과 크기 (비용 산정 근거) ──────────────────────────────────────
{
  echo "## 삭제 전 상태 ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  echo "### Lambda"
  aws lambda get-function-configuration --function-name "$FUNCTION" --region "$REGION" \
    --query '{name:FunctionName,state:State,memory_mb:MemorySize,timeout_s:Timeout,last_modified:LastModified}' --output json 2>&1 || true
  echo "### CloudWatch 로그 그룹"
  aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" \
    --query 'logGroups[].{name:logGroupName,stored_bytes:storedBytes,retention_days:retentionInDays}' --output json 2>&1 || true
  echo "### ECR 이미지"
  aws ecr describe-images --repository-name "$ECR_REPO" --region "$REGION" \
    --query 'imageDetails[].{tags:imageTags[0],size_mb:imageSizeInBytes,pushed:imagePushedAt}' --output table 2>&1 || true
  echo "### S3 객체 요약"
  aws s3 ls "s3://${BUCKET}" --recursive --summarize --region "$REGION" 2>&1 | tail -2 || true
} | mask | tee "$OUT_DIR/before.txt"

# ── 삭제 (이미 없으면 건너뜀) ─────────────────────────────────────────────────
echo ""
echo "## 삭제"
aws lambda delete-function --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1 \
  && echo "Lambda 삭제: $FUNCTION" || echo "Lambda 없음(건너뜀)"
aws logs delete-log-group --log-group-name "$LOG_GROUP" --region "$REGION" 2>/dev/null \
  && echo "로그 그룹 삭제: $LOG_GROUP" || echo "로그 그룹 없음(건너뜀)"
aws ecr delete-repository --repository-name "$ECR_REPO" --region "$REGION" --force >/dev/null 2>&1 \
  && echo "ECR 저장소 삭제: $ECR_REPO" || echo "ECR 저장소 없음(건너뜀)"
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1; then
  aws s3 rm "s3://${BUCKET}" --recursive --region "$REGION" --only-show-errors
  aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION"
  echo "S3 버킷 삭제: $BUCKET"
else
  echo "S3 버킷 없음(건너뜀)"
fi

# ── 삭제 후 재조회 ────────────────────────────────────────────────────────────
sleep 5
check() {  # $1=이름, 나머지=조회 명령. 성공하면 남아 있음(remaining), 실패하면 삭제됨(deleted)
  local name=$1; shift
  local out; out=$("$@" 2>&1) && { echo "$name: remaining"; echo "$out" | head -3; } \
    || echo "$name: deleted ($(echo "$out" | grep -oE '[A-Za-z]*(NotFound|NoSuch)[A-Za-z]*|Not Found|404' | head -1))"
}
{
  echo "## 삭제 후 재조회 ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  check lambda      aws lambda get-function --function-name "$FUNCTION" --region "$REGION"
  check ecr         aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION"
  check s3          aws s3api head-bucket --bucket "$BUCKET" --region "$REGION"
  n=$(aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" --region "$REGION" --query 'length(logGroups)' --output text)
  [ "$n" = "0" ] && echo "log_group: deleted (조회 결과 0개)" || echo "log_group: remaining ($n개)"
  echo "### 이름에 학번이 들어간 남은 자원 검색"
  echo "Lambda: $(aws lambda list-functions --region "$REGION" --query "Functions[?contains(FunctionName,'${OWNER_TAG:-2022100185}')].FunctionName" --output text)"
  echo "ECR:    $(aws ecr describe-repositories --region "$REGION" --query "repositories[?contains(repositoryName,'${OWNER_TAG:-2022100185}')].repositoryName" --output text)"
  echo "S3:     $(aws s3api list-buckets --query "Buckets[?contains(Name,'${OWNER_TAG:-2022100185}')].Name" --output text)"
  echo "Logs:   $(aws logs describe-log-groups --region "$REGION" --log-group-name-prefix /aws/lambda/bike-demand --query 'logGroups[].logGroupName' --output text)"
} | mask | tee "$OUT_DIR/after.txt"

# ── 요약 기록 ─────────────────────────────────────────────────────────────────
EXTRA="$(mktemp)"
set +e   # 남은 자원이 있어도(종료 코드 3) 실패 기록은 남긴다
"$PY" - "$OUT_DIR/after.txt" "$EXTRA" "$RUN_ID" <<'PYEOF'
import json, sys
after, extra_path, run_id = sys.argv[1:4]
state = {}
for line in open(after):
    for k in ("lambda", "ecr", "s3", "log_group"):
        if line.startswith(k + ":"):
            state[k] = line.split(":", 1)[1].strip().split()[0]
json.dump({"resources_after": state, "outputs": [f"runs/{run_id}/before.txt", f"runs/{run_id}/after.txt"]},
          open(extra_path, "w"), ensure_ascii=False)
sys.exit(0 if state and all(v == "deleted" for v in state.values()) else 3)
PYEOF
rc=$?
if [ $rc -eq 0 ]; then
  "$PY" src/run_log.py --stage cleanup --status success --started-at "$STARTED_AT" --extra-file "$EXTRA"
  echo "✅ 정리 완료 — 모든 자원 삭제 확인"
else
  "$PY" src/run_log.py --stage cleanup --status failed --started-at "$STARTED_AT" --extra-file "$EXTRA" \
    --error "삭제 후에도 남은 자원이 있음 ($OUT_DIR/after.txt 참고)"
  echo "❌ 남은 자원 있음 — $OUT_DIR/after.txt 확인"
fi
rm -f "$EXTRA"
exit $rc
