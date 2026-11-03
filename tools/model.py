"""정비사업 성공가능성 모델 (로컬 분석용) — PD 모델처럼: 관측시점 = 구역지정, good = 단계 도달, bad = 해제
  입력: zone_features.json (pipeline.features 결과; GitHub 로그의 FEATDUMP를 풀어 저장)
  모든 구역은 같은 방식(대표 지번 + 같은 면적의 원)으로 계산한 행만 씀 → 측정 방식 차이 편향 방지
  A) 사업시행인가 도달 vs 해제   — good: 진행 목록 중 사업시행~이주 (착공 전 → 옛 건물이 남아 있어 변수 전부 사용)
  B) 관리처분인가 도달 vs 해제   — good: 관리처분~이주
  C) 완료 포함, 시간불변 변수만  — good: 사업시행 이상 전부 + 완료 추정(그 자리에 지정 뒤 100세대+ 신축 확인)
  지정 2003~2015 코호트, 5겹 교차검증 AUC·AR·KS, 로지스틱(표준화·L2) 계수, GBM 비교
  python tools/model.py zone_features.json [scores.json]"""
import sys, json
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

FULL = ['old_ratio', 'age_mean', 'bldg_per_ha', 'hh_per_ha', 'owners_per_ha', 'jiphap_ratio', 'new5_before_ref', 'small_ratio', 'dae_ratio',
        'road_ratio', 'pub_ratio', 'far_room', 'far_now', 'z1', 'z2', 'z3', 'zcom', 'lu_plan', 'lu_heritage', 'log_area', 'log_gj',
        'station_m', 'cityhall_km', 'gangnam_km', 'yeouido_km', 'apt_gu', 'price_gap', 'k_rebuild', 'k_promo']
FIXED = ['log_area', 'station_m', 'cityhall_km', 'gangnam_km', 'yeouido_km', 'apt_gu', 'apt_gu_new', 'k_rebuild', 'k_promo', 'seoul_ne', 'seoul_sw']
STAGE = {'구역지정': 0, '추진위': 1, '조합설립': 2, '건축심의': 3, '사업시행': 4, '관리처분': 5, '이주': 6, '착공': 7, '준공': 8}


def ks(y, p):
    o = np.argsort(p); y = np.asarray(y)[o]
    return float(np.max(np.abs(np.cumsum(y) / y.sum() - np.cumsum(1 - y) / (1 - y).sum())))


def load(path):
    d = pd.DataFrame(json.load(open(path, encoding='utf-8')))
    d['log_area'] = np.log(d['area_ha'].clip(lower=0.1))
    d['log_gj'] = np.log(d['gj_med'].where(d['gj_med'] > 0))
    d['si'] = d['s'].map(STAGE) if 's' in d else np.nan
    tt = d['t'].astype(str)
    d['k_rebuild'] = tt.str.contains('재건축').astype(int)
    d['k_promo'] = tt.str.contains('촉진').astype(int)
    d['seoul_ne'] = ((d.cx > 127.0) & (d.cy > 37.57)).astype(int)   # 동북권 대략
    d['seoul_sw'] = ((d.cx < 126.95) & (d.cy < 37.53)).astype(int)  # 서남권 대략
    return d


def fit(name, tr, cols):
    tr = tr.dropna(subset=['y'])
    X, y = tr[cols].astype(float), tr.y.values.astype(int)
    print(f'\n=== {name}: good {int((1 - y).sum())} vs bad(해제) {int(y.sum())}')
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    lr = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), LogisticRegression(C=0.3, max_iter=3000))
    gb = make_pipeline(SimpleImputer(strategy='median'), HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=15))
    res = {}
    for nm, m in (('logistic', lr), ('gbm', gb)):
        p = cross_val_predict(m, X, y, cv=cv, method='predict_proba')[:, 1]
        auc = roc_auc_score(y, p); res[nm] = dict(auc=round(auc, 3), ar=round(2 * auc - 1, 3), ks=round(ks(y, p), 3))
        print(f'  {nm:9s} CV AUC {auc:.3f} · AR {2 * auc - 1:.3f} · KS {ks(y, p):.3f}')
    lr.fit(X, y)
    coef = pd.Series(lr[-1].coef_[0], index=cols).sort_values()
    print('  표준화 계수 (+ = 해제 위험↑):', ', '.join(f'{k} {v:+.2f}' for k, v in coef.items() if abs(v) >= 0.1))
    print('  단변량 AUC (>0.5 = 클수록 해제)·중위 해제/good:')
    for c in cols:
        v = tr[c].astype(float); ok = v.notna()
        if ok.sum() > 30 and len(set(y[ok])) == 2:
            a = roc_auc_score(y[ok], v[ok])
            if abs(a - 0.5) >= 0.07: print(f'    {c:16s} {a:.3f}  {v[y == 1].median():.3g} / {v[y == 0].median():.3g}')
    return lr, res, coef


def main(path, out=None):
    d = load(path)
    coh = d[(d.ref >= 2003) & (d.ref <= 2015) & (d.n_bldg.fillna(0) >= 3)]
    bad = coh[(coh.kind == 'released') & ~coh.t.isin(['예정', '관리'])].assign(y=1)
    act = coh[coh.kind == 'active_c']
    done = coh[(coh.kind == 'done') & (coh.post_hh.fillna(0) >= 100)]
    print(f"코호트(지정 2003~2015): 해제 {len(bad)} · 진행 {len(act)} (단계 {act.s.value_counts().to_dict()}) · 완료추정 {len(coh[coh.kind == 'done'])} 중 신축 확인 {len(done)}")
    A = pd.concat([bad, act[act.si.between(4, 6)].assign(y=0)])
    B = pd.concat([bad, act[act.si.between(5, 6)].assign(y=0)])
    C = pd.concat([bad, act[act.si >= 4].assign(y=0), done.assign(y=0)])
    res = {}
    mA, res['A'], cA = fit('A) 사업시행 도달 vs 해제 (전체 변수)', A, FULL)
    _, res['B'], _ = fit('B) 관리처분 도달 vs 해제 (전체 변수)', B, FULL)
    _, res['C'], _ = fit('C) 사업시행 이상·완료 vs 해제 (시간불변 변수만)', C, FIXED)
    allact = d[d.kind == 'active_c'].copy()
    allact['risk'] = mA.predict_proba(allact[FULL].astype(float))[:, 1]
    print('\n진행 구역 해제위험(모델 A) 단계별 중위:', allact.groupby('s').risk.median().round(3).to_dict())
    if out:
        json.dump(dict(metrics=res, coef=cA.round(4).to_dict(), scores={int(r.id): round(float(r.risk), 4) for r in allact.itertuples()}),
                  open(out, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    main(*sys.argv[1:])
