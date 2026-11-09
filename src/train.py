"""
train.py — 모델 학습, 저장, 모델 버전(SHA256 앞 12자리) 계산

모델: scikit-learn RandomForestRegressor (random_state 고정)
베이스라인: 학습 데이터 cnt 평균값, hr별 평균값
"""

import hashlib
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import RandomForestRegressor

sys.path.insert(0, str(Path(__file__).parent))
import data as data_mod
import run_log

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def _model_version(path: Path) -> str:
    """모델 파일 SHA256 앞 12자리를 버전으로 사용."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def train(cfg: dict):
    """학습 데이터로 모델을 훈련하고 저장한다."""
    # 데이터 로드
    train_df, _ = data_mod.run(cfg)
    features, target = data_mod.get_features(cfg)

    X_train = train_df[features]
    y_train = train_df[target]

    # 모델 학습
    params = cfg["model"]["params"]
    log.info("모델 학습 시작: %s", cfg["model"]["type"])
    model = RandomForestRegressor(**params)
    model.fit(X_train, y_train)
    log.info("모델 학습 완료")

    # 베이스라인 저장 (hr별 평균)
    baseline_mean = float(y_train.mean())
    baseline_hr   = train_df.groupby("hr")[target].mean().to_dict()
    log.info("베이스라인 — 전체 평균: %.2f 대/시간", baseline_mean)

    # 모델 저장
    model_path = Path(cfg["paths"]["model"])
    model_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "model":         model,
        "features":      features,
        "baseline_mean": baseline_mean,
        "baseline_hr":   baseline_hr,
    }
    joblib.dump(payload, model_path)
    log.info("모델 저장: %s", model_path)

    version = _model_version(model_path)
    log.info("모델 버전(SHA256[:12]): %s", version)

    run_log.save(
        stage="train",
        status="success",
        extra={
            "model_version": version,
            "model_path":    str(model_path),
            "n_train":       len(X_train),
            "features":      features,
        },
    )
    return model_path, version


if __name__ == "__main__":
    cfg_path = Path("config/config.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    train(cfg)
