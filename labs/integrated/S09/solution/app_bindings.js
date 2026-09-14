// 제조 운영 앱(ops-console)의 데이터 연결 — system/labplatform/app_templates/ops-console/index.html 의 methods 에서 뽑았다.
// ${...} 는 config.js 값(hydops_api, platform_api, schema_name, process_def_id)과 화면에서 고른 값(asset_id, event_id, instance_id)으로 채워진다.
window.APP_BINDINGS = {
  assetList:       { method: 'POST', url: '${platform_api}/studio/schemas/${schema_name}/objects/Asset/fetch' },
  assetEvents:     { method: 'GET',  url: '${platform_api}/studio/schemas/${schema_name}/objects/Asset/${asset_id}/related/HAS_EVENT' },
  eventDetail:     { method: 'GET',  url: '${hydops_api}/api/events/${event_id}' },
  processInstance: { method: 'GET',  url: '${platform_api}/process/instances/${instance_id}' },
  worklist:        { method: 'GET',  url: '${platform_api}/process/worklist' },
  openWork:        { method: 'POST', url: '${platform_api}/process/definitions/${process_def_id}/start' },
  series:          { method: 'GET',  url: '${hydops_api}/api/series?asset_id=${asset_id}&seconds=180' },
};
