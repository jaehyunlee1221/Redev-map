"""정비사업 해제위험 등급 (지도 팝업용) — LightGBM + SHAP 사유코드
  학습: 지정 2003~2015 코호트, 건축심의~사업시행 단계(good: 이주·철거 전이라 옛 건물이 그대로 남아 있음) vs 해제(bad)
        (관리처분 이후는 이주·멸실로 건물 수·근생 비율이 줄어 '도달 → 변수 변화' 누수가 생김 → good에서 제외) — 모든 구역 같은 방식(대표 지번 + 같은 면적의 원)
  점수: 아직 사업시행 전(구역지정~건축심의) 진행 구역만 → 상대 5등급 + 위험을 올리고 내린 요인 (LightGBM pred_contrib = TreeSHAP)
  python -m pipeline.score  → site/data/zscore.json"""
import json
import numpy as np, pandas as pd
from .common import RAW, OUT

FULL = ['old_ratio', 'age_mean', 'bldg_per_ha', 'hh_per_ha', 'units_ref_per_ha', 'jiphap_ratio', 'new5_before_ref', 'small_ratio', 'dae_ratio',
        'road_ratio', 'pub_ratio', 'far_room', 'far_now', 'z1', 'z2', 'z3', 'zcom', 'lu_heritage', 'log_area', 'log_gj',
        'station_m', 'cityhall_km', 'gangnam_km', 'yeouido_km', 'apt_gu', 'price_gap', 'k_rebuild', 'k_dosi',
        'lt_apt', 'lt_house', 'lt_nbhd', 'lt_comm', 'has_relig', 'has_school',
        'feas', 'apt_dong_new', 'apt_dong_rel', 'apt_gu_rel']
