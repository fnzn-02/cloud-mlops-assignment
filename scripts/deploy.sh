#!/usr/bin/env bash
# deploy.sh — 모델 S3 보관 → 이미지 빌드·ECR push → Lambda 생성/업데이트 → 실행 기록
#
# 사용: bash scripts/deploy.sh            (또는 make deploy)
# 사전 조건: make train 완료, Docker 실행 중, MFA 임시 자격 증명(bash scripts/mfa_session.sh <코드>)
#
# 오류 재현용: LAMBDA_MODEL_PATH=/var/task/model/wrong.joblib bash scripts/deploy.sh
#              (이미지 안에 없는 모델 경로를 환경변수로 배포 → docs/incident.md 참고)
#
# 실행 기록: runs/<UTC시각>_deploy.json (성공·실패 모두). 계정 ID는 기록에서 <ACCOUNT_ID>로 가린다.

set -euo pipefail
cd "$(dirname "$0")/.."

# ── 설정 (.env → 기본값) ──────────────────────────────────────────────────────
if [ -f .env ]; then set -a; . ./.env; set +a; fi

REGION="${AWS_REGION:-ap-northeast-2}"
BUCKET="${BUCKET_NAME:?.env 에 BUCKET_NAME 필요}"
FUNCTION="${FUNCTION_NAME:-bike-demand-2022100185}"
ECR_REPO="${ECR_REPO_NAME:-bike-demand-2022100185}"
ROLE_NAME="${LAMBDA_ROLE_NAME:-yeonsung-lambda-basic-role}"
MODEL_PATH_IN_IMAGE="${LAMBDA_MODEL_PATH:-/var/task/model/model.joblib}"
OWNER_TAG="${OWNER_TAG:-2022100185}"
MODEL_FILE="data/model.joblib"
PY="${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)}"

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
STEP="사전 확인"
EXTRA_FILE="$(mktemp)"
echo '{}' > "$EXTRA_FILE"

mask() { sed -E 's/[0-9]{12}/<ACCOUNT_ID>/g'; }

# 실패 시: 어느 단계에서 실패했는지 기록하고 중단
on_error() {
  local code=$?
  echo ""
  echo "❌ 배포 실패 — 단계: $STEP (종료 코드 $code)"
  "$PY" src/run_log.py --stage deploy --status failed --started-at "$STARTED_AT" \
    --extra-file "$EXTRA_FILE" --error "단계 '$STEP' 실패 (종료 코드 $code)" || true
  rm -f "$EXTRA_FILE"
  exit "$code"
}
trap on_error ERR

echo "=============================="
echo "배포 시작 — 리전: $REGION / 버킷: $BUCKET / Lambda: $FUNCTION / ECR: $ECR_REPO"
echo "=============================="

# ── 0. 사전 확인 ──────────────────────────────────────────────────────────────
[ -f "$MODEL_FILE" ] || { echo "모델 파일 없음: $MODEL_FILE — 먼저 make train"; false; }
docker info >/dev/null 2>&1 || { echo "Docker가 실행 중이 아님 — Docker Desktop 실행 필요"; false; }
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text) || {
  echo "AWS 인증 실패 — bash scripts/mfa_session.sh <MFA 코드> 실행 후 AWS_PROFILE=mfa 확인"; false; }
GIT_COMMIT=$(git rev-parse --short HEAD)
MODEL_VERSION=$(shasum -a 256 "$MODEL_FILE" | cut -c1-12)
IMAGE_TAG="${MODEL_VERSION}-${GIT_COMMIT}"
MODEL_S3_URI="s3://${BUCKET}/models/${MODEL_VERSION}/model.joblib"
ECR_HOST="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
ECR_URI="${ECR_HOST}/${ECR_REPO}"
echo "모델 버전: $MODEL_VERSION / Git 커밋: $GIT_COMMIT / 이미지 태그: $IMAGE_TAG"

# ── 1. S3 버킷 (모델 보관본과 호출 결과 저장용) ───────────────────────────────
STEP="1/5 S3 버킷 확인·생성"; echo ""; echo "[$STEP]"
if aws s3api head-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null 2>&1; then
  echo "버킷 이미 존재: $BUCKET"
