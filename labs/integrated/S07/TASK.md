# 통합반 7회 실습 — Ontology Studio에서 내 설비 조회

교재: `textbooks/통합반/I07_Ontology_Studio에서_내_설비_조회.md` §7

## 채울 파일

| 파일 | 빈칸 | 확인 방법 |
|---|---|---|
| `my_binding.json` | 스키마 이름, Asset·Event 키 속성, Asset 그래프 라벨, Event·Verification 데이터소스·테이블·컬럼, HAS_EVENT·HAS_VERIFICATION 조인 속성 | 제공 템플릿 `system/labplatform/templates/ontology_hydraulic.json` 과 같아야 하고, 모든 컬럼이 `GET /fabric/datasources/hydops_edu` 메타데이터에 있어야 한다 |
| `studio_lookup.py` | 플랫폼 주소, 스키마 이름, 발행 전 HTTP 상태 코드, 관계 조회 주소 조각, 조회 개수 필드, 센서 ID 필드 | 조회 결과를 `NOT_PUBLISHED / PUBLISHED_NO_DATA / HAS_DATA` 로 구분하고, HYD-01 센서가 로컬(:8800)과 플랫폼(:8910)에서 같은지 대조 |

## 규칙

- 테스트와 `studio_lookup.py` 는 **GET 만** 호출한다. 발행은 교재 활동 3에서 콘솔 버튼으로 한 번만 한다.
- `count` 가 0이면 note 가 없어도(그래프 관계) "발행됐지만 데이터 없음"이다.

## 실행

```bash
cd lecture/system
PYTHONPATH=. .venv/bin/python -m pytest ../labs/integrated/S07 -q          # 내 답 검사
PYTHONPATH=. .venv/bin/python ../labs/integrated/S07/studio_lookup.py      # 조회 결과 출력
```