# 현재 소유정보(소유자 수·법인·국공유 비율)는 학습에서 뺌: 사업이 진행되면 조합·신탁사(법인)가 땅을 사들여 바뀜 (관리처분 구역 법인 비율 26%, 착공 50% vs 조합설립 5%)
# → 지정 당시 건물로 추정한 소유 단위(units_ref_per_ha)를 대신 씀. 소유자 유형은 구역 분석 화면에서만 보여줌
FIXED = ['log_area', 'station_m', 'cityhall_km', 'gangnam_km', 'yeouido_km', 'apt_gu', 'apt_gu_new', 'k_rebuild', 'k_dosi', 'seoul_ne', 'seoul_sw']
STAGE = {'구역지정': 0, '추진위': 1, '조합설립': 2, '건축심의': 3, '사업시행': 4, '관리처분': 5, '이주': 6, '착공': 7, '준공': 8}
pct = lambda v: f'{v:.0%}'
LABEL = {  # 변수 → (이름, 값 표시)
    'old_ratio': ('노후 건물 비율', pct), 'age_mean': ('평균 건물 연령', lambda v: f'{v:.0f}년'), 'bldg_per_ha': ('건물 밀도', lambda v: f'{v:.0f}동/ha'),
    'hh_per_ha': ('세대 밀도', lambda v: f'{v:.0f}세대/ha'), 'owners_per_ha': ('소유자 밀도', lambda v: f'{v:.0f}명/ha'),
    'jiphap_ratio': ('집합건물(아파트·빌라) 비율', pct), 'new5_before_ref': ('지정 전 5년 내 신축 비율', pct), 'small_ratio': ('과소필지 비율', pct),
    'dae_ratio': ('대지 비율', pct), 'road_ratio': ('도로 비율', pct), 'pub_ratio': ('국공유지 비율', pct),
    'far_room': ('용적률 여유', lambda v: f'{v:.0f}%p'), 'far_now': ('현재 용적률', lambda v: f'{v:.0f}%'),
    'z1': ('1종주거 비율', pct), 'z2': ('2종주거 비율', pct), 'z3': ('3종주거 비율', pct), 'zcom': ('상업·준주거 비율', pct),
    'lu_heritage': ('문화재·경관 규제 비율', pct), 'log_area': ('구역 면적', lambda v: f'{np.exp(v):.1f}ha'),
    'log_gj': ('공시지가 중위', lambda v: f'{np.exp(v) / 1e4:,.0f}만원/㎡'), 'station_m': ('지하철역 거리', lambda v: f'{v:,.0f}m'),
    'cityhall_km': ('시청 거리', lambda v: f'{v:.1f}km'), 'gangnam_km': ('강남역 거리', lambda v: f'{v:.1f}km'), 'yeouido_km': ('여의도 거리', lambda v: f'{v:.1f}km'),
    'apt_gu': ('구 아파트 시세(지정 당시)', lambda v: f'{v:,.0f}만원/㎡'), 'price_gap': ('신축 시세/공시지가', lambda v: f'{v:.1f}배'),
    'lt_apt': ('공동주택 부지 비율', pct), 'lt_house': ('단독주택 부지 비율', pct), 'lt_nbhd': ('근린생활시설 부지 비율', pct),
    'lt_comm': ('상업·업무시설 부지 비율', pct), 'lt_vacant': ('나대지 비율', pct), 'has_relig': ('종교시설', lambda v: '있음' if v else '없음'),
    'has_school': ('학교', lambda v: '있음' if v else '없음'), 'ow_ind': ('개인 소유 면적 비율', pct), 'ow_corp': ('법인 소유 면적 비율', pct),
    'ow_pub': ('국공유지 면적 비율', pct), 'ow_clan': ('종중·종교단체 소유 비율', pct),
    'units_ref_per_ha': ('소유 단위 밀도(지정 당시 추정)', lambda v: f'{v:.0f}/ha'),
    'feas': ('추정 사업성(비례율 근사)', lambda v: f'{v * 100:.0f}%'), 'gfa_per_owner': ('소유자당 지을 수 있는 연면적', lambda v: f'{v:.0f}㎡'),
    'apt_dong_new': ('동 신축 아파트 시세(지정 당시)', lambda v: f'{v:,.0f}만원/㎡'),
    'apt_dong_rel': ('동 신축 시세 (그해 서울 중간=100)', lambda v: f'{v * 100:.0f}'), 'apt_gu_rel': ('구 신축 시세 (그해 서울 중간=100)', lambda v: f'{v * 100:.0f}'),
    'k_rebuild': ('사업 유형', lambda v: '재건축' if v else '재개발'), 'k_dosi': ('도시정비형', lambda v: '예' if v else '아니오'),
}
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=7, max_depth=3, min_child_samples=15, subsample=0.8, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=1.0, random_state=0, verbose=-1)


def load(path):
    d = pd.DataFrame(json.load(open(path, encoding='utf-8')))
    d['log_area'] = np.log(d['area_ha'].clip(lower=0.1))
    d['log_gj'] = np.log(d['gj_med'].where(d['gj_med'] > 0))
    d['si'] = d['s'].map(STAGE) if 's' in d else np.nan
    if 'psi' in d: d.loc[d.kind == 'plus_c', 'si'] = d.loc[d.kind == 'plus_c', 'psi']  # 서울플랜+ 사업은 단계 이름이 달라 redev.plus_si 값 (후보·기획 -1)
    tt = d['ty'].astype(str) if 'ty' in d else d['t'].astype(str)  # features.ty: 출처와 무관하게 같은 기준의 유형
    d['k_rebuild'] = (tt == '재건축').astype(int)
    d['k_dosi'] = (tt == '도시정비형').astype(int)
    for k, c in (('has_relig', 'n_relig'), ('has_school', 'n_school')): d[k] = (d[c].fillna(0) > 0).astype(int) if c in d else np.nan
    d['seoul_ne'] = ((d.cx > 127.0) & (d.cy > 37.57)).astype(int)   # 동북권 대략
    d['seoul_sw'] = ((d.cx < 126.95) & (d.cy < 37.53)).astype(int)  # 서남권 대략
    return d