else
  aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
    --create-bucket-configuration LocationConstraint="$REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --region "$REGION" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-tagging --bucket "$BUCKET" --region "$REGION" \
    --tagging "TagSet=[{Key=owner,Value=${OWNER_TAG}},{Key=project,Value=cloud-mlops-assignment}]" \
    || echo "⚠️ 버킷 태그 지정 실패 (계속 진행)"
  echo "버킷 생성 완료: $BUCKET (퍼블릭 접근 차단)"
fi

# ── 2. 모델 보관본 업로드 ─────────────────────────────────────────────────────
STEP="2/5 모델 S3 업로드"; echo ""; echo "[$STEP]"
aws s3 cp "$MODEL_FILE" "$MODEL_S3_URI" --region "$REGION" \
  --metadata "model-version=${MODEL_VERSION},git-commit=${GIT_COMMIT}" --only-show-errors
echo "업로드 완료: $MODEL_S3_URI"

# ── 3. ECR 저장소 ─────────────────────────────────────────────────────────────
STEP="3/5 ECR 저장소 확인·생성"; echo ""; echo "[$STEP]"
if aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" >/dev/null 2>&1; then
  echo "ECR 저장소 이미 존재: $ECR_REPO"
else
  aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" \
    --tags "Key=owner,Value=${OWNER_TAG}" "Key=project,Value=cloud-mlops-assignment" >/dev/null
  echo "ECR 저장소 생성 완료: $ECR_REPO"
fi

# ── 4. 이미지 빌드·push ───────────────────────────────────────────────────────
STEP="4/5 이미지 빌드"; echo ""; echo "[4/5 이미지 빌드·검사·push]"
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "$ECR_HOST" >/dev/null
# Apple Silicon → Lambda(x86_64)용 linux/amd64 로 빌드
docker build --platform linux/amd64 --provenance=false -f service/Dockerfile -t "${ECR_URI}:${IMAGE_TAG}" .
# 재발 방지 1: 배포할 MODEL_PATH 가 이미지 안에 실제로 있는지 push 전에 확인 (docs/incident.md 오류 1)
STEP="4/5 이미지 내 MODEL_PATH 확인"
docker run --rm --platform linux/amd64 --entrypoint test "${ECR_URI}:${IMAGE_TAG}" -f "$MODEL_PATH_IN_IMAGE" || {
  echo "MODEL_PATH($MODEL_PATH_IN_IMAGE)가 이미지 안에 없음 — 배포 중단"
  echo "이미지 안의 /var/task 내용:"
  docker run --rm --platform linux/amd64 --entrypoint ls "${ECR_URI}:${IMAGE_TAG}" -R /var/task | grep -v "^$" || true
  false; }
echo "이미지 내 모델 확인: $MODEL_PATH_IN_IMAGE"
STEP="4/5 이미지 push"
docker push "${ECR_URI}:${IMAGE_TAG}" >/dev/null
IMAGE_DIGEST=$(aws ecr describe-images --repository-name "$ECR_REPO" --region "$REGION" \
  --image-ids imageTag="$IMAGE_TAG" --query 'imageDetails[0].imageDigest' --output text)
IMAGE_URI="${ECR_URI}@${IMAGE_DIGEST}"
echo "push 완료: ${ECR_REPO}:${IMAGE_TAG} (${IMAGE_DIGEST:0:19}…)"

# ── 5. Lambda 생성·업데이트 ───────────────────────────────────────────────────
STEP="5/5 Lambda 배포"; echo ""; echo "[$STEP]"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
ENV_VARS="Variables={MODEL_PATH=${MODEL_PATH_IN_IMAGE}}"

if aws lambda get-function --function-name "$FUNCTION" --region "$REGION" >/dev/null 2>&1; then
  echo "기존 함수 업데이트..."
  aws lambda update-function-code --function-name "$FUNCTION" --region "$REGION" \
    --image-uri "$IMAGE_URI" >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION" --region "$REGION"
  aws lambda update-function-configuration --function-name "$FUNCTION" --region "$REGION" \
    --environment "$ENV_VARS" --memory-size 1024 --timeout 30 >/dev/null
  aws lambda wait function-updated-v2 --function-name "$FUNCTION" --region "$REGION"
