// S09 · 제조 운영 앱 바인딩 표 — app_templates/ops-console/index.html 의 fetch 호출을 한 표로 옮긴 것.
// {이름} 은 window.APP_CONFIG 의 키, {asset_id}·{event.*}·{workitem_id}·{draft}·{form.*} 는 화면에서 고른 값이다.
window.APP_BINDING = {
  "assets":       {"method": "POST", "url": "{platform_api}/studio/schemas/{schema_name}/objects/Asset/fetch", "body": {"limit": 10}},
  "events":       {"method": "GET",  "url": "{platform_api}/studio/schemas/{schema_name}/objects/Asset/{asset_id}/related/HAS_EVENT"},
  "event_detail": {"method": "GET",  "url": "{hydops_api}/api/events/{event_id}"},
  "series":       {"method": "GET",  "url": "{hydops_api}/api/series?asset_id={asset_id}&seconds=180"},
  "start_work":   {"method": "POST", "url": "{platform_api}/process/definitions/{process_def_id}/start",
                   "body": {"values": {"event_id": "{event.event_id}", "asset_id": "{event.asset_id}", "run_id": "{event.run_id}", "event_type": "{event.event_type}"}}},
  "instance":     {"method": "GET",  "url": "{platform_api}/process/instances/{event.process_ref.instance_id}"},
  "worklist":     {"method": "GET",  "url": "{platform_api}/process/worklist"},
  "complete":     {"method": "POST", "url": "{platform_api}/process/workitems/{workitem_id}/complete", "body": {"values": "{draft}"}},
  "approval_draft": {"decision": "APPROVED", "approved_value": "{form.approved_value}", "approver": "", "comment": ""}
};
