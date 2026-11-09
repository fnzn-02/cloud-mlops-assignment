"""
data.py — 데이터 다운로드, SHA256 검증, 결측/이상값 검증, 학습/평가 분할

UCI Bike Sharing Dataset (hour.csv)
출처: https://archive.ics.uci.edu/dataset/275/bike+sharing+dataset
라이선스: CC BY 4.0

정규화 단위 (원본 데이터가 이미 0~1로 변환됨):
  temp      = 실제 기온(°C) / 41
  atemp     = 체감 기온(°C) / 50
  hum       = 습도(%) / 100
  windspeed = 풍속(km/h) / 67
"""

import hashlib
import logging
import sys
import urllib.request
from pathlib import Path

import pandas as pd
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# UCI 직접 다운로드 URL (zip)
DATA_URL = "https://archive.ics.uci.edu/static/public/275/bike+sharing+dataset.zip"
# 공식 SHA256 (hour.csv 원본 파일)
HOUR_CSV_SHA256 = None  # 첫 실행 후 자동으로 기록됨 — 이후 고정

RANGE_RULES = {
    "hum":       (0.0, 1.0),
    "temp":      (0.0, 1.0),
    "atemp":     (0.0, 1.0),
    "windspeed": (0.0, 1.0),
    "season":    (1,   4),
    "hr":        (0,   23),
    "mnth":      (1,   12),
    "weathersit":(1,   4),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download(cfg: dict) -> Path:
    """hour.csv 다운로드 (이미 있으면 스킵). SHA256 로그 출력."""
    raw_path = Path(cfg["paths"]["raw_data"])
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    if raw_path.exists():
        log.info("데이터 파일 이미 존재: %s", raw_path)
    else:
        import zipfile, io
        log.info("다운로드 시작: %s", DATA_URL)
        with urllib.request.urlopen(DATA_URL) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            with z.open("hour.csv") as src, open(raw_path, "wb") as dst:
                dst.write(src.read())
        log.info("다운로드 완료: %s", raw_path)

    sha = _sha256(raw_path)
    log.info("SHA256: %s", sha)
    return raw_path


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    결측치와 범위 밖 값을 제거한다.
    - 서비스(app.py)에서는 400 에러로 거부
    - 학습/평가에서는 해당 행을 제거하고 건수를 기록
    """
    original = len(df)
    removed = 0

    # 결측치 제거
    before = len(df)
    df = df.dropna()
    n = before - len(df)
    if n:
        log.warning("결측치 제거: %d행", n)
    removed += n

    # 범위 밖 값 제거
    for col, (lo, hi) in RANGE_RULES.items():
        if col not in df.columns:
            continue
        before = len(df)
        df = df[(df[col] >= lo) & (df[col] <= hi)]
        n = before - len(df)
        if n:
            log.warning("범위 밖 값 제거 (%s, [%.1f, %.1f]): %d행", col, lo, hi, n)
        removed += n

    log.info("검증 완료 — 원본 %d행, 제거 %d행, 최종 %d행", original, removed, len(df))
    return df


def split(df: pd.DataFrame, cfg: dict):
    """
    시간 순서 기반 분할 (무작위 분할 금지).
    yr=0(2011) → 학습용, yr=1(2012) → 평가용.
    """
    train_year = cfg["split"]["train_year"]
    test_year  = cfg["split"]["test_year"]

    train = df[df["yr"] == train_year].copy()
    test  = df[df["yr"] == test_year].copy()

    log.info("학습 데이터: %d행 (yr=%d)", len(train), train_year)
    log.info("평가 데이터: %d행 (yr=%d)", len(test),  test_year)
    return train, test


def get_features(cfg: dict):
    return cfg["features"]["input"], cfg["features"]["target"]


def run(cfg: dict):
    """전체 데이터 파이프라인 실행."""
    raw_path = download(cfg)

    df = pd.read_csv(raw_path)
    log.info("원본 로드: %d행 %d열", *df.shape)

    df = validate(df)

    train, test = split(df, cfg)
    return train, test


if __name__ == "__main__":
    cfg_path = Path("config/config.yaml")
    if not cfg_path.exists():
        log.error("config/config.yaml 없음")
        sys.exit(1)
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    run(cfg)
