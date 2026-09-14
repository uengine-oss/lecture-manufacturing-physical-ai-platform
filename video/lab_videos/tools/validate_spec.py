"""사양 검증: python tools/validate_spec.py <ID|all> [--run]"""
import sys

from common import APP_ACTIONS, LECTURE, SPECS, TYPES, apply_fix, fresh_work_copy, load_spec, outcome, run_cmd

ORDER = ["title", "concept_block", "lab_block", "quiz", "answer", "summary", "next"]


def check(sid: str, do_run: bool) -> list[str]:
    s = load_spec(sid)
    errs = []
    for k in ("id", "class", "session", "title", "date", "textbook", "lab", "next", "scenes"):
        if k not in s:
            errs.append(f"missing {k}")
    if not (LECTURE / s["textbook"]).exists():
        errs.append("textbook not found")
    if not (LECTURE / s["lab"]).exists():
        errs.append("lab not found")
    sc = s["scenes"]
    types = [x["type"] for x in sc]
    if types[0] != "title" or types[-4:] != ["quiz", "answer", "summary", "next"]:
        errs.append(f"순서 위반: {types}")
    total_chars = 0
    for i, x in enumerate(sc, 1):
        t = x["type"]
        if t not in TYPES:
            errs.append(f"#{i} unknown type {t}")
        n = x.get("narration", "")
        total_chars += len(n)
        if not (80 <= len(n) <= 420):
            errs.append(f"#{i} {t} narration {len(n)}자 (80~420)")
        for key in ("image",):
            if x.get(key) and not (LECTURE / x[key]).exists():
                errs.append(f"#{i} image missing {x[key]}")
        if t == "code":
            p = LECTURE / x["file"]
            if not p.exists():
                errs.append(f"#{i} code file missing {x['file']}")
            else:
                n_lines = len(p.read_text().splitlines())
                a, b = x["lines"]
                if not (1 <= a <= b <= n_lines):
                    errs.append(f"#{i} lines {x['lines']} out of 1..{n_lines}")
        if t == "apply_fix":
            if not (LECTURE / s["lab"] / x["file"]).exists() or not (LECTURE / s["lab"] / "solution" / x["file"]).exists():
                errs.append(f"#{i} apply_fix file missing {x['file']}")
        if t == "app" and x.get("action") not in APP_ACTIONS:
            errs.append(f"#{i} app action {x.get('action')}")
        if t == "quiz" and len(x.get("questions", [])) != 3:
            errs.append(f"#{i} quiz 3문항 아님")
        if t == "answer" and len(x.get("answers", [])) != 3:
            errs.append(f"#{i} answer 3개 아님")
    est = total_chars / 7.0 / 60
    if not (6.5 <= est <= 13.5):
        errs.append(f"예상 길이 {est:.1f}분 (7~12분 권장)")
    if "run" not in types:
        errs.append("run 장면 없음 (실습을 실제로 실행해야 한다)")
    if do_run and not errs:
        fresh_work_copy(s)
        for i, x in enumerate(sc, 1):
            if x["type"] == "apply_fix":
                apply_fix(s, x["file"], x.get("function"))
            if x["type"] == "run":
                p = run_cmd(s, x["cmd"])
                got = outcome(p)
                tail = (p.stdout + p.stderr).strip().splitlines()[-2:]
                print(f"  run #{i}: expect={x['expect']} got={got} | {' / '.join(tail)[:160]}")
                if got != x["expect"]:
                    errs.append(f"#{i} run expect {x['expect']} got {got}")
    print(f"{sid}: {len(sc)} scenes, ~{est:.1f}분, {'OK' if not errs else 'ERR'}")
    for e in errs:
        print("   -", e)
    return errs


if __name__ == "__main__":
    ids = sorted(p.stem for p in SPECS.glob("*.json")) if sys.argv[1] == "all" else [sys.argv[1]]
    bad = sum(bool(check(i, "--run" in sys.argv)) for i in ids)
    sys.exit(1 if bad else 0)
