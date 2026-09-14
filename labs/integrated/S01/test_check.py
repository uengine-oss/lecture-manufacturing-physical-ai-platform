"""통합반 S01 점검 — 매핑 표·값 하나 설명·노트북 전체 실행.

실행: cd lecture/system && PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S01 -q
정답본 검사: LAB_SOLUTION=1 을 앞에 붙인다.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import nbformat
import pytest

from hydops.b1_data import uci

HERE = Path(__file__).resolve().parent
NB_DIR = HERE / "solution" if os.environ.get("LAB_SOLUTION") == "1" else HERE
NB_PATH = NB_DIR / "S01_sensor_flow.ipynb"


def _cells(tag: str) -> list[str]:
    nb = nbformat.read(NB_PATH, as_version=4)
    return [c.source for c in nb.cells if c.cell_type == "code" and tag in c.metadata.get("tags", [])]


def _exec_tag(tag: str, ns: dict | None = None) -> dict:
    ns = ns if ns is not None else {}
    ns.setdefault("____", None)
    src = _cells(tag)
    assert src, f"'{tag}' 태그가 붙은 셀이 없다 — 셀을 지우지 말 것"
    for s in src:
        # 표를 출력하는 마지막 줄(pd.DataFrame(...).T)은 검사에 필요 없다
        lines = [ln for ln in s.splitlines() if not ln.startswith("pd.DataFrame")]
        exec("\n".join(lines), ns)
    return ns


def test_mapping_table_matches_provided_code():
    ns = _exec_tag("mapping")
    table = ns["SENSOR_TABLE"]
    assert {"TS1", "PS1", "FS1"} <= set(table)  # 경험자가 센서 한 줄을 더해도 된다
    for sid in ("TS1", "PS1", "FS1"):
        row = table[sid]
        ref = uci.SENSOR_MAP[sid]
        assert row["file"] == ref["file"], f"{sid} file 빈칸"
        assert row["hz"] == ref["hz"], f"{sid} hz 빈칸"
        assert row["unit"] == ref["unit"], f"{sid} unit 빈칸"
        assert row["quantity"] == ref["quantity"]
        assert row["asset_id"] == "HYD-01"
        assert row["sensor_id"] == f"HYD-01.{sid}", f"{sid} sensor_id 는 '설비ID.센서코드' 모양"


def test_hz_agrees_with_raw_file_columns():
    ns = _exec_tag("mapping")
    for sid in ("TS1", "PS1", "FS1"):
        row = ns["SENSOR_TABLE"][sid]
        with open(uci.RAW / uci.SENSOR_MAP[sid]["file"]) as f:
            n_cols = len(f.readline().split("\t"))
        assert row["hz"] == n_cols // 60, f"{sid}: 원본 한 줄 {n_cols}칸 / 60초"


def test_one_value_is_explained():
    ns = _exec_tag("one_value")
    one_value = ns["ONE_VALUE"]
    ds = uci.load_reduced()
    rows = uci.cycle_observations(ds, 100, "HYD-01", datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc))
    ref = next(r for r in rows if r["sensor_id"] == "TS1" and r["elapsed_s"] == 30)
    assert one_value["asset_id"] == ref["asset_id"]
    assert isinstance(one_value["raw_value"], (int, float)) and abs(one_value["raw_value"] - ref["raw_value"]) < 0.001
    assert one_value["unit"] == ref["unit"]
    assert one_value["source_file"] == "TS1.txt"
    assert one_value["is_synthetic"] is False


def test_notebook_runs_top_to_bottom():
    from nbclient import NotebookClient

    nb = nbformat.read(NB_PATH, as_version=4)
    NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(NB_DIR)}}).execute()
    check = next(c for c in nb.cells if "check" in c.metadata.get("tags", []))
    text = "".join(o.get("text", "") for o in check.outputs if o.output_type == "stream")
    assert "모든 빈칸 통과" in text, text
    saved = NB_DIR / "saved" / "S01_replay_observations.csv"
    assert saved.exists()
    assert sum(1 for _ in open(saved)) == 540 + 1  # 사이클 3개 × 센서 3개 × 60초 + 머리줄
