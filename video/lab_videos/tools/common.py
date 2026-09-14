"""실습 영상 제작 공용 경로·도구."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

LECTURE = Path(__file__).resolve().parents[3]
SYSTEM = LECTURE / "system"
LV = LECTURE / "video" / "lab_videos"
SPECS = LV / "specs"
BUILD = LV / "build"
PY = str(SYSTEM / ".venv" / "bin" / "python")
ENV_FILE = "/Users/uengine/uengine-platform/process-gpt/.env"

TYPES = {"title", "concept", "image", "code", "task", "run", "apply_fix", "app", "quiz", "answer", "summary", "next"}
APP_ACTIONS = {"dashboard", "neo4j", "console", "platform_flow", "app_page", "notebook", "api"}


def load_spec(sid: str) -> dict:
    return json.loads((SPECS / f"{sid}.json").read_text())


def work_dir(spec: dict) -> Path:
    """실습 작업 사본: lecture/labs_work/<practical|integrated>/SXX — 원본 시작본은 건드리지 않는다."""
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
