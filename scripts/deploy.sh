#!/usr/bin/env bash
# deploy.sh — S3 업로드 → ECR push → Lambda 생성/업데이트
# 사용: bash scripts/deploy.sh

set -euo pipefail

# ── .env 로드 ──────────────────────────────────────────────────────────────
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

REGION="${AWS_REGION:-ap-northeast-2}"
BUCKET="${BUCKET_NAME}"
FUNCTION="${FUNCTION_NAME:-bike-demand}"
ECR_REPO="${ECR_REPO_NAME:-bike-demand}"

echo "=============================="
echo "배포 시작"
echo "리전: $REGION"
echo "버킷: $BUCKET"
echo "Lambda: $FUNCTION"
echo "=============================="

# ── 계정 ID 확인 ───────────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "계정 ID: XXXX (가림)"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

# ── 1. 모델 버전 계산 ────────────────────────────────────────────────────────
MODEL_PATH="data/model.joblib"
if [ ! -f "$MODEL_PATH" ]; then
  echo "❌ 모델 파일 없음: $MODEL_PATH — 먼저 make train 실행"
  exit 1
fi
MODEL_VERSION=$(sha256sum "$MODEL_PATH" 2>/dev/null || shasum -a 256 "$MODEL_PATH" | awk '{print $1}')
MODEL_VERSION="${MODEL_VERSION:0:12}"
echo "모델 버전: $MODEL_VERSION"

MODEL_S3_URI="s3://${BUCKET}/models/${MODEL_VERSION}/model.joblib"

# ── 2. S3 버킷 생성 (없으면) ────────────────────────────────────────────────
echo ""
echo "[1/5] S3 버킷 확인/생성..."
if aws s3 ls "s3://${BUCKET}" --region "$REGION" 2>/dev/null; then
  echo "버킷 이미 존재: $BUCKET"
else
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
  echo "버킷 생성 완료: $BUCKET"
fi

# ── 3. 모델 S3 업로드 ───────────────────────────────────────────────────────
echo ""
echo "[2/5] 모델 S3 업로드..."
aws s3 cp "$MODEL_PATH" "$MODEL_S3_URI"
echo "업로드 완료: $MODEL_S3_URI"

# ── 4. ECR 저장소 생성 (없으면) + 이미지 push ──────────────────────────────
echo ""
echo "[3/5] ECR 저장소 확인/생성..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" 2>/dev/null || \
  aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION"
echo "ECR 저장소: $ECR_URI"

echo ""
echo "[4/5] Docker 이미지 빌드 및 ECR push..."
IMAGE_TAG="${MODEL_VERSION}"

# ECR 로그인
aws ecr get-login-password --region "$REGION" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Apple Silicon → linux/amd64 강제
docker build --platform linux/amd64 -f service/Dockerfile -t "${ECR_REPO}:${IMAGE_TAG}" .
docker tag "${ECR_REPO}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"
echo "이미지 push 완료: ${ECR_URI}:${IMAGE_TAG}"

# ── 5. Lambda 함수 생성 또는 업데이트 ──────────────────────────────────────
echo ""
echo "[5/5] Lambda 함수 배포..."

# IAM 역할 ARN 조회 (현재 사용자와 동일한 계정의 LabRole 또는 직접 생성한 역할)
ROLE_NAME="bike-demand-lambda-role"
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
  echo "IAM 역할 생성: $ROLE_NAME"
  # Lambda 신뢰 정책
  cat > /tmp/trust-policy.json << 'TRUST'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "lambda.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
TRUST
  ROLE_ARN=$(aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document file:///tmp/trust-policy.json \
    --query Role.Arn --output text)

  # S3 + CloudWatch 권한 부여
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess

  echo "IAM 역할 생성 완료: $ROLE_ARN"
  echo "역할 활성화 대기 (10초)..."
  sleep 10
fi

# Lambda 존재 여부 확인
LAMBDA_EXISTS=$(aws lambda get-function --function-name "$FUNCTION" --region "$REGION" 2>/dev/null && echo "yes" || echo "no")

if [ "$LAMBDA_EXISTS" = "yes" ]; then
  echo "Lambda 업데이트..."
  aws lambda update-function-code \
    --function-name "$FUNCTION" \
    --image-uri "${ECR_URI}:${IMAGE_TAG}" \
    --region "$REGION"
  sleep 5
  aws lambda update-function-configuration \
    --function-name "$FUNCTION" \
    --environment "Variables={MODEL_S3_URI=${MODEL_S3_URI},AWS_REGION_NAME=${REGION}}" \
    --region "$REGION"
else
  echo "Lambda 신규 생성..."
  aws lambda create-function \
    --function-name "$FUNCTION" \
    --package-type Image \
    --code ImageUri="${ECR_URI}:${IMAGE_TAG}" \
    --role "$ROLE_ARN" \
    --memory-size 1024 \
    --timeout 30 \
    --architectures x86_64 \
    --environment "Variables={MODEL_S3_URI=${MODEL_S3_URI},AWS_REGION_NAME=${REGION}}" \
    --region "$REGION"
fi

echo ""
echo "=============================="
echo "배포 완료!"
echo "MODEL_S3_URI: $MODEL_S3_URI"
echo "IMAGE_URI:    ${ECR_URI}:${IMAGE_TAG}"
echo "FUNCTION:     $FUNCTION"
echo "=============================="

# 배포 기록 저장
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)_deploy"
mkdir -p runs
cat > "runs/${RUN_ID}.json" << EOF
{
  "run_id": "${RUN_ID}",
  "stage": "deploy",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "success",
  "model_version": "${MODEL_VERSION}",
  "model_s3_uri": "${MODEL_S3_URI}",
  "image_uri": "${ECR_URI}:${IMAGE_TAG}",
  "function_name": "${FUNCTION}",
  "region": "${REGION}"
}
EOF
echo "배포 기록 저장: runs/${RUN_ID}.json"
