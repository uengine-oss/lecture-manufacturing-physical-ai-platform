# 통합반 9회 실습 — 아이나루 관제 화면과 배포

교재: `textbooks/통합반/I09_관제_화면과_배포.md` §7

제공 화면(`system/labplatform/app_templates/ops-console/index.html`)은 고치지 않는다. 화면이 어디서 데이터를 읽는지 **설정과 주소의 빈칸**만 채운다.

## 채울 파일

| 파일 | 빈칸 | 확인 방법 |
|---|---|---|
| `config.js` | `hydops_api`, `platform_api`, `schema_name`, `process_def_id` | 게시 검증(`apps.py` 의 required)이 요구하는 네 값이 모두 있고, 게시된 앱의 `config.js`(GET)와 같아야 한다 |
| `app_bindings.js` | 설비 목록 클래스, 설비→사건 관계, 사건 상세 서버, 인스턴스 ID 변수, 업무 시작 메서드·정의 ID | 치환하면 제공 화면 index.html 의 조회 주소와 글자까지 같아야 한다 |
| `same_event.py` | 화면·프로세스·조치 기록에서 event_id 를 읽는 필드, 조치 기록 없음 표시, 인스턴스 대응 필드 | 실제 사건 상세(:8800)와 인스턴스(:8910)를 GET 해 세 가지가 같은 사건을 가리키는지 확인 |

## 규칙

- 테스트는 게시·업무 시작을 하지 않는다. 게시는 활동 3에서 콘솔 Apps 화면의 **게시** 버튼으로 한다.
- 설비 목록 조회(`objects/Asset/fetch`)는 POST 지만 읽기 전용 조회다.

## 실행

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S09 -q
```
