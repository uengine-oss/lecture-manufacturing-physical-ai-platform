"""S05 · 예측·이상감지·근거·작업 지침의 역할 구분 (정답본).

값은 FORECAST(앞으로의 값을 예측) / DETECT(지금 이상인지 판정) / EVIDENCE(무엇이 허용되는지의 근거 문서) /
GUIDE(판단 순서·중단 규칙) / TOOL(조회·검사·실행 기능) 중 하나다.
"""

ROLE = {
    "hydops/b5_detect/zeroshot.py (Chronos-Bolt tiny)": "FORECAST",
    "hydops/b5_detect/detector.py (ThresholdDetector 60°C·10초)": "DETECT",
    "hydops/b6_sop/docs/SOP-LOAD-001_v1.md": "EVIDENCE",
    "skills/hydraulic-cooling-response/SKILL.md": "GUIDE",
    "hydops/b7_agent/tools.py search_sop": "TOOL",
}

# 사건(event)을 만드는 필수 경로는 무엇인가? (FORECAST 또는 DETECT)
EVENT_PATH = "DETECT"

# SKILL.md 를 근거로 인용해도 되는가?
SKILL_IS_CITABLE = False
