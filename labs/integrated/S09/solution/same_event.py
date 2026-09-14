"""통합반 9회 실습 — 앱 화면의 '같은 사건 확인' 세 줄을 Python 으로 옮긴 것.

ops-console/index.html 의 computed sameUi · sameProcess · sameAction 과 같은 판정이다.
"""
from __future__ import annotations

____ = None  # 빈칸 표시


def same_event_checks(event_id: str, detail: dict, instance: dict | None) -> dict:
    """detail = GET {hydops_api}/api/events/{event_id}, instance = GET {platform_api}/process/instances/{id}"""
    actions = detail["actions"]
    return {
        "화면 event_id": detail["event"]["event_id"] == event_id,
        "프로세스 입력 event_id": instance is not None and instance["vars"]["event_id"] == event_id,
        # 조치 기록이 없으면(실행 전 종료) None — 실패가 아니라 해당 없음
        "조치 기록 event_id": all(a["event_id"] == event_id for a in actions) if actions else None,
    }


def instance_id_of(detail: dict) -> str | None:
    """사건에 대응된 프로세스 인스턴스 ID (event.process_ref)"""
    ref = detail["event"].get("process_ref")
    return ref["instance_id"] if ref else None
