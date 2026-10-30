# redev-map — 재개발 노후도·소유자 지도

브이월드 연속지적도·용도지역·토지소유정보와 건축물대장을 필지(PNU) 단위로 묶어
노후도, 추정 소유자 수, 신축 비율을 지도에 띄우고, 지도에 구역을 그리면 재개발 요건 지표를 즉석에서 계산합니다.

## 구조
| 경로 | 역할 |
|---|---|
| `config.yaml` | 대상 지역(test=서초구, seoul, seongnam)과 노후 판정 기준 |
| `pipeline/fetch.py` | 원천데이터 수집 → `data/raw/{시군구}/{법정동}_*.json` (25일 캐시, 이어받기) |
| `pipeline/metrics.py` | 필지별 집계: 노후·신축·호수 / 추정 소유자 수 |
| `pipeline/build.py` | `site/data/{법정동}.geojson`, `site/data/dongs.geojson` 생성 |
| `site/index.html` | 지도 앱 (MapLibre). 구역 그리기 → 노후도·과소필지·호수밀도·소유자 수 계산 |
| `.github/workflows/pipeline.yml` | Actions에서 수집·빌드 → GitHub Pages 배포 |

## 데이터 출처
- 연속지적도 `LP_PA_CBND_BUBUN`, 용도지역 `LT_C_UQ111`, 읍면동 `LT_C_ADEMD_INFO` — 브이월드 2D 데이터 API
- 토지소유정보 `getPossessionAttr` — 브이월드 NED
- 건축물대장 표제부 `getBrTitleInfo` — 공공데이터포털 건축HUB

## 수집 구조
브이월드는 해외 IP(GitHub 서버)를 차단 → **브이월드는 집 PC에서, 건축물대장은 GitHub에서** 받음.

| 어디서 | 무엇을 | 어떻게 |
|---|---|---|
| 집 PC (윈도우) | 읍면동·연속지적도·용도지역·토지소유정보 | `collect.bat` 더블클릭 → `data/seed/`에 동별 압축 저장 → 자동 커밋·푸시 |
| GitHub Actions | 건축물대장 표제부 → 지표 계산 → 지도 배포 | `data/seed` 푸시되면 자동 실행 (매월 2일에도 실행) |

- `check.bat`: API가 되는지 1분 점검 (아무것도 올리지 않음)
- `install_auto.bat`: 매일 9시(꺼져 있었으면 켜진 직후) `auto.bat` 자동 실행 등록. 최신 코드 받기 → 기한 지난 동만 수집 → 구 단위로 바로 업로드. 로그는 `logs/auto.log`, 해제는 `install_auto.bat remove`
- `collect.bat vworld test`: 서초구만 / 기본값은 `seoul+seongnam`
- 지적도·용도지역 90일, 소유정보 30일, 건축물대장 25일 이내 받은 동은 건너뜀 → 끊겨도 다시 실행하면 이어받음
- 소유정보는 원본 행을 저장하지 않고 필지별 집계(추정 소유자 수·국공유 여부 등)만 커밋
- 처음 PC 준비: Python 3.12, Git 설치 → `git clone https://github.com/jaehyunlee1221/Redev-map` → `collect.bat` 실행하면 `.env`(브이월드 키) 입력창이 열림
- `pipeline/seed.py`: (보조) 브이월드에서 직접 받은 shp/csv 파일 변환

## 설정
Secrets: `DATA_GO_KR_KEY`(Decoding 키). 브이월드 키는 PC의 `.env`에만 둠
Settings → Pages → Source: **GitHub Actions**


## 지표 정의 (추정치)
- **노후도** = 노후 주건축물 동수 / 주건축물 동수. 철근콘크리트·철골계 30년, 그 외 20년 경과 (`config.yaml`)
  사용승인일 미상은 따로 집계하고 "미상 포함 시"도 함께 표시 (1989.1.24 이전 무허가 건축물 산입 규정 대응)
- **추정 토지등소유자** = 필지별 구분소유 단위 합(공유는 대표 1인) ~ 공유자 각각 합. 국공유 제외.
  동일인 다물건은 구분 불가 → 실제보다 많게 나옴
- **과소필지** = 지목 '대' 중 90㎡ 미만, **호수밀도** = 주건축물 동수 / ha

## 로드맵
- [ ] 서초구 실데이터 검증 (방배·서초·양재 기존 정비구역 수치와 대조)
- [ ] 정비구역 레이어 + 진행단계·예정세대수 (정비사업 정보몽땅 / 고시문)
- [ ] 접도율 (지목 '도로' 필지 + 4m 폭 판정)
- [ ] 서울 전체 → 성남시 확장, 데이터가 커지면 PMTiles 전환
