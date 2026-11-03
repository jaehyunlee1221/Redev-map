"""정비사업 해제 위험 모델 (로컬 분석용)
  입력: zone_features.json (pipeline.features 결과; GitHub 로그의 FEATDUMP를 풀어 저장)
  표본: 같은 시기(지정 2003~2015)에 지정된 구역 중 → 해제(1) vs 지금도 진행 중·완료(0)
        진행 구역은 해제 구역과 같은 방식(대표 지번 + 같은 면적의 원)으로 계산한 'active_c'를 씀 → 측정 방식 차이로 인한 편향 방지
  모형: 로지스틱(표준화, L2) — 5겹 교차검증 AUC·AR·KS / 계수 방향 / 진행 구역 전체 점수
  python tools/model.py zone_features.json [out.json]"""
import sys, json, math
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score

X_COLS = ['old_ratio', 'age_mean', 'bldg_per_ha', 'hh_per_ha', 'owners_per_ha', 'jiphap_ratio', 'new5_before_ref', 'small_ratio', 'dae_ratio',
          'road_ratio', 'pub_ratio', 'far_room', 'far_now', 'z1', 'z2', 'z3', 'zcom', 'lu_plan', 'lu_heritage', 'log_area', 'log_gj',
          'station_m', 'cityhall_km', 'gangnam_km', 'yeouido_km', 'apt_gu', 'price_gap']


def ks(y, p):
    o = np.argsort(p); y = np.asarray(y)[o]
    c1, c0 = np.cumsum(y) / y.sum(), np.cumsum(1 - y) / (1 - y).sum()
    return float(np.max(np.abs(c1 - c0)))


def load(path):
    d = pd.DataFrame(json.load(open(path, encoding='utf-8')))
    d['log_area'] = np.log(d['area_ha'].clip(lower=0.1))
    d['log_gj'] = np.log(d['gj_med'].where(d['gj_med'] > 0))
    d['zd_y'] = pd.to_numeric(d['zd'].astype(str).str[:4], errors='coerce')
    return d


def main(path, out=None):
    d = load(path)
    rel = d[(d.kind == 'released') & ~d.t.isin(['예정', '관리'])].copy()   # 정비예정·주거환경관리는 성격이 달라 제외
    act = d[(d.kind == 'active_c')].copy()
    print(f'해제 {len(rel)} · 진행(원 근사) {len(act)}')
    coh = lambda x: x[(x.ref >= 2003) & (x.ref <= 2015)]
    tr = pd.concat([coh(rel).assign(y=1), coh(act).assign(y=0)])
    tr = tr[tr.n_bldg >= 5]
    print(f'학습 표본 (지정 2003~2015): 해제 {int(tr.y.sum())} vs 진행·완료 {int((1 - tr.y).sum())}')
    X, y = tr[X_COLS].astype(float), tr.y.values
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    lr = make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), LogisticRegression(C=0.3, max_iter=2000))
    gb = make_pipeline(SimpleImputer(strategy='median'), HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200, min_samples_leaf=15))
    res = {}
    for nm, m in (('logistic', lr), ('gbm', gb)):
        p = cross_val_predict(m, X, y, cv=cv, method='predict_proba')[:, 1]
        auc = roc_auc_score(y, p); res[nm] = dict(auc=auc, ar=2 * auc - 1, ks=ks(y, p))
        print(f'{nm:9s} CV AUC {auc:.3f} · AR {2 * auc - 1:.3f} · KS {ks(y, p):.3f}')
    lr.fit(X, y)
    coef = pd.Series(lr[-1].coef_[0], index=X_COLS).sort_values()
    print('\n표준화 계수 (+ = 해제 위험↑):'); print(coef.round(3).to_string())
    print('\n변수별 단변량 AUC (해제 쪽이 클수록 >0.5):')
    for c in X_COLS:
        v = tr[c].astype(float)
        if v.notna().sum() > 30: print(f'  {c:16s} {roc_auc_score(y[v.notna()], v[v.notna()]):.3f}  해제 중위 {v[y == 1].median():.3g} / 진행 {v[y == 0].median():.3g}')
    act['risk'] = lr.predict_proba(act[X_COLS].astype(float))[:, 1]
    if out:
        json.dump(dict(metrics=res, coef=coef.round(4).to_dict(), n=dict(rel=int(y.sum()), act=int((1 - y).sum())),
                       scores={int(r.id): round(float(r.risk), 4) for r in act.itertuples()}), open(out, 'w'), ensure_ascii=False)
    return act


if __name__ == '__main__':
    main(*sys.argv[1:])
