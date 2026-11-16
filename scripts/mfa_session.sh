#!/usr/bin/env bash
# mfa_session.sh — MFA 인증으로 임시 자격 증명을 받아 ~/.aws/credentials 의 [mfa] 프로필에 저장
#
# 배경: 계정 정책(StudentSelfManagement)이 MFA 없이 호출한 요청을 모두 거부한다.
#       액세스 키만 쓰는 CLI는 MFA 미인증으로 취급되므로 임시 자격 증명이 필요하다.
#
# 사용: bash scripts/mfa_session.sh <인증 앱 6자리 코드>
#       이후 AWS_PROFILE=mfa 로 aws 명령 실행 (.env 에 AWS_PROFILE=mfa 를 넣으면 make 명령에 자동 적용)
#
# 비밀 값(키, 토큰)은 화면에 출력하지 않고 저장소 밖(~/.aws/credentials)에만 저장한다.

set -euo pipefail

CODE="${1:?사용법: bash scripts/mfa_session.sh <MFA 6자리 코드>}"
SRC_PROFILE="${SOURCE_PROFILE:-default}"   # 장기 액세스 키가 있는 프로필
PROFILE="${MFA_PROFILE:-mfa}"              # 임시 자격 증명을 저장할 프로필
DURATION="${DURATION:-43200}"              # 유효 시간(초), 기본 12시간
REGION="${AWS_REGION:-ap-northeast-2}"

# AWS_PROFILE 이 mfa 로 설정돼 있어도 원본 키로 발급받도록 환경변수 무시
unset AWS_PROFILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

SERIAL=$(aws iam list-mfa-devices --profile "$SRC_PROFILE" \
  --query 'MFADevices[0].SerialNumber' --output text)
if [ -z "$SERIAL" ] || [ "$SERIAL" = "None" ]; then
  echo "❌ 등록된 MFA 장치가 없음"
  exit 1
fi

read -r AK SK ST EXP < <(aws sts get-session-token --profile "$SRC_PROFILE" \
  --serial-number "$SERIAL" --token-code "$CODE" --duration-seconds "$DURATION" \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken,Expiration]' --output text)

aws configure set aws_access_key_id     "$AK" --profile "$PROFILE"
aws configure set aws_secret_access_key "$SK" --profile "$PROFILE"
aws configure set aws_session_token     "$ST" --profile "$PROFILE"
aws configure set region                "$REGION" --profile "$PROFILE"

echo "✅ MFA 임시 자격 증명 저장 완료 — 프로필: $PROFILE, 만료: $EXP"
echo "   사용: export AWS_PROFILE=$PROFILE"
