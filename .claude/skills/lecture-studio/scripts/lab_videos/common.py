"""실습 영상 제작 공용 경로·도구."""
from __future__ import annotations

import json
import os
import shutil
import sys
import subprocess
from pathlib import Path

# 경로는 환경 변수로 받는다 — 스킬 폴더에서 실행해도 강의 저장소를 가리키도록.
LECTURE = Path(os.environ.get("LECTURE_ROOT", ".")).resolve()          # 강의 저장소 루트 (textbooks/, labs/, system/, materials/)
SYSTEM = Path(os.environ.get("SYSTEM_DIR", LECTURE / "system"))        # run 장면의 명령을 실행할 폴더
LV = Path(os.environ.get("LAB_VIDEOS_DIR", LECTURE / "video" / "lab_videos"))
SPECS = LV / "specs"
BUILD = LV / "build"
PY = os.environ.get("PYTHON", sys.executable)
ENV_FILE = os.environ.get("OPENAI_ENV_FILE", str(LECTURE / ".env"))   # OPENAI_API_KEY 가 들어 있는 .env

TYPES = {"title", "concept", "review", "image", "code", "task", "run", "apply_fix", "app", "quiz", "answer", "summary", "next"}
APP_ACTIONS = {"dashboard", "neo4j", "console", "platform_flow", "app_page", "notebook", "api"}


def load_spec(sid: str) -> dict:
    return json.loads((SPECS / f"{sid}.json").read_text())


def work_dir(spec: dict) -> Path:
    """실습 작업 사본: <LECTURE>/labs_work/<반 폴더>/<회차 폴더> — 원본 시작본은 건드리지 않는다.
    labs/<반>/<회차> 와 깊이가 같아야 테스트의 상대 경로(HERE.parents[2])가 그대로 동작한다."""
    lab = LECTURE / spec["lab"]
    return LECTURE / "labs_work" / lab.parent.name / lab.name


def fresh_work_copy(spec: dict) -> Path:
    src, dst = LECTURE / spec["lab"], work_dir(spec)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return dst


def rel_work(spec: dict) -> str:
    return str(Path("..") / work_dir(spec).relative_to(LECTURE))


def run_cmd(spec: dict, cmd: str, timeout: int = 600) -> subprocess.CompletedProcess:
    full = cmd.replace("{WORK}", rel_work(spec))
    return subprocess.run(["/bin/zsh", "-lc", full], cwd=SYSTEM, capture_output=True, text=True, timeout=timeout)


def outcome(proc: subprocess.CompletedProcess) -> str:
    return "pass" if proc.returncode == 0 else "fail"


def _block(text: str, name: str) -> tuple[int, int] | None:
    """최상위 def/class 블록의 [시작, 끝) 줄 범위."""
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith((f"def {name}(", f"class {name}(", f"class {name}:", f"async def {name}("))), None)
    if start is None:
        return None
    while start > 0 and lines[start - 1].startswith("@"):
        start -= 1
    end = next((j for j in range(start + 1, len(lines)) if lines[j] and not lines[j][0].isspace() and not lines[j].startswith((")", "]", "}", "#"))), len(lines))
    while end > start and not lines[end - 1].strip():
        end -= 1
    return start, end


def fixed_text(before: str, solution: str, function: str | None) -> str:
    if not function:
        return solution
    a, b = _block(before, function), _block(solution, function)
    if a is None or b is None:
        raise SystemExit(f"function {function} not found")
    bl, sl = before.split("\n"), solution.split("\n")
    return "\n".join(bl[: a[0]] + sl[b[0] : b[1]] + bl[a[1] :])


def apply_fix(spec: dict, file: str, function: str | None = None) -> tuple[str, str]:
    wd = work_dir(spec)
    before = (wd / file).read_text()
    after = fixed_text(before, (LECTURE / spec["lab"] / "solution" / file).read_text(), function)
    (wd / file).write_text(after)
    return before, after
