"""
run_log.py — 실행 기록 공통 함수

runs/<UTC시각>_<단계>.json 형식으로 자동 저장.
사람이 손으로 쓰지 않고 스크립트가 자동으로 남긴다.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _git_info() -> tuple[str, bool]:
    """현재 git commit hash와 dirty 여부를 반환."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True
        ).strip()
        return commit, bool(status)
    except Exception:
        return "unknown", False


def save(stage: str, status: str, extra: dict = None, error: str = None) -> Path:
    """
    실행 기록을 runs/ 디렉토리에 JSON으로 저장.

    Args:
        stage:  파이프라인 단계 이름 (data / train / evaluate / deploy / invoke)
        status: "success" 또는 "failed"
        extra:  추가 정보 (model_version, metrics 등)
        error:  실패 시 에러 메시지

    Returns:
        저장된 파일 경로
    """
    now = datetime.now(timezone.utc)
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{stage}"
    commit, dirty = _git_info()

    record = {
        "run_id":      run_id,
        "stage":       stage,
        "started_at":  now.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status":      status,
        "git_commit":  commit,
        "git_dirty":   dirty,
        "error":       error,
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