def usable(d, cols):
    """값이 있는 변수만 (예: 소유자 유형은 PC에서 소유정보 v3를 다시 받기 전엔 비어 있음)"""
    return [c for c in cols if c in d and d[c].notna().mean() > 0.5]


def samples(d):
    """(코호트, 해제, 진행, 완료확인) — 지정 2003~2015"""
    coh = d[(d.ref >= 2003) & (d.ref <= 2015) & (d.n_bldg.fillna(0) >= 3)]
    bad = coh[(coh.kind == 'released') & ~coh.t.isin(['예정', '관리'])].assign(y=1)
    act = coh[coh.kind == 'active_c']
    done = coh[(coh.kind == 'done') & (coh.post_hh.fillna(0) >= 100)]
    return coh, bad, act, done


def main():
    from lightgbm import LGBMClassifier
    from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
    d = load(RAW / 'zone_features.json')
    _, bad, act, _ = samples(d)
    tr = pd.concat([bad, act[act.si.between(3, 4)].assign(y=0)])  # 건축심의~사업시행 (철거 전)
    cols = usable(tr, FULL)
    X, y = tr[cols].astype(float), tr.y.values.astype(int)
    if y.sum() < 30 or (1 - y).sum() < 20: return print(f'표본 부족 (해제 {y.sum()}, 사업시행 도달 {(1 - y).sum()}) → 등급 생략', flush=True)
    cv = cross_val_score(LGBMClassifier(**PARAMS), X, y, cv=RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=0), scoring='roc_auc')
    m = LGBMClassifier(**PARAMS).fit(X, y)
    a = d[d.kind.isin(['active_c', 'plus_c']) & (d.si.fillna(-1) <= 2)].copy()  # 아직 사업시행 전(구역지정~조합설립) + 신통기획 등 지정 전 후보
    a = a.drop_duplicates('id', keep='first')
    Xa = a[cols].astype(float)
    a['risk'] = m.predict_proba(Xa)[:, 1]
    sh = m.predict(Xa, pred_contrib=True)[:, :-1]  # TreeSHAP (log-odds 기여, 마지막 열은 기준값)
    a['pr'] = a.risk.rank(pct=True)
    out = {}
    for (_, r), s in zip(a.iterrows(), sh):
        o = np.argsort(-s)
        why = lambda idx: [f'{LABEL[cols[j]][0]} {LABEL[cols[j]][1](r[cols[j]])}' for j in idx if not pd.isna(r[cols[j]])][:3]
        out[str(int(r.id))] = dict(g=min(int(r.pr * 5) + 1, 5), p=round(float(r.pr), 3),
                                   up=why([j for j in o if s[j] > 0.05]), dn=why([j for j in o[::-1] if s[j] < -0.05]))
    meta = dict(model='LightGBM', target='사업시행 단계 도달 vs 해제 (지정 2003~2015)', n_bad=int(y.sum()), n_good=int((1 - y).sum()),
                auc=round(float(cv.mean()), 3), auc_sd=round(float(cv.std()), 3), n_scored=len(out))
    own = {str(int(r.id)): [int(r.owners or 0), int(r.owners_hi or 0)] for r in d[d.kind == 'active'].itertuples() if r.owners}  # 경계 안 추정 토지등소유자 (팝업: 분양분과 비교)
    (OUT / 'zscore.json').write_text(json.dumps(dict(meta=meta, z=out, own=own), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"해제위험 등급 {len(out)}개 구역 · 학습 해제 {meta['n_bad']} vs 사업시행 도달 {meta['n_good']} · CV AUC {meta['auc']} ± {meta['auc_sd']}", flush=True)
    imp = pd.Series(np.abs(m.predict(X, pred_contrib=True)[:, :-1]).mean(0), index=cols).sort_values(ascending=False)
    print('  SHAP 평균 영향 상위:', ', '.join(f'{LABEL[k][0]} {v:.2f}' for k, v in imp.head(8).items()), flush=True)


if __name__ == '__main__':
    main()
