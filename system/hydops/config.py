"""전체 시스템 설정.

모든 임계값은 교육용 가정값이며 UCI 설비의 운전 기준이 아니다 (실라버스 'Skill과 조치 프로세스 계약').
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"

# API 키는 강의 저장소에 복사하지 않고 플랫폼 .env 에서 읽는다.
_ENV_CANDIDATES = [
    ROOT / ".env",
    Path(os.environ.get("HYDOPS_ENV_FILE", "/Users/uengine/uengine-platform/process-gpt/.env")),
]
for _p in _ENV_CANDIDATES:
    if _p.exists():
        load_dotenv(_p, override=False)


@dataclass(frozen=True)
class Settings:
    pg_dsn: str = os.environ.get("HYDOPS_PG_DSN", "postgresql://hydops:hydops@localhost:55432/hydops")
    neo4j_uri: str = os.environ.get("HYDOPS_NEO4J_URI", "bolt://localhost:57687")
    neo4j_user: str = os.environ.get("HYDOPS_NEO4J_USER", "neo4j")
    neo4j_password: str = os.environ.get("HYDOPS_NEO4J_PASSWORD", "hydops-lecture")

    llm_model: str = os.environ.get("HYDOPS_LLM_MODEL", "gpt-4.1-mini")
    embedding_model: str = os.environ.get("HYDOPS_EMBEDDING_MODEL", "text-embedding-3-small")
    # offline: LLM/임베딩 없이 같은 Skill 순서를 코드로 따르는 결정적 에이전트 (테스트·장애 대비)
    agent_mode: str = os.environ.get("HYDOPS_AGENT_MODE", "llm" if os.environ.get("OPENAI_API_KEY") else "offline")


@dataclass(frozen=True)
class Thresholds:
    """실라버스 예시 설정: 60°C 초과 10초 지속 → 경보, 부하 1.0→0.8, 30초 후 55°C 이하 10초 유지 → 회복."""

    alarm_temp_c: float = 60.0
    alarm_sustain_s: int = 10
    recovery_temp_c: float = 55.0
    recovery_sustain_s: int = 10
    verify_wait_s: int = 30
    verify_window_s: int = 60
    # 재측정 창에서 유효 관측 비율이 이보다 낮으면 '데이터 부족'으로 판정을 보류한다
    verify_min_valid_ratio: float = 0.7
    default_load: float = 1.0
    reduced_load: float = 0.8
    min_load: float = 0.6  # 허용 조치 값 범위 (0.6 ~ 1.0)
    max_load: float = 1.0
    max_action_attempts: int = 1  # 반복 조치 억제
    rule_version: str = "temp-sustain-v1"


# 품질 검사 기준 (B2)
@dataclass(frozen=True)
class QualityRules:
    physical_min: dict = field(default_factory=lambda: {"TS1": -10.0, "PS1": 0.0, "FS1": 0.0})
    physical_max: dict = field(default_factory=lambda: {"TS1": 120.0, "PS1": 250.0, "FS1": 30.0})
    # UCI 정상 사이클의 1초 최대 변화: TS1 0.23°C · PS1 40.3 bar · FS1 10.9 L/min (펌프 기동) → 그보다 큰 점프만 급등
    spike_delta: dict = field(default_factory=lambda: {"TS1": 8.0, "PS1": 60.0, "FS1": 15.0})
    spike_window: int = 5
    stuck_run: int = 8  # 같은 값이 8초 이상 반복되면 고착
    gap_hold_s: int = 5  # 5초 이상 결측이면 판정 보류


SETTINGS = Settings()
TH = Thresholds()
QR = QualityRules()
