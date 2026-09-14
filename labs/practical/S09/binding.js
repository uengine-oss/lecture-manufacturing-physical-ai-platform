// S09 · 제조 운영 앱 바인딩 표 — app_templates/ops-console/index.html 의 fetch 호출을 한 표로 옮긴 것.
// {이름} 은 window.APP_CONFIG 의 키, {asset_id}·{event.*}·{workitem_id}·{draft}·{form.*} 는 화면에서 고른 값이다.
// TODO(학생): 사건 목록 관계, 사건 상세를 읽는 서버, 업무 시작 입력값, 승인 초안의 승인값 네 곳이 틀렸다.
window.APP_BINDING = {
  "assets":       {"method": "POST", "url": "{platform_api}/studio/schemas/{schema_name}/objects/Asset/fetch", "body": {"limit": 10}},
  "events":       {"method": "GET",  "url": "{platform_api}/studio/schemas/{schema_name}/objects/Asset/{asset_id}/related/HAS_SENSOR"},
  "event_detail": {"method": "GET",  "url": "{platform_api}/api/events/{event_id}"},
  "series":       {"method": "GET",  "url": "{hydops_api}/api/series?asset_id={asset_id}&seconds=180"},
  "start_work":   {"method": "POST", "url": "{platform_api}/process/definitions/{process_def_id}/start",
                   "body": {"values": {"event_id": "{event.id}", "asset_id": "{event.asset_id}", "event_type": "{event.event_type}"}}},
  "instance":     {"method": "GET",  "url": "{platform_api}/process/instances/{event.process_ref.instance_id}"},
  "worklist":     {"method": "GET",  "url": "{platform_api}/process/worklist"},
  "complete":     {"method": "POST", "url": "{platform_api}/process/workitems/{workitem_id}/complete", "body": {"values": "{draft}"}},
  "approval_draft": {"decision": "APPROVED", "approved_value": 0.8, "approver": "", "comment": ""}
};