else
  echo "신규 함수 생성 (실행 역할: $ROLE_NAME)..."
  aws lambda create-function --function-name "$FUNCTION" --region "$REGION" \
    --package-type Image --code ImageUri="$IMAGE_URI" --role "$ROLE_ARN" \
    --memory-size 1024 --timeout 30 --architectures x86_64 \
    --environment "$ENV_VARS" \
    --tags "owner=${OWNER_TAG},project=cloud-mlops-assignment" >/dev/null
  aws lambda wait function-active-v2 --function-name "$FUNCTION" --region "$REGION"
fi

# 재발 방지 2: 정상 입력 1건을 실제로 호출해 200이 아니면 배포 실패로 기록 (docs/incident.md 오류 1·2)
#   첫 호출은 콜드 스타트라 시간이 걸리므로 소요 시간도 함께 기록한다
STEP="배포 후 정상 입력 확인(smoke test)"; echo ""; echo "[$STEP]"
SMOKE_OUT="$(mktemp)"
SMOKE_T0=$(date +%s)
aws lambda invoke --function-name "$FUNCTION" --region "$REGION" \
  --cli-binary-format raw-in-base64-out --payload fileb://tests/test_inputs/normal_01.json \
  "$SMOKE_OUT" >/dev/null
SMOKE_SEC=$(( $(date +%s) - SMOKE_T0 ))
SMOKE_STATUS=$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("statusCode"))' "$SMOKE_OUT" 2>/dev/null || echo none)
echo "응답: $(cat "$SMOKE_OUT") (${SMOKE_SEC}초)"
rm -f "$SMOKE_OUT"
[ "$SMOKE_STATUS" = "200" ] || { echo "정상 입력이 200이 아님 → 배포 실패"; false; }

# 배포된 실제 설정을 조회해 기록 (계정 ID 가림)
STEP="기록 저장"
aws lambda get-function-configuration --function-name "$FUNCTION" --region "$REGION" \
  --query '{function_name:FunctionName, state:State, last_update_status:LastUpdateStatus, last_modified:LastModified, code_sha256:CodeSha256, memory_mb:MemorySize, timeout_s:Timeout, architectures:Architectures, package_type:PackageType, role:Role, environment:Environment.Variables}' \
  --output json | mask > "${EXTRA_FILE}.fn"

"$PY" - "$EXTRA_FILE" "${EXTRA_FILE}.fn" <<PYEOF
import json, sys
extra_path, fn_path = sys.argv[1], sys.argv[2]
extra = {
    "region":        "${REGION}",
    "model_version": "${MODEL_VERSION}",
    "model_s3_uri":  "${MODEL_S3_URI}",
    "image_tag":     "${IMAGE_TAG}",
    "image_uri":     "<ACCOUNT_ID>.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}@${IMAGE_DIGEST}",
    "lambda":        json.load(open(fn_path)),
    "smoke_test":    {"input": "tests/test_inputs/normal_01.json", "status": ${SMOKE_STATUS}, "seconds": ${SMOKE_SEC}},
    "outputs":       ["${MODEL_S3_URI}", "lambda:${FUNCTION}"],
}
json.dump(extra, open(extra_path, "w"), ensure_ascii=False)
PYEOF
rm -f "${EXTRA_FILE}.fn"
"$PY" src/run_log.py --stage deploy --status success --started-at "$STARTED_AT" --extra-file "$EXTRA_FILE"
rm -f "$EXTRA_FILE"

echo ""
echo "=============================="
echo "✅ 배포 완료 — Lambda: $FUNCTION / 모델 버전: $MODEL_VERSION / MODEL_PATH: $MODEL_PATH_IN_IMAGE"
echo "   다음: bash scripts/invoke.sh (또는 make invoke)"
echo "=============================="
