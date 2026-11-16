"""
run_log.py — 실행 기록 공통 함수

runs/<UTC시각>_<단계>.json 형식으로 자동 저장.
사람이 손으로 쓰지 않고 스크립트가 자동으로 남긴다.

모든 기록에 공통으로 들어가는 항목 (과제 요구: 시각, 성공 여부, Git 커밋, 모델 버전, 입력, 설정, 결과 위치):
  started_at / finished_at   단계 시작·종료 시각 (UTC)
  status                     success / failed
  git_commit / git_dirty     코드 버전, 커밋되지 않은 변경 여부
  input                      데이터 파일 경로와 SHA256
  config                     설정 파일 SHA256과 주요 설정값
단계별 추가 항목 (extra): model_version, metrics, outputs(결과 위치) 등
"""

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

CONFIG_PATH = Path("config/config.yaml")

_started_at = None


def start():
    """단계 시작 시각을 기록한다. pipeline.py가 단계 시작 직전에 호출."""
    global _started_at
    _started_at = datetime.now(timezone.utc)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_info() -> tuple[str, bool]:
    """현재 git commit hash와 dirty 여부를 반환."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], text=True
        ).strip()
        return commit, bool(status)
    except Exception:
        return "unknown", False


def _config_info() -> tuple[dict, dict]:
    """설정 파일 해시·주요 값과, 설정에 적힌 입력 데이터의 경로·해시를 반환."""
    if not CONFIG_PATH.exists():
        return {"path": str(CONFIG_PATH), "sha256": None}, {}
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    config = {
        "path":   str(CONFIG_PATH),
        "sha256": sha256_file(CONFIG_PATH),
        "split":  cfg.get("split"),
        "model":  cfg.get("model"),
    }

    data_path = Path(cfg["paths"]["raw_data"])
    data = {
        "data_path":   str(data_path),
        "data_sha256": sha256_file(data_path) if data_path.exists() else None,
    }
    return config, data


def save(stage: str, status: str, extra: dict = None, error: str = None,
         started_at: datetime = None) -> Path:
    """
    실행 기록을 runs/ 디렉토리에 JSON으로 저장.

    Args:
        stage:  파이프라인 단계 이름 (data / train / evaluate / deploy / invoke)
        status: "success" 또는 "failed"
        extra:  추가 정보 (model_version, metrics, outputs 등)
        error:  실패 시 에러 메시지
        started_at: 시작 시각 (셸 스크립트에서 호출할 때 지정, 없으면 start() 값 사용)

    Returns:
        저장된 파일 경로
    """
    global _started_at
    finished = datetime.now(timezone.utc)
    started = started_at or _started_at or finished
    _started_at = None

    run_id = f"{started.strftime('%Y%m%dT%H%M%SZ')}_{stage}"
    commit, dirty = _git_info()
    config, data = _config_info()

    record = {
        "run_id":      run_id,
        "stage":       stage,
        "started_at":  started.isoformat(),
        "finished_at": finished.isoformat(),
        "status":      status,
        "git_commit":  commit,
        "git_dirty":   dirty,
        "error":       error,
        "input":       data,
        "config":      config,
    }
    if extra:
        record.update(extra)

    runs_dir = Path("runs")
    runs_dir.mkdir(exist_ok=True)
    out = runs_dir / f"{run_id}.json"
    with open(out, "w") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"[run_log] 기록 저장: {out}")
    return out


if __name__ == "__main__":
    # 셸 스크립트(scripts/deploy.sh, invoke.sh)에서 같은 형식으로 기록을 남기기 위한 입구
    #   python src/run_log.py --stage deploy --status success \
    #       --started-at 2026-11-17T01:00:00+00:00 --extra-file /tmp/extra.json [--error "..."]
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--status", required=True, choices=["success", "failed"])
    ap.add_argument("--started-at")
    ap.add_argument("--extra-file")
    ap.add_argument("--error")
    a = ap.parse_args()

    extra = json.loads(Path(a.extra_file).read_text()) if a.extra_file else None
    started = datetime.fromisoformat(a.started_at) if a.started_at else None
    save(a.stage, a.status, extra=extra, error=a.error, started_at=started)
