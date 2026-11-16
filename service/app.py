"""
app.py — Lambda 핸들러

환경변수:
  MODEL_S3_URI  s3://<버킷>/models/<버전>/model.joblib

입력 (JSON):
  {
    "season": 2, "mnth": 6, "hr": 17, "holiday": 0,
    "weekday": 3, "workingday": 1, "weathersit": 1,
    "temp": 0.72, "atemp": 0.6515, "hum": 0.42, "windspeed": 0.1642
  }

출력 (JSON):
  {
    "predicted_cnt": 348.1,
    "unit": "대/시간",
    "model_version": "8b6cf2669bbe",
    "run_id": "20261116T..."
  }

에러:
  400 — 입력 검증 실패 (필드 누락, 범위 밖, 타입 오류)
  500 — 서버 내부 오류 (모델 로드 실패 등)
"""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

import boto3
import joblib

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── 필수 입력 필드와 허용 범위 ──────────────────────────────────────────────
FIELDS = {
    "season":     {"type": int,   "min": 1,   "max": 4},
    "mnth":       {"type": int,   "min": 1,   "max": 12},
    "hr":         {"type": int,   "min": 0,   "max": 23},
    "holiday":    {"type": int,   "min": 0,   "max": 1},
    "weekday":    {"type": int,   "min": 0,   "max": 6},
    "workingday": {"type": int,   "min": 0,   "max": 1},
    "weathersit": {"type": int,   "min": 1,   "max": 4},
    "temp":       {"type": float, "min": 0.0, "max": 1.0},
    "atemp":      {"type": float, "min": 0.0, "max": 1.0},
    "hum":        {"type": float, "min": 0.0, "max": 1.0},
    "windspeed":  {"type": float, "min": 0.0, "max": 1.0},
}

FEATURE_ORDER = list(FIELDS.keys())

# ── 모델 캐시 (Lambda 컨테이너 재사용 시 재로드 방지) ────────────────────────
_cache = {}


def _load_model():
    """S3에서 model.joblib 를 다운로드해 캐시한다. 시작 시 경로 확인 포함."""
    if _cache:
        return _cache

    model_uri = os.environ.get("MODEL_S3_URI", "")
    if not model_uri.startswith("s3://"):
        raise RuntimeError(f"MODEL_S3_URI 환경변수가 올바르지 않음: '{model_uri}'")

    # s3://bucket/key 파싱
    without_scheme = model_uri[5:]
    bucket, _, key = without_scheme.partition("/")

    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))

    # 경로 존재 여부 확인 (명확한 에러 메시지를 위해)
    try:
        s3.head_object(Bucket=bucket, Key=key)
    except s3.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]
        raise RuntimeError(f"모델 파일을 찾을 수 없음 ({code}): s3://{bucket}/{key}")

    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        s3.download_fileobj(bucket, key, tmp)
        tmp_path = tmp.name

    try:
        # 모델 버전 = 파일 SHA256 앞 12자리 (src/train.py, scripts/deploy.sh와 동일한 방식)
        h = hashlib.sha256()
        with open(tmp_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        version = h.hexdigest()[:12]

        payload = joblib.load(tmp_path)
    finally:
        os.unlink(tmp_path)

    # S3 경로(models/<버전>/model.joblib)에 적힌 버전과 실제 파일 해시 비교
    parts = key.split("/")
    path_version = parts[-2] if len(parts) >= 2 else ""
    if path_version != version:
        log.warning("모델 버전 불일치 — 경로: %s, 파일 SHA256[:12]: %s", path_version, version)

    _cache["model"]   = payload["model"]
    _cache["features"] = payload["features"]
    _cache["version"] = version
    _cache["baseline_mean"] = payload["baseline_mean"]

    log.info("모델 로드 완료 — 버전: %s, URI: %s", version, model_uri)
    return _cache


def _validate(body: dict) -> tuple[list, dict]:
    """
    입력 검증.
    반환: (errors, cleaned_values)
    errors가 비어있으면 통과.
    """
    errors = []
    cleaned = {}

    for field, rule in FIELDS.items():
        if field not in body:
            errors.append(f"필수 필드 누락: '{field}'")
            continue

        raw = body[field]
        # 타입 변환 시도
        try:
            val = rule["type"](raw)
        except (ValueError, TypeError):
            errors.append(
                f"타입 오류: '{field}' — {rule['type'].__name__} 필요, 받은 값: {repr(raw)}"
            )
            continue

        # 범위 확인
        if not (rule["min"] <= val <= rule["max"]):
            errors.append(
                f"범위 오류: '{field}' = {val} — 허용 범위 [{rule['min']}, {rule['max']}]"
            )
            continue

        cleaned[field] = val

    return errors, cleaned


def _save_result_to_s3(run_id: str, payload: dict):
    """결과를 S3 runs/<run_id>/output.json 에 저장."""
    try:
        model_uri = os.environ.get("MODEL_S3_URI", "")
        bucket = model_uri[5:].split("/")[0]
        key = f"runs/{run_id}/output.json"
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-northeast-2"))
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False),
            ContentType="application/json",
        )
        log.info("결과 저장: s3://%s/%s", bucket, key)
    except Exception as e:
        log.warning("결과 S3 저장 실패 (무시): %s", e)


def handler(event, context):
    """Lambda 핸들러 진입점."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_invoke"

    # ── body 파싱 ────────────────────────────────────────────────────────────
    if isinstance(event, dict) and "body" in event:
        # API Gateway 형식
        try:
            body = json.loads(event["body"]) if isinstance(event["body"], str) else event["body"]
        except (json.JSONDecodeError, TypeError):
            return {"statusCode": 400, "body": json.dumps({"error": "body가 유효한 JSON이 아님"})}
    else:
        # aws lambda invoke 직접 호출 형식
        body = event

    # ── 입력 검증 ─────────────────────────────────────────────────────────────
    errors, cleaned = _validate(body)
    if errors:
        resp = {"statusCode": 400, "errors": errors}
        log.warning("입력 검증 실패: %s", errors)
        return resp

    # ── 모델 로드 및 예측 ─────────────────────────────────────────────────────
    try:
        cache = _load_model()
    except RuntimeError as e:
        log.error("모델 로드 실패: %s", e)
        return {"statusCode": 500, "error": str(e)}

    features = cache["features"]
    X = [[cleaned[f] for f in features]]
    predicted = float(cache["model"].predict(X)[0])
    predicted = round(max(0.0, predicted), 2)  # 음수 방지

    # ── 응답 구성 ─────────────────────────────────────────────────────────────
    result = {
        "statusCode": 200,
        "run_id": run_id,
        "predicted_cnt": predicted,
        "unit": "대/시간",
        "model_version": cache["version"],
        "input": cleaned,
    }

    _save_result_to_s3(run_id, result)
    log.info("예측 완료 — run_id: %s, predicted: %.2f", run_id, predicted)
    return result
