// S09 · 게시 앱 설정 — POST /apps 의 config 가 이 파일(window.APP_CONFIG)로 생성된다 (labplatform/apps.py)
// TODO(학생): 키 이름·주소·스키마 이름을 실제 서버와 apps.py 의 필수 바인딩에 맞춘다.
window.APP_CONFIG = {
  "hydops_api": "http://localhost:8800",
  "platform_api": "http://localhost:8800",
  "schema_name": "Hydraulic_Ops",
  "process_def": "cooling_response",
  "app_name": "hydops-ops"
};
