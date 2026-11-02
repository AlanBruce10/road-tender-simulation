"""Define Q scenarios and calibrate conditional duration models for Script 06.

Uses Script 03's eligible cohort only. No imputation or additional exclusions.
Primary scenarios: Q<P25, P25<=Q<=P75, Q>P75. Tertiles: sensitivity only.
Nested three-by-three entity/project-component folds compare M0--M4.
Retrospective published schedules; v3 requires explicit downstream adaptation.
Dependencies: pandas numpy scipy openpyxl. No API or SEACE connection required.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import unicodedata
import sys
from datetime import datetime, timezone
import tempfile
import traceback
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import optimize, stats

VERSION='3.0-nested-covariates'
Q='queries_observations_count'
TOTAL='query_close_to_award_calendar_days'
PHASES=['absolution_calendar_days','integration_calendar_days','post_integration_calendar_days']
PHASE_LABELS=['query_close_to_absolution_end','absolution_end_to_integration_end','integration_end_to_award_end']
BOUNDARIES=['schedule_query_end_date','schedule_absolution_end_date','schedule_integration_end_date','schedule_award_end_date']
DATE_NATURE='published_schedule_not_verified_actual_events'
SEED=20251025
MIN_POSITIVE=30  # Stability safeguard, not a scientific universal or exclusion rule.
STRUCTURES={'no_Q':(0,2),'Q_location':(0,1,2),'Q_location_and_shape':(0,1,2,3)}
LOG=[]
ENTITY='source00_entity_code'
FAMILIES=[('COMAS_RESTART','811044','848861'),('OLMOS_ITEMS_RESTART','995451','1058629')]


def log(message):
    print(message,flush=True);LOG.append(str(message))


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def boolean(series):
    x=series.astype(str).str.strip().str.lower()
    if not x.isin(['true','false','1','0']).all():raise ValueError('Invalid or missing eligible flag')
    return x.isin(['true','1'])


def validate(df):
    required={'procedure_code',Q,TOTAL,*PHASES,*BOUNDARIES,ENTITY,'duration_unit','modeled_origin','source02_count_status','source02_queries_observations_count','source00_notice_date','eligible_common_model','date_nature'}
    if required-set(df):raise ValueError(f'Missing Script 03 columns: {sorted(required-set(df))}')
    df['procedure_code']=df.procedure_code.astype(str).str.strip().str.replace(r'\.0$','',regex=True)
    if not df.procedure_code.str.fullmatch(r'\d+').all() or df.procedure_code.duplicated().any():
        raise ValueError('Missing/invalid/duplicate procedure codes')
    if not boolean(df.eligible_common_model).all() or not df.date_nature.eq(DATE_NATURE).all():
        raise ValueError('Use the eligible published-schedule dataset from Script 03')
    for col in [Q,TOTAL]+PHASES:
        df[col]=pd.to_numeric(df[col],errors='coerce')
        if not np.isfinite(df[col]).all() or (df[col]<0).any():raise ValueError(f'Invalid values: {col}')
    if df[ENTITY].isna().any() or df[ENTITY].astype(str).str.strip().eq('').any(): raise ValueError('Entity identifiers are required for clustered analysis')
    if not df.duration_unit.eq('calendar_days').all() or not df.modeled_origin.eq('query_formulation_start').all(): raise ValueError('Unexpected upstream duration unit/origin')
    if not df.source02_count_status.eq('OK').all() or not np.array_equal(df[Q],pd.to_numeric(df.source02_queries_observations_count,errors='coerce')): raise ValueError('Q differs from verified Script 02 source')
    for col in [c for c in df if c.startswith('qc_')]:
        if not boolean(df[col]).all(): raise ValueError(f'Upstream quality control failed: {col}')
    if df[Q].mod(1).ne(0).any():raise ValueError('Q must be an integer count')
    if df[TOTAL].le(0).any():raise ValueError('The current positive-total model requires T>0; no records silently discarded')
    if not np.allclose(df[PHASES].sum(axis=1),df[TOTAL],rtol=0,atol=0):raise ValueError('Phase sum differs from post-query-close total')
    for col in BOUNDARIES+['source00_notice_date']:
        if df[col].dropna().map(lambda x:isinstance(x,(int,float,np.number))).any(): raise ValueError(f'Numeric dates require explicit upstream resolution: {col}')
        df[col]=pd.to_datetime(df[col],errors='coerce').dt.normalize()
        if df[col].isna().any():raise ValueError(f'Missing/invalid date: {col}')
    for phase,start,end in zip(PHASES,BOUNDARIES,BOUNDARIES[1:]):
        if not np.array_equal((df[end]-df[start]).dt.days.to_numpy(),df[phase].to_numpy()):
            raise ValueError(f'Phase/date mismatch: {phase}')
    return df


def classify(q,cuts):
    # Approved hypothesis: strictly below P25 and strictly above P75.
    # Values exactly equal to either boundary belong to the medium group.
    return np.where(q<cuts[0],'low',np.where(q>cuts[1],'high','medium'))


def classify_tertiles(q,cuts):
    # Previous scheme retained only for sensitivity; its original ties are preserved.
    return np.where(q<=cuts[0],'low',np.where(q<=cuts[1],'medium','high'))


def distribution(model,z):
    a,b,c,d=model['coefficients_abcd']
    location=np.exp(a+b*z)
    shape=np.exp(c+d*z)
    if model['family']=='lognormal':return stats.lognorm(s=shape,scale=location)
    if model['family']=='weibull':return stats.weibull_min(c=shape,scale=location)
    raise ValueError('Not a parametric marginal')


def fit_candidates(y,z,outcome):
    rows=[];models=[]
    for family in ['lognormal','weibull']:
        if family=='lognormal':
            initial=np.array([np.log(y).mean(),0,np.log(max(np.log(y).std(ddof=0),.05)),0.])
        else:
            shape,_,scale=stats.weibull_min.fit(y,floc=0)
            initial=np.array([np.log(scale),0,np.log(shape),0.])
        for structure,indices in STRUCTURES.items():
            indices=list(indices)
            bounds_all=[(-12,20),(-5,5),(-6,4),(-3,3)]
            def objective(theta):
                beta=np.zeros(4);beta[indices]=theta
                a,b,c,d=beta
                loc=np.exp(a+b*z);shape=np.exp(c+d*z)
                with np.errstate(over='ignore',invalid='ignore',divide='ignore'):
                    density=(stats.lognorm.logpdf(y,s=shape,scale=loc) if family=='lognormal'
                             else stats.weibull_min.logpdf(y,c=shape,scale=loc))
                return -float(density.sum()) if np.isfinite(density).all() else 1e100
            slope,intercept=np.polyfit(z,np.log(y),1) if np.std(z)>0 else (0.,np.log(y).mean())
            alternative=initial.copy(); alternative[0]=intercept; alternative[1]=slope
            starts=[initial[indices],alternative[indices]]
            results=[optimize.minimize(objective,np.clip(start,[bounds_all[i][0]+1e-3 for i in indices],[bounds_all[i][1]-1e-3 for i in indices]),method='L-BFGS-B',
                       bounds=[bounds_all[i] for i in indices],options={'maxiter':2000,'ftol':1e-11}) for start in starts]
            interior=lambda res: res.success and np.isfinite(res.fun) and res.fun<1e90 and all(abs(v-lo)>=1e-5 and abs(v-hi)>=1e-5 for v,(lo,hi) in zip(res.x,[bounds_all[i] for i in indices]))
            result=min([res for res in results if interior(res)] or results,key=lambda res:res.fun)
            beta=np.zeros(4);beta[indices]=result.x
            ll=-objective(result.x);k=len(indices)
            hit_bound=any(abs(v-lo)<1e-5 or abs(v-hi)<1e-5 for v,(lo,hi) in zip(result.x,[bounds_all[i] for i in indices]))
            accepted=bool(result.success and np.isfinite(ll) and ll>-1e90 and not hit_bound)
            row={'outcome':outcome,'family':family,'structure':structure,'positive_n':len(y),
                 'converged':bool(result.success),'boundary_solution':hit_bound,'accepted':accepted,
                 'log_likelihood':ll,'parameters':k,'AIC':2*k-2*ll,'BIC':np.log(len(y))*k-2*ll,
                 'optimizer_message':str(result.message),'deterministic_starts':len(starts)}
            rows.append(row)
            models.append({'family':family,'structure':structure,'coefficients_abcd':beta.tolist(),
                           'positive_BIC':float(row['BIC']),'positive_AIC':float(row['AIC']),
                           'accepted':accepted,'candidate_index':len(rows)-1})
    accepted=[m for m in models if m['accepted']]
    if not accepted:raise RuntimeError(f'No converged interior candidate for {outcome}; inspect model specification')
    selected=min(accepted,key=lambda m:m['positive_BIC']).copy()
    selected['kind']='parametric_positive_with_zero_mass'
    for i,row in enumerate(rows):row['selected']=i==selected['candidate_index']
    # A no-Q benchmark is always saved, even when the conditional model is selected.
    baseline=min((m for m in accepted if m['structure']=='no_Q'),key=lambda m:m['positive_BIC'],default=None)
    if baseline is None:raise RuntimeError(f'No valid no-Q benchmark for {outcome}')
    return selected,baseline.copy(),rows


def fit_marginal(values,z,outcome):
    positive=values>0;npositive=int(positive.sum());pzero=float((~positive).mean())
    if npositive==0:
        model={'kind':'constant','value':0.0,'positive_n':0,'p_zero':1.0}
        return model,model.copy(),[]
    if npositive<MIN_POSITIVE or np.unique(values[positive]).size<3:
        # Do not invent a regression from a handful of positive integration delays.
        model={'kind':'empirical_zero_positive_mixture','positive_values':values[positive].tolist(),
               'positive_n':npositive,'p_zero':pzero,
               'limitation':'Sparse/constant positive sample; Q dependence and tails not estimated; empirical support only'}
        return model,model.copy(),[]
    selected,baseline,rows=fit_candidates(values[positive],z[positive],outcome)
    for model in (selected,baseline):model.update(kind='parametric_positive_with_zero_mass',p_zero=pzero,positive_n=npositive)
    return selected,baseline,rows


def randomized_pit(values,z,model,rng):
    if model['kind']=='constant':return rng.uniform(1e-6,1-1e-6,len(values))
    pzero=model['p_zero'];u=np.empty(len(values));zero=values==0
    u[zero]=rng.uniform(size=zero.sum())*pzero
    if model['kind']=='empirical_zero_positive_mixture':
        support=np.asarray(model['positive_values'])
        for i in np.flatnonzero(~zero):
            lower=(support<values[i]).mean();upper=(support<=values[i]).mean()
            u[i]=pzero+(1-pzero)*rng.uniform(lower,upper)
    else:
        u[~zero]=pzero+(1-pzero)*distribution(model,z[~zero]).cdf(values[~zero])
    return np.clip(u,1e-6,1-1e-6)


def fit_dependence(train,z,models,seed=SEED):
    # Sparse/constant phases are explicitly independent in the working copula.
    active=[i for i,p in enumerate(PHASES) if models[p]['kind']=='parametric_positive_with_zero_mass']
    corr=np.eye(len(PHASES));rng=np.random.default_rng(seed)
    if len(active)>1:
        latent=np.column_stack([stats.norm.ppf(randomized_pit(train[p].to_numpy(float),z,models[p],rng)) for i,p in enumerate(PHASES) if i in active])
        active_corr=np.corrcoef(latent,rowvar=False)
        if not np.isfinite(active_corr).all():raise ValueError('Invalid fitted residual dependence')
        corr[np.ix_(active,active)]=active_corr
    # Numerical positive-definiteness correction only; no fitted relation forced positive.
    eig,vec=np.linalg.eigh(corr);corr=(vec*np.maximum(eig,1e-8))@vec.T
    sd=np.sqrt(np.diag(corr));corr=corr/np.outer(sd,sd)
    return {'kind':'gaussian_copula','phase_order':PHASES,'latent_correlation':corr.tolist(),
            'active_parametric_phases':[PHASES[i] for i in active],
            'assumptions':'Residual Gaussian copula constant across Q; sparse/constant phases independent; dependence is observational, not a queue/resource mechanism',
            'seed_for_zero_mass_PIT':seed}


def save_workbook(path,sheets):
    temp=path.with_suffix('.tmp.xlsx')
    with pd.ExcelWriter(temp,engine='openpyxl') as writer:
        for name,frame in sheets.items():
            frame.to_excel(writer,sheet_name=name,index=False)
            ws=writer.sheets[name];ws.freeze_panes='B2'
            if len(frame.columns):ws.auto_filter.ref=ws.dimensions
    try:temp.replace(path)
    except PermissionError as exc:raise PermissionError(f'Close {path.name} in Excel and rerun') from exc


def normalized(value):
    if pd.isna(value):return ''
    return re.sub(r'\s+',' ',''.join(c for c in unicodedata.normalize('NFKD',str(value).lower()) if not unicodedata.combining(c))).strip()


def project_group(row):
    description=normalized(row.get('source00_procedure_description',''))
    # Repeated calls for an identifiable project remain together. This is not
    # fuzzy project linkage; unresolved textual variants can remain separate.
    matches=set(re.findall(r'\bcui\b[^\d]{0,25}(\d{6,9})\b',description))
    if len(matches)==1:return 'CUI_'+next(iter(matches)),'explicit_CUI'
    entity=normalized(row.get('source00_entity_code',row.get('source00_entity_name','')))
    if description:
        text=re.sub(r'[^a-z0-9]','',entity+' '+description)
        return 'DESC_'+hashlib.sha256(text.encode()).hexdigest()[:24],'exact_entity_description'
    return 'CODE_'+row['procedure_code'],'procedure_code_fallback'


def assign_folds(data,nfolds=5,seed=SEED):
    """Keep connected entity/project components together; never use outcomes.

    Existing project columns are preserved. The additive dependency-group column
    explicitly identifies the stronger split used by the corrected CV artifacts.
    """
    result=data.copy()
    grouping=[project_group(row) for row in result.to_dict('records')]
    result['cv_project_group']=[v[0] for v in grouping]
    result['cv_group_basis']=[v[1] for v in grouping]
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x:
            parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b: parent[max(a,b)]=min(a,b)
    for row in result.to_dict('records'):
        union('ENTITY_'+str(row[ENTITY]),'PROJECT_'+row['cv_project_group'])
    indexed=result.set_index('procedure_code')
    for _,a,b in FAMILIES:
        if a in indexed.index and b in indexed.index:
            union('ENTITY_'+str(indexed.loc[a,ENTITY]),'ENTITY_'+str(indexed.loc[b,ENTITY]))
    result['cv_dependency_group']=['DEP_'+hashlib.sha256(find('ENTITY_'+str(v)).encode()).hexdigest()[:24] for v in result[ENTITY]]
    sizes=result.cv_dependency_group.value_counts().sort_index()
    if len(sizes)<nfolds: raise ValueError('Too few independent entity/project components for validation folds')
    rng=np.random.default_rng(seed)
    ranked=pd.DataFrame({'group':sizes.index,'size':sizes.values,'tie':rng.random(len(sizes))})
    ranked=ranked.sort_values(['size','tie'],ascending=[False,True],kind='stable')
    totals=np.zeros(nfolds,dtype=int); mapping={}
    for row in ranked.itertuples(index=False):
        options=np.flatnonzero(totals==totals.min()); fold=int(rng.choice(options))
        mapping[row.group]=fold+1; totals[fold]+=row.size
    result['cv_fold']=result.cv_dependency_group.map(mapping).astype(int)
    for group in ['cv_project_group','cv_dependency_group',ENTITY]:
        if result.groupby(group).cv_fold.nunique().max()!=1: raise RuntimeError(f'{group} crossed validation folds')
    return result


def scenario_cuts(training):
    cuts=training[Q].quantile([.25,.75],interpolation='linear').to_numpy(float).tolist()
    if cuts[0]>=cuts[1]:raise ValueError('P25/P75 coincide; three distinct scenarios cannot be defined without changing the approved rule')
    labels=classify(training[Q].to_numpy(),cuts)
    if set(labels)!={'low','medium','high'}:
        raise ValueError('An approved-rule scenario is empty in training; equal-Q ties will not be broken arbitrarily')
    return cuts


def tertile_cuts(training):
    ordered=np.sort(training[Q].to_numpy(int))
    cuts=[int(ordered[int(np.ceil(len(ordered)*p))-1]) for p in (1/3,2/3)]
    if cuts[0]>=cuts[1]:
        return None  # A collapsed sensitivity scheme does not invalidate the primary one.
    if set(classify_tertiles(training[Q].to_numpy(),cuts))!={'low','medium','high'}: return None
    return cuts


def calibrate(training,fit_id,seed=SEED,parameter_uncertainty=False):
    """Only training data enter cutpoints, transforms, marginal fits and copula."""
    if len(training)<100:raise ValueError(f'{fit_id}: insufficient training cases')
    cuts=scenario_cuts(training)
    transform={'kind':'standardized_log1p_Q','mean':float(np.log1p(training[Q]).mean()),
               'std_population':float(np.log1p(training[Q]).std(ddof=0))}
    if transform['std_population']<=0:raise ValueError('Constant Q in training set')
    z=(np.log1p(training[Q].to_numpy(float))-transform['mean'])/transform['std_population']
    models={};baselines={};candidates=[]
    for outcome in [TOTAL]+PHASES:
        model,baseline,rows=fit_marginal(training[outcome].to_numpy(float),z,outcome)
        models[outcome]=model;baselines[outcome]=baseline
        for row in rows:candidates.append({'fit_id':fit_id,**row})
    bundle={'fit_id':fit_id,'training_n':len(training),
            'training_procedure_codes':sorted(training.procedure_code.tolist()),
            'Q_transform':transform,'training_Q_range':[int(training[Q].min()),int(training[Q].max())],
            'scenarios':{'method':'training_Q_P25_P75_linear_interpolation_strict_extremes','cuts':cuts,
                         'rules':{'low':'Q < P25','medium':'P25 <= Q <= P75','high':'Q > P75'},
                         'meaning':'Relative proxy-volume categories, not universal information-asymmetry thresholds',
                         'modelling':'Numeric Q is retained in the conditional models; scenario distributions evaluate those models within each Q category'},
            'sensitivity_scenarios':{'tertiles':{'role':'sensitivity_only','method':'nearest_rank_training_Q_tertiles',
                'cuts':tertile_cuts(training),'rules':{'low':'Q <= P33','medium':'P33 < Q <= P67','high':'Q > P67'},
                'modelling':'Same conditional-Q models; only scenario aggregation changes. No separate fit required.'}},
            'models':models,'no_Q_benchmarks':baselines,'dependence':fit_dependence(training,z,models,seed)}
    if parameter_uncertainty:
        bundle['parameter_uncertainty']={outcome:cluster_coefficient_uncertainty(training[outcome].to_numpy(float),z,training.get('cv_dependency_group',training[ENTITY]).astype(str).to_numpy(),model) for outcome,model in models.items()}
    return bundle,candidates


def audit_marginals(training,bundle):
    rows=[]
    for phase in [TOTAL]+PHASES:
        model=bundle['models'][phase]
        rows.append({'fit_id':bundle['fit_id'],'outcome':phase,'training_n':len(training),
                     'positive_n':int(training[phase].gt(0).sum()),'zero_n':int(training[phase].eq(0).sum()),
                     'kind':model['kind'],'family':model.get('family',''),
                     'structure':model.get('structure',''),'limitation':model.get('limitation','')})
    return rows


def atomic_json(path,data):
    temporary=path.with_suffix('.tmp.json')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def cluster_coefficient_uncertainty(values,z,entities,model):
    """Cluster score sandwich, conditional on selected working family/structure.

    Positive observations enter the positive-component likelihood. Entire entity
    scores are summed before forming the meat. No model-selection, zero-mass,
    copula or Q-cut uncertainty is included; these are not causal coefficients.
    """
    if model['kind']!='parametric_positive_with_zero_mass':
        return {'status':'NO_PARAMETRIC_COEFFICIENTS','limitation':model.get('limitation','Constant outcome')}
    mask=values>0; y=values[mask]; zz=z[mask]; entity=entities[mask]
    indices=list(STRUCTURES[model['structure']]); theta=np.array(model['coefficients_abcd'])[indices]
    def contributions(t):
        m={**model,'coefficients_abcd':np.zeros(4).tolist()}
        beta=np.zeros(4); beta[indices]=t; m['coefficients_abcd']=beta.tolist()
        return distribution(m,zz).logpdf(y)
    def objective(t): return -float(contributions(t).sum())
    k=len(theta); steps=1e-4*(1+np.abs(theta)); hessian=np.empty((k,k)); score=np.empty((len(y),k))
    center=objective(theta)
    for i in range(k):
        ei=np.zeros(k); ei[i]=steps[i]
        score[:,i]=(contributions(theta+ei)-contributions(theta-ei))/(2*steps[i])
        hessian[i,i]=(objective(theta+ei)-2*center+objective(theta-ei))/steps[i]**2
        for j in range(i):
            ej=np.zeros(k); ej[j]=steps[j]
            hessian[i,j]=hessian[j,i]=(objective(theta+ei+ej)-objective(theta+ei-ej)-objective(theta-ei+ej)+objective(theta-ei-ej))/(4*steps[i]*steps[j])
    cluster=pd.DataFrame(score).groupby(entity,sort=True).sum().to_numpy(); g=len(cluster)
    eig=np.linalg.eigvalsh(hessian)
    if g<=k+1 or not np.isfinite(hessian).all() or eig.min()<=0:
        return {'status':'UNSTABLE_HESSIAN_OR_TOO_FEW_CLUSTERS','dependency_clusters':g}
    cluster-=cluster.mean(axis=0)
    bread=np.linalg.inv(hessian); covariance=(g/(g-1))*bread@(cluster.T@cluster)@bread
    covariance=(covariance+covariance.T)/2
    if not np.isfinite(covariance).all() or np.diag(covariance).min()<0:
        return {'status':'UNSTABLE_SANDWICH','dependency_clusters':g}
    se=np.sqrt(np.diag(covariance))
    return {'status':'FIXED_MODEL_DEPENDENCY_CLUSTER_SANDWICH','dependency_clusters':g,
            'free_parameters':[list('abcd')[i] for i in indices],
            'covariance':covariance.tolist(),'standard_errors':se.tolist(),
            'ci95_low':(theta-1.96*se).tolist(),'ci95_high':(theta+1.96*se).tolist(),
            'hessian_condition_number':float(np.linalg.cond(hessian)),
            'limitation':'Pointwise normal approximation conditional on selected model; no selection, cutpoint, copula or zero-mass uncertainty propagated downstream'}


def uncertainty_rows(bundle):
    rows=[]
    for outcome,uncertainty in bundle['parameter_uncertainty'].items():
        names=uncertainty.get('free_parameters',[])
        if not names: rows.append({'outcome':outcome,'parameter':'','status':uncertainty['status']})
        for i,name in enumerate(names):
            rows.append({'outcome':outcome,'parameter':name,'estimate':bundle['models'][outcome]['coefficients_abcd'][list('abcd').index(name)],
                         'cluster_se':uncertainty['standard_errors'][i],'ci95_low':uncertainty['ci95_low'][i],
                         'ci95_high':uncertainty['ci95_high'][i],'dependency_clusters':uncertainty['dependency_clusters'],'status':uncertainty['status']})
    return rows


def marginal_forecast(model,z,y=None):
    n=len(z); kind=model['kind']
    if kind=='constant':
        value=model['value']; mean=np.full(n,value); quantiles=[mean.copy() for _ in range(3)]
        score=np.where(y==value,0.,-np.inf) if y is not None else None
    else:
        pzero=model['p_zero']
        if kind=='empirical_zero_positive_mixture':
            support=np.asarray(model['positive_values'],float)
            mean=np.full(n,(1-pzero)*support.mean())
            quantiles=[np.full(n,0. if p<=pzero else np.quantile(support,(p-pzero)/(1-pzero),method='inverted_cdf')) for p in [.1,.5,.9]]
            if y is not None:
                mass=np.array([pzero if v==0 else (1-pzero)*np.mean(support==v) for v in y])
                with np.errstate(divide='ignore'): score=np.log(mass)
        else:
            rv=distribution(model,z); mean=(1-pzero)*rv.mean(); quantiles=[]
            for p in [.1,.5,.9]:
                quantiles.append(np.zeros(n) if p<=pzero else rv.ppf((p-pzero)/(1-pzero)))
            if y is not None:
                score=np.full(n,-np.inf); positive=y>0
                if pzero>0: score[~positive]=np.log(pzero)
                score[positive]=np.log1p(-pzero)+distribution(model,z[positive]).logpdf(y[positive])
        if y is None: score=None
    return {'mean':mean,'p10':quantiles[0],'median':quantiles[1],'p90':quantiles[2],'log_score':score}


def out_of_fold_predictions(heldout,bundle,fold):
    transform=bundle['Q_transform']; z=(np.log1p(heldout[Q].to_numpy(float))-transform['mean'])/transform['std_population']
    scenarios=classify(heldout[Q].to_numpy(),bundle['scenarios']['cuts'])
    records=[]
    for outcome in [TOTAL]+PHASES:
        y=heldout[outcome].to_numpy(float)
        prediction=marginal_forecast(bundle['models'][outcome],z,y)
        benchmark=marginal_forecast(bundle['no_Q_benchmarks'][outcome],z,y)
        for i,(_,row) in enumerate(heldout.iterrows()):
            records.append({'procedure_code':row.procedure_code,'fold':fold,'outcome':outcome,ENTITY:str(row[ENTITY]),
                            'notice_year':int(row.source00_notice_date.year),'entity_type':row.get('source00_entity_type','UNKNOWN'),
                            'cv_dependency_group':row.get('cv_dependency_group',str(row[ENTITY])),'training_scenario':scenarios[i],Q:row[Q],
                            'observed':y[i],'predicted_mean':prediction['mean'][i],'predicted_median':prediction['median'][i],
                            'p10':prediction['p10'][i],'p90':prediction['p90'][i],
                            'selected_log_score':prediction['log_score'][i],'no_Q_log_score':benchmark['log_score'][i],
                            'no_Q_predicted_median':benchmark['median'][i],
                            'family':bundle['models'][outcome].get('family',bundle['models'][outcome]['kind']),
                            'structure':bundle['models'][outcome].get('structure','empirical'),
                            'score_scope':'Working continuous positive density plus zero/empirical mass; not a rounded-day PMF'})
    return records


def prediction_metrics(predictions):
    rows=[]
    for outcome,part in predictions.groupby('outcome',sort=False):
        selected=part.selected_log_score.to_numpy(float); baseline=part.no_Q_log_score.to_numpy(float)
        finite=np.isfinite(selected)&np.isfinite(baseline); all_finite=bool(finite.all())
        gain=selected-baseline if all_finite else None
        se=np.nan; lo=np.nan; hi=np.nan
        if gain is not None:
            centered=gain-gain.mean(); scores=pd.Series(centered,index=part.index).groupby(part.get('cv_dependency_group',part[ENTITY])).sum()
            g=len(scores)
            if g>1:
                se=float(np.sqrt(g/(g-1)*np.square(scores).sum())/len(part)); lo=float(gain.mean()-1.96*se); hi=float(gain.mean()+1.96*se)
        rows.append({'outcome':outcome,'n':len(part),'dependency_clusters':part.get('cv_dependency_group',part[ENTITY]).nunique(),'unsupported_selected_values':int((~np.isfinite(selected)).sum()),
                     'unsupported_no_Q_values':int((~np.isfinite(baseline)).sum()),
                     'mean_selected_log_score':float(selected.mean()) if np.isfinite(selected).all() else np.nan,
                     'mean_no_Q_log_score':float(baseline.mean()) if np.isfinite(baseline).all() else np.nan,
                     'mean_selected_minus_no_Q':float(gain.mean()) if gain is not None else np.nan,
                     'gain_cluster_se':se,'gain_ci95_low':lo,'gain_ci95_high':hi,
                     'MAE_selected_median':float((part.observed-part.predicted_median).abs().mean()),
                     'MAE_no_Q_median':float((part.observed-part.no_Q_predicted_median).abs().mean()),
                     'central_80_coverage':float(((part.observed>=part.p10)&(part.observed<=part.p90)).mean()),
                     'mean_predicted':float(part.predicted_mean.mean()),'mean_observed':float(part.observed.mean()),
                     'scope':'Descriptive OOF marginal diagnostics; pointwise gain CI clustered by connected entity/project component. Not joint phase-sum validation.'})
    return pd.DataFrame(rows)


def stratified_metrics(predictions,column):
    rows=[]
    for label,part in predictions.groupby(column,dropna=False,sort=True):
        metrics=prediction_metrics(part)
        metrics.insert(0,column,label); rows.append(metrics)
    return pd.concat(rows,ignore_index=True)


def downstream_compatibility(bundle):
    models=bundle['models']; rows=[]
    for outcome in [PHASES[0],PHASES[2]]:
        m=models[outcome]
        ok=m['kind']=='parametric_positive_with_zero_mass' and m.get('family')=='lognormal' and m['p_zero']==0
        rows.append({'consumer':'06/07','contract':outcome+' interpreted as positive lognormal','compatible':ok,
                     'detail':'Consumer hard-codes lognormal PPF; selection is not forced for compatibility'})
    m=models[PHASES[1]]
    rows.append({'consumer':'06/07','contract':'Empirical integration mixture','compatible':m['kind']=='empirical_zero_positive_mixture' and bool(m.get('positive_values')),
                 'detail':'Consumers require p_zero and positive_values; constant/parametric alternatives need consumer changes'})
    m=models[PHASES[0]]
    rows.append({'consumer':'09','contract':'Absolution shape independent of Q','compatible':m.get('family')=='lognormal' and m.get('coefficients_abcd',[0,0,0,1])[3]==0,
                 'detail':'Current 09 omits d*z for absolution'})
    rows.append({'consumer':'09','contract':'Total includes integration','compatible':models[PHASES[1]]['p_zero']==1,
                 'detail':'Current 09 drops integration even if positive; this is not the same total as 05'})
    rows.append({'consumer':'07/08','contract':'Grouped OOF assessment and parameter uncertainty','compatible':False,
                 'detail':'Current consumers use full-cohort fits/point estimates; they do not consume the OOF diagnostic or cluster uncertainty artifacts'})
    return pd.DataFrame(rows)


def refit_fixed(model,values,z):
    pzero=float(np.mean(values==0)); y=values[values>0]; zz=z[values>0]
    if model['kind']!='parametric_positive_with_zero_mass':
        return {'kind':'empirical_zero_positive_mixture','positive_values':y.tolist(),'p_zero':pzero,'positive_n':len(y)} if len(y) else {'kind':'constant','value':0.,'p_zero':1.,'positive_n':0}
    indices=list(STRUCTURES[model['structure']]); start=np.array(model['coefficients_abcd'])[indices]
    bounds=[(-12,20),(-5,5),(-6,4),(-3,3)]
    def objective(theta):
        beta=np.zeros(4); beta[indices]=theta
        with np.errstate(over='ignore',divide='ignore',invalid='ignore'):
            density=distribution({**model,'coefficients_abcd':beta.tolist()},zz).logpdf(y)
        return -float(density.sum()) if np.isfinite(density).all() else 1e100
    result=optimize.minimize(objective,start,method='L-BFGS-B',bounds=[bounds[i] for i in indices],options={'maxiter':2000,'ftol':1e-11})
    if not result.success or not np.isfinite(result.fun) or any(abs(v-lo)<1e-5 or abs(v-hi)<1e-5 for v,(lo,hi) in zip(result.x,[bounds[i] for i in indices])):
        raise RuntimeError('Fixed-model family sensitivity fit did not converge to an interior solution')
    beta=np.zeros(4); beta[indices]=result.x
    return {**model,'coefficients_abcd':beta.tolist(),'p_zero':pzero,'positive_n':len(y)}


def family_sensitivity(data,bundle):
    indexed=data.set_index('procedure_code'); registry=[]
    related=set()
    for family,a,b in FAMILIES:
        if a not in indexed.index or b not in indexed.index: raise ValueError('Missing documented family record')
        related.update((a,b))
        if indexed.loc[a,'cv_fold']!=indexed.loc[b,'cv_fold']: raise RuntimeError('Related family crossed folds')
        for code in (a,b): registry.append({'family':family,'procedure_code':code,'fold':indexed.loc[code,'cv_fold'],ENTITY:str(indexed.loc[code,ENTITY]),'policy':'Related reference records retained; sensitivity is not definitive deduplication'})
    choices=[('full',data),('exclude_four',data.loc[~data.procedure_code.isin(related)])]
    import itertools
    for retain in itertools.product(*[(a,b) for _,a,b in FAMILIES]):
        choices.append(('retain_'+'_'.join(retain),data.loc[~data.procedure_code.isin(related-set(retain))]))
    transform=bundle['Q_transform']; rows=[]; q50=float(data[Q].median()); at=np.array([(np.log1p(q50)-transform['mean'])/transform['std_population']])
    for name,part in choices:
        z=(np.log1p(part[Q].to_numpy(float))-transform['mean'])/transform['std_population']; cuts=scenario_cuts(part)
        for outcome,model in bundle['models'].items():
            fitted=model if name=='full' else refit_fixed(model,part[outcome].to_numpy(float),z)
            mean=float(marginal_forecast(fitted,at)['mean'][0]); base=float(marginal_forecast(model,at)['mean'][0])
            row={'cohort':name,'n':len(part),'outcome':outcome,'P25':cuts[0],'P75':cuts[1],'p_zero':fitted['p_zero'],
                 'family':fitted.get('family',fitted['kind']),'structure':fitted.get('structure','empirical'),
                 'prediction_Q':q50,'mean_at_Q50':mean,'relative_mean_change_percent':100*(mean-base)/base if base else np.nan,
                 'policy':'Selected structure and full-cohort Q transform fixed; only parameters refitted; no definitive deduplication'}
            row.update(dict(zip(list('abcd'),fitted.get('coefficients_abcd',[np.nan]*4)))); rows.append(row)
    return pd.DataFrame(registry),pd.DataFrame(rows)


def legacy_build_calibration(root,output,input_hash,script_hash,seed):
    source=root/'02_results'/'01_sample_and_data'/'03_2_model_ready_dataset.xlsx'
    try:
        data=validate(pd.read_excel(source,dtype={'procedure_code':str,ENTITY:str})).sort_values('procedure_code').reset_index(drop=True)
        data=assign_folds(data,seed=seed)
        log(f'SCENARIOS AND CALIBRATION | {VERSION} | eligible={len(data)}')
        log('All study years retained; five entity/project-component folds; no future-year holdout')
        candidates=[];marginal_audit=[];fold_bundles=[];fold_rows=[];oof_rows=[]
        data['scenario_out_of_fold']=''
        data['tertile_sensitivity_out_of_fold']=''
        data['cv_Q_outside_training_range']=False
        for fold in range(1,6):
            mask=data.cv_fold.eq(fold);training=data.loc[~mask].copy();heldout=data.loc[mask].copy()
            for group in ['cv_project_group','cv_dependency_group',ENTITY]:
                if set(training[group])&set(heldout[group]): raise RuntimeError(f'{group} leakage between training and validation')
            log(f'Fold {fold}/5: calibrating {len(training)} | reserved for validation {len(heldout)}')
            bundle,rows=calibrate(training,f'fold_{fold:02d}',seed=seed+fold)
            bundle.update(schema_version=VERSION,artifact_role='cross_validation_training_fit',fold=fold,
                          input_sha256=input_hash,script_sha256=script_hash,
                          validation_procedure_codes=sorted(heldout.procedure_code.tolist()),
                          validation_n=len(heldout),date_nature=DATE_NATURE,target=TOTAL,
                          phase_order=PHASES,duration_unit='calendar_days',origin='query_close')
            oof_rows.extend(out_of_fold_predictions(heldout,bundle,fold))
            data.loc[mask,'scenario_out_of_fold']=classify(heldout[Q].to_numpy(),bundle['scenarios']['cuts'])
            tcuts=bundle['sensitivity_scenarios']['tertiles']['cuts']
            data.loc[mask,'tertile_sensitivity_out_of_fold']=(classify_tertiles(heldout[Q].to_numpy(),tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS')
            lo,hi=bundle['training_Q_range']
            data.loc[mask,'cv_Q_outside_training_range']=heldout[Q].lt(lo)|heldout[Q].gt(hi)
            fold_rows.append({'fold':fold,'training_n':len(training),'validation_n':len(heldout),
                              'training_project_groups':training.cv_project_group.nunique(),
                              'validation_project_groups':heldout.cv_project_group.nunique(),
                              'training_entities':training[ENTITY].nunique(),'validation_entities':heldout[ENTITY].nunique(),
                              'dependency_overlap':len(set(training.cv_dependency_group)&set(heldout.cv_dependency_group)),
                              'primary_P25':bundle['scenarios']['cuts'][0],'primary_P75':bundle['scenarios']['cuts'][1],
                              'sensitivity_P33':tcuts[0] if tcuts else None,'sensitivity_P67':tcuts[1] if tcuts else None,
                              'validation_Q_outside_training_range':int(data.loc[mask,'cv_Q_outside_training_range'].sum())})
            candidates.extend(rows);marginal_audit.extend(audit_marginals(training,bundle));fold_bundles.append(bundle)
        if data.scenario_out_of_fold.eq('').any() or sum(b['validation_n'] for b in fold_bundles)!=len(data):
            raise RuntimeError('Cross-validation coverage incomplete')
        log(f'Final application fit: calibrating all {len(data)} procedures')
        final,rows=calibrate(data,'full_cohort_application_fit',seed=seed,parameter_uncertainty=True)
        candidates.extend(rows);marginal_audit.extend(audit_marginals(data,final))
        cuts=final['scenarios']['cuts'];data['asymmetry_scenario']=classify(data[Q].to_numpy(),cuts)
        tcuts=final['sensitivity_scenarios']['tertiles']['cuts']
        data['tertile_sensitivity_scenario']=(classify_tertiles(data[Q].to_numpy(),tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS')
        scenario_summary=[]
        for label in ['low','medium','high']:
            group=data.loc[data.asymmetry_scenario.eq(label)]
            if group.empty:raise RuntimeError('Empty final scenario')
            scenario_summary.append({'scenario':label,'procedures':len(group),'Q_min':int(group[Q].min()),
                                     'Q_max':int(group[Q].max()),'verified_Q_zero_n':int(group[Q].eq(0).sum())})
        log(f'PRIMARY scenarios: low Q<{cuts[0]:g} | medium {cuts[0]:g}<=Q<={cuts[1]:g} | high Q>{cuts[1]:g}')
        log(f'SENSITIVITY tertile cuts only: {tcuts}')
        for phase in PHASES:
            model=final['models'][phase]
            log(f"{phase}: {model['kind']} | positive={model['positive_n']} | zero probability={model['p_zero']:.6f}")
        spec={
            **final,'schema_version':VERSION,'artifact_role':'full_cohort_application_fit_NOT_out_of_fold_validation',
            'input_sha256':input_hash,'script_sha256':script_hash,'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'date_nature':DATE_NATURE,'target':TOTAL,'duration_unit':'calendar_days','origin':'query_close',
            'predictor_columns':[Q],'covariates_X':'None in this initial model; source variables retained',
            'cross_validation':{'kind':'seeded_entity_project_component_5_fold','seed':seed,'folds':5,'all_procedures_n':len(data),
                                'grouping':'Connected components of entity identifiers and explicit CUI/exact-description project identifiers; documented families forced together',
                                'scope':'Held-out entity/project components within the pooled 2020-2025 cohort; not future-year performance or an untouched external test',
                                'limitations':'Entity identifiers and conservative project linkage define the split; undetected cross-entity project relations may remain. Full cohort previously explored by Script 04.',
                                'validation_rule':'Use only the fold model excluding each procedure/project for out-of-fold predictions; never validate with this full-cohort fit',
                                'scenario_rule':'Primary and sensitivity out-of-fold scenarios use training-only cuts; final application labels use full-cohort cuts'},
            'hypothesis_contract':{'primary_groups':'Q < P25 versus Q > P75; boundaries assigned to medium',
                'H1':'sigma_high > sigma_low','H0':'sigma_high <= sigma_low','alpha':0.05,
                'outcome':TOTAL,'evidence':'Published schedule differences of eligible records, not verified actual event durations or simulated replicas as additional evidence',
                'scope':'This script defines groups and fits models; inferential dispersion contrast remains a separate analysis',
                'sensitivity':'Tertiles are supplementary and do not replace the primary hypothesis'},
            'DES_event_specification':{'initial_event':'query_close','event_order':PHASE_LABELS,'durations':PHASES,
                                       'recurrence':'event_time[j+1] = event_time[j] + duration[j]',
                                       'resources_or_queues':'Not identified or invented',
                                       'verification':'Sequential DES and direct sum must agree for identical sampled durations'},
            'equations':{'z':'(log(1+Q)-Q_transform.mean)/Q_transform.std_population',
                         'lognormal':'log(T_positive) = a+b*z + exp(c+d*z)*epsilon; epsilon~N(0,1)',
                         'weibull':'T_positive~Weibull(shape=exp(c+d*z), scale=exp(a+b*z))',
                         'zero_mass':'P(T=0)=p_zero; positive component weight=1-p_zero',
                         'risk':'P(T_total>d | Q=q); stage-based probabilities computed by Script 06'},
            'selection':'Minimum working IID BIC among converged interior positive-duration candidates; two deterministic starts. Correlated records mean BIC is a heuristic, not robust model evidence. No held-out outcome is used for selection.',
            'limitations':['Positive continuous marginals approximate integer calendar days; rounding/ties require explicit handling in validation.',
                           'Zero probability constant in Q. Sparse positive phases use empirical values; their Q relationship and unobserved tails are not estimated.',
                           'Residual copula constant across Q; sparse phases assumed independent; assumptions require sensitivity assessment.',
                           'No causal effect, superiority of DES, actual-event accuracy or predictive adequacy established by calibration.'],
            'minimum_positive_parametric_sample':MIN_POSITIVE,
            'versions':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'scipy':scipy.__version__}}
        notes=pd.DataFrame([
            ('population','Every eligible record remains in classification and participates once as validation and four times as training in five-fold CV.'),
            ('final_fit','Uses the entire eligible cohort for subsequent application. Its fitted values are not out-of-fold validation results.'),
            ('folds','Seeded entity/project-component allocation using identifiers/descriptions and group sizes only, never outcomes.'),
            ('grouping_limit','Entities, detected projects and documented families remain together. Undetected cross-entity project links can remain.'),
            ('scenario_method','PRIMARY: linear-interpolated P25/P75 of Q; low Q<P25, high Q>P75, medium includes boundaries. Equal-Q values remain together.'),
            ('sensitivity_method','SENSITIVITY ONLY: previous nearest-rank tertiles with low <=P33 and high >P67. Same conditional-Q models; alternative aggregation, not another primary hypothesis.'),
            ('hypothesis_contrast','Direction is higher observed-duration SD in high versus low Q. No dispersion hypothesis p-value or validation conclusion is calculated here.'),
            ('scenario_validation','Use scenario_out_of_fold for out-of-fold scenario validation; asymmetry_scenario is the final full-cohort classification.'),
            ('model_horizon','Query CLOSE to award END, partitioned into three nonoverlapping blocks. Formulation duration is outside this target.'),
            ('zero_days','Both dates can be complete and equal. Such intervals are observed zeros, not missing values.'),
            ('phase_model','Blocks include waiting between events; no individual query handling times, resource capacities or queues inferred.'),
            ('selection','Training-only positive-component BIC comparison of lognormal/Weibull and no-Q/location-Q/location-and-shape-Q structures.'),
            ('sparse_safeguard',f'Fewer than {MIN_POSITIVE} positive cases or three distinct positive values triggers empirical positives; numerical safeguard, not case exclusion.'),
            ('scope','Calibration plus descriptive out-of-fold marginal diagnostics only. Existing 06–09 do not yet consume the fold predictions or parameter uncertainty.'),
            ('leakage','Cuts, Q standardization, zero masses, marginal candidates and residual dependence re-estimated from training data for every fold.'),
            ('validation_limit','Grouped pooled-cohort CV does not establish future-year performance. Earlier whole-cohort exploration prevents claiming a wholly untouched external test.'),
        ],columns=['item','description'])
        if sha(source)!=input_hash:raise RuntimeError('Input changed during calibration; no outputs replaced')
        # Every output is built inside the private staging directory.
        predictions=pd.DataFrame(oof_rows)
        predictive_metrics=prediction_metrics(predictions)
        compatibility=downstream_compatibility(final)
        spec['downstream_compatibility']=compatibility.to_dict('records')
        spec['assumption_status']={
            'scenarios':'Empirical Q-volume strata under a prespecified quantile rule, not validated information-asymmetry levels or interventions',
            'positive_marginals':'Working continuous approximation to integer calendar-day differences; no censoring/truncation or inclusive +1 added',
            'zero_probability':'Unconditional empirical proportion, assumed constant in Q; sparse integration is not a fitted Q regression',
            'copula':'Gaussian latent dependence constant in Q; sparse integration independent by assumption, not demonstrated empirically',
            'uncertainty':'Connected entity/project-component sandwich for fixed selected marginal coefficients only; excludes model selection, cuts, zero mass and copula uncertainty',
            'heterogeneity':'Q-only pooled model; entity-grouped CV and stratified predictive diagnostics assess limitations but do not model entity/year effects',
            'parameter_use':'Current simulation scripts condition on point estimates and do not propagate parameter uncertainty',
            'direct_total':'Separate marginal benchmark; it is not the distribution of the sum of fitted phases',
        }
        extra_notes=[
            ('score_policy','Out-of-fold positive scores are continuous log densities, zero/empirical branches are probability masses. They are working mixed-measure diagnostics, not rounded-day PMF scores or KS hypothesis tests.'),
            ('sparse_prediction','Any unsupported held-out empirical value is counted explicitly; an overall mean log score is not reported when any value has zero predictive probability.'),
            ('parameter_uncertainty','Pointwise normal intervals from connected entity/project-component score sandwich conditional on selected family/structure. No causal or post-selection coverage claim.'),
            ('downstream_contract','06/07 hard-code lognormal active phases and an empirical integration mixture. 09 additionally fixes absolution shape and omits integration; 08 does not use grouped out-of-fold diagnostics. Compatibility is reported, not forced by model selection.'),
            ('family_sensitivity','Alternative family views refit the selected marginal structures only; no new selection search and no definitive deduplication.'),
        ]
        notes=pd.concat([notes,pd.DataFrame(extra_notes,columns=['item','description'])],ignore_index=True)
        coefficient_rows=uncertainty_rows(final)
        family_audit,family_fits=family_sensitivity(data,final)
        predictions.to_csv(output/'05_5_out_of_fold_predictions.csv',index=False,encoding='utf-8-sig')
        cv_dir=output/'05_cv_models';cv_dir.mkdir(exist_ok=True)
        manifest=[]
        for bundle in fold_bundles:
            path=cv_dir/f"fold_{bundle['fold']:02d}.json";atomic_json(path,bundle)
            manifest.append({'fold':bundle['fold'],'path':str(path.relative_to(output)).replace('\\','/'),'sha256':sha(path),
                             'training_n':bundle['training_n'],'validation_n':bundle['validation_n']})
        spec['cross_validation']['model_files']=manifest
        csv=output/'05_1_classified_dataset.csv';temp=csv.with_suffix('.tmp.csv')
        data.to_csv(temp,index=False,encoding='utf-8-sig');temp.replace(csv)
        assignments=data[['procedure_code','cv_project_group','cv_group_basis','cv_fold','scenario_out_of_fold','asymmetry_scenario','tertile_sensitivity_out_of_fold','tertile_sensitivity_scenario','cv_Q_outside_training_range','cv_dependency_group',ENTITY]]
        assignments.to_csv(output/'05_4_cv_assignments.csv',index=False,encoding='utf-8-sig')
        spec['classified_csv_sha256']=sha(csv);spec['cv_assignments_sha256']=sha(output/'05_4_cv_assignments.csv')
        save_workbook(output/'05_1_classified_dataset.xlsx',{'data':data})
        selected=[]
        for bundle in fold_bundles+[final]:
            for outcome,model in bundle['models'].items():
                row={'fit_id':bundle['fit_id'],'outcome':outcome,'kind':model['kind'],'family':model.get('family',''),
                     'structure':model.get('structure',''),'p_zero':model['p_zero'],'positive_n':model['positive_n']}
                row.update(dict(zip(['a','b','c','d'],model.get('coefficients_abcd',[None]*4))))
                selected.append(row)
        sensitivity_rows=[]
        sensitivity_desc=[]
        for method,column in [('primary_P25_P75','asymmetry_scenario'),('sensitivity_tertiles','tertile_sensitivity_scenario')]:
            for scenario,group in data.groupby(column):
                sensitivity_rows.append({'method':method,'scenario':scenario,'procedures':len(group),
                                         'Q_min':int(group[Q].min()),'Q_max':int(group[Q].max())})
                for outcome in [TOTAL]+PHASES:
                    values=group[outcome]
                    sensitivity_desc.append({'method':method,'scenario':scenario,'outcome':outcome,'n':len(group),
                        'mean':values.mean(),'median':values.median(),'std_dev':values.std(ddof=1),
                        'p25':values.quantile(.25),'p75':values.quantile(.75),
                        'interpretation':'Observed full-cohort descriptive only; no hypothesis test or out-of-fold predictive validation'})
        transition=pd.crosstab(data.asymmetry_scenario,data.tertile_sensitivity_scenario).rename_axis('primary_scenario').reset_index()
        train_desc=data.groupby('asymmetry_scenario')[[Q,TOTAL]+PHASES].agg(['count','mean','median','std'])
        train_desc.columns=['__'.join(c) for c in train_desc.columns]
        save_workbook(output/'05_2_calibration_audit.xlsx',{
            'final_scenario_membership':pd.DataFrame(scenario_summary),'cv_fold_audit':pd.DataFrame(fold_rows),
            'selected_models':pd.DataFrame(selected),'candidate_fits':pd.DataFrame(candidates),
            'phase_availability':pd.DataFrame(marginal_audit),'final_descriptives':train_desc.rename_axis('scenario').reset_index(),
            'sensitivity_membership':pd.DataFrame(sensitivity_rows),
            'sensitivity_descriptives':pd.DataFrame(sensitivity_desc),
            'classification_transition':transition,
            'grouping_summary':data.cv_group_basis.value_counts().rename_axis('basis').reset_index(name='procedures'),
            'definitions':notes,'cv_model_manifest':pd.DataFrame(manifest),
            'parameter_uncertainty':pd.DataFrame(coefficient_rows),'oof_metrics':predictive_metrics,
            'oof_by_year':stratified_metrics(predictions,'notice_year'),
            'oof_by_entity_type':stratified_metrics(predictions,'entity_type'),
            'oof_by_scenario':stratified_metrics(predictions,'training_scenario'),
            'related_families':family_audit,'family_fixed_model_sensitivity':family_fits,
            'downstream_compatibility':compatibility})
        atomic_json(output/'05_3_model_parameters.json',spec)
        log(f'BUILT | staged classified={len(data)} | out-of-fold coverage={len(data)}/{len(data)} | final fit={len(data)}')
        log(f'Verified Q=0 retained: {int(data[Q].eq(0).sum())}')
        log('No procedures removed. CV predictions must use fold models; full fit is for application.')
        log(f'Parameters and CV artifacts staged: {output}')
        return spec
    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}');raise


def protected_hashes(root):
    paths=sorted((root/'00_data').glob('*.xlsx'))+sorted(p for p in (root/'02_results/01_sample_and_data').iterdir() if p.is_file())
    return [{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in paths]


def legacy_verify_outputs(output,data_source,spec):
    csv=output/'05_1_classified_dataset.csv'; xlsx=output/'05_1_classified_dataset.xlsx'
    if sha(csv)!=spec['classified_csv_sha256'] or sha(output/'05_4_cv_assignments.csv')!=spec['cv_assignments_sha256']: raise ValueError('Classified/CV fingerprint mismatch')
    data=pd.read_csv(csv,dtype={'procedure_code':str,ENTITY:str})
    with pd.ExcelFile(xlsx) as book:
        excel=pd.read_excel(book,dtype={'procedure_code':str,ENTITY:str})
    if list(data.columns)!=list(excel.columns) or len(data)!=len(excel) or set(data.procedure_code)!=set(data_source.procedure_code): raise ValueError('Classified dataset contract mismatch')
    for col in data.columns:
        left,right=data[col],excel[col]
        if pd.api.types.is_numeric_dtype(right): equal=np.allclose(pd.to_numeric(left),right,equal_nan=True,rtol=1e-12,atol=1e-12)
        elif pd.api.types.is_datetime64_any_dtype(right): equal=pd.to_datetime(left).fillna(pd.Timestamp.min).eq(pd.to_datetime(right).fillna(pd.Timestamp.min)).all()
        else: equal=left.fillna('').astype(str).eq(right.fillna('').astype(str)).all()
        if not equal: raise ValueError(f'Classified Excel/CSV mismatch: {col}')
    for group in [ENTITY,'cv_project_group','cv_dependency_group']:
        if data.groupby(group).cv_fold.nunique().max()!=1: raise ValueError(f'Leakage in published CV table: {group}')
    for entry in spec['cross_validation']['model_files']:
        path=output/entry['path']
        if sha(path)!=entry['sha256']: raise ValueError('CV model hash mismatch')
        bundle=json.loads(path.read_text(encoding='utf-8'))
        train=set(bundle['training_procedure_codes']); validation=set(bundle['validation_procedure_codes'])
        if train&validation or train|validation!=set(data.procedure_code): raise ValueError('CV code coverage/leakage')
        if validation!=set(data.loc[data.cv_fold.eq(bundle['fold']),'procedure_code']): raise ValueError('CV assignment mismatch')
    predictions=pd.read_csv(output/'05_5_out_of_fold_predictions.csv',dtype={'procedure_code':str})
    if len(predictions)!=4*len(data) or predictions.duplicated(['procedure_code','outcome']).any(): raise ValueError('Incomplete OOF marginal predictions')
    with pd.ExcelFile(output/'05_2_calibration_audit.xlsx') as book:
        required=['final_scenario_membership','cv_fold_audit','selected_models','candidate_fits','oof_metrics','parameter_uncertainty','downstream_compatibility']
        if not set(required).issubset(book.sheet_names): raise ValueError('Incomplete audit workbook')
        for name in book.sheet_names: pd.read_excel(book,sheet_name=name)
    return data


def run(root,output_root,seed=SEED):
    root=Path(root).resolve(); output_root=Path(output_root).resolve()
    if output_root==root or output_root==root/'00_data' or (root/'00_data') in output_root.parents: raise ValueError('Use a fresh independent output root outside original 00_data')
    output=output_root/'02_results/02_statistical_analysis'
    if output.exists() or output.is_symlink(): raise FileExistsError(f'Refusing existing output: {output}')
    source=root/'02_results/01_sample_and_data/03_2_model_ready_dataset.xlsx'
    input_hash=sha(source); script_hash=sha(Path(__file__)); before=protected_hashes(root); LOG.clear()
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex
    metadata={'run_id':run_id,'version':VERSION,'started_utc':datetime.now(timezone.utc).isoformat(),
              'seed':seed,'input':str(source),'input_sha256':input_hash,'script_sha256':script_hash,
              'versions':{name:importlib.metadata.version(name) for name in ['pandas','numpy','scipy','openpyxl']},'python':platform.python_version()}
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.05_'+run_id+'_',suffix='.tmp',dir=output.parent))
    logs=output_root/'03_logs/02_statistical_analysis'; logs.mkdir(parents=True,exist_ok=True)
    logfile=logs/f'05_scenarios_and_calibration_{run_id}.log'
    try:
        spec=build_calibration(root,staging,input_hash,script_hash,seed)
        verify_outputs(staging,pd.read_excel(source,dtype={'procedure_code':str}),spec)
        if protected_hashes(root)!=before or sha(Path(__file__))!=script_hash: raise ValueError('Protected input/output or script changed during calibration')
        files=[{'path':str(p.relative_to(staging)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(staging.rglob('*')) if p.is_file()]
        metadata.update(status='COMPLETE',completed_utc=datetime.now(timezone.utc).isoformat(),outputs=files,protected_files=before)
        (staging/'05_run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        if output.exists() or output.is_symlink(): raise FileExistsError('Output appeared during calibration')
        staging.rename(output); log(f'COMPLETE | Validated calibration published: {output}')
        return output
    except Exception:
        log('FAILED | No definitive calibration published\n'+traceback.format_exc())
        if staging.exists():
            if staging.is_symlink() or staging.resolve().parent!=output.parent.resolve() or not staging.name.startswith('.05_'+run_id+'_'): raise RuntimeError('Unsafe staging cleanup path')
            shutil.rmtree(staging)
        raise
    finally:
        with logfile.open('x',encoding='utf-8') as stream: stream.write(json.dumps(metadata,ensure_ascii=False)+'\n'+'\n'.join(LOG)+'\n')



def legacy_run_self_tests():
    """Synthetic tests only; no research files, other scripts or internet used."""
    import contextlib
    import io
    import unittest
    from unittest import mock

    def fixture():
        rng=np.random.default_rng(2041); n=240
        codes=['811044','848861','995451','1058629']+[str(900000+i) for i in range(n-4)]
        q=rng.integers(0,101,n); z=(np.log1p(q)-np.log1p(q).mean())/np.log1p(q).std()
        phase1=np.maximum(1,np.round(np.exp(2+.2*z+.4*rng.standard_normal(n))))
        phase2=np.zeros(n); phase2[[20,65,140,207]]=[1,2,2,8]
        phase3=np.maximum(1,np.round(np.exp(2.8+.12*z+.55*rng.standard_normal(n))))
        data=pd.DataFrame({'procedure_code':codes,Q:q,PHASES[0]:phase1,PHASES[1]:phase2,PHASES[2]:phase3,
                           TOTAL:phase1+phase2+phase3,ENTITY:['E'+str(i//4) for i in range(n)],
                           'source00_procedure_description':['SYNTHETIC ROAD CUI '+str(2000000+i//3) for i in range(n)],
                           'source00_notice_date':[pd.Timestamp(2020+i%6,1,1) for i in range(n)],
                           'eligible_common_model':True,'date_nature':DATE_NATURE,'duration_unit':'calendar_days',
                           'modeled_origin':'query_formulation_start','source02_count_status':'OK',
                           'source02_queries_observations_count':q})
        data[BOUNDARIES[0]]=pd.to_datetime(data.source00_notice_date)+pd.Timedelta(days=1)
        for phase,start,end in zip(PHASES,BOUNDARIES,BOUNDARIES[1:]): data[end]=data[start]+pd.to_timedelta(data[phase],unit='D')
        return data

    class CalibrationTests(unittest.TestCase):
        def setUp(self): self.data=fixture()

        def test_valid_input(self):
            checked=validate(self.data.copy()); self.assertEqual(len(checked),240)

        def test_invalid_Q_and_dates(self):
            part=self.data.copy(); part[Q]=part[Q].astype(float); part.loc[0,Q]=-.5
            with self.assertRaises(ValueError): validate(part)
            part=self.data.copy(); part.loc[0,TOTAL]+=1
            with self.assertRaisesRegex(ValueError,'Phase sum'): validate(part)
            part=self.data.copy(); part[BOUNDARIES[0]]=43831
            with self.assertRaisesRegex(ValueError,'Numeric dates'): validate(part)

        def test_missing_entity_or_duplicate_codes(self):
            with self.assertRaisesRegex(ValueError,'Missing Script 03'): validate(self.data.drop(columns=[ENTITY]))
            part=self.data.copy(); part.loc[0,'procedure_code']=part.loc[1,'procedure_code']
            with self.assertRaisesRegex(ValueError,'duplicate'): validate(part)

        def test_primary_scenario_ties(self):
            labels=classify(np.array([0,7,17,35,36]),[7,35])
            self.assertEqual(labels.tolist(),['low','medium','medium','medium','high'])
            with self.assertRaisesRegex(ValueError,'coincide'): scenario_cuts(pd.DataFrame({Q:[1]*100}))

        def test_tertile_ties_and_collapse(self):
            self.assertEqual(classify_tertiles(np.array([0,10,11,27,28]),[10,27]).tolist(),['low','low','medium','medium','high'])
            self.assertIsNone(tertile_cuts(pd.DataFrame({Q:[0]*100+[1]*200})))

        def test_fold_leakage_and_reproducibility(self):
            a=assign_folds(self.data); b=assign_folds(self.data.sample(frac=1,random_state=5))
            pd.testing.assert_series_equal(a.set_index('procedure_code').cv_fold.sort_index(),b.set_index('procedure_code').cv_fold.sort_index())
            for group in [ENTITY,'cv_project_group','cv_dependency_group']:
                self.assertEqual(a.groupby(group).cv_fold.nunique().max(),1)
            for _,x,y in FAMILIES: self.assertEqual(a.set_index('procedure_code').loc[x,'cv_fold'],a.set_index('procedure_code').loc[y,'cv_fold'])
            self.assertEqual(set(a.cv_fold),set(range(1,6)))

        def test_folds_ignore_outcomes(self):
            first=assign_folds(self.data)
            changed=self.data.copy(); changed[TOTAL]=np.arange(len(changed))*1000
            second=assign_folds(changed)
            self.assertEqual(first.cv_fold.tolist(),second.cv_fold.tolist())

        def test_project_link_across_entities(self):
            data=self.data.copy(); data.loc[0,ENTITY]='UNIQUE_ENTITY'
            assigned=assign_folds(data)
            self.assertEqual(assigned.loc[0,'cv_fold'],assigned.loc[1,'cv_fold'])

        def test_sparse_integration_and_forecast(self):
            values=np.array([0.]*100+[1.,2.,2.,8.]); z=np.linspace(-1,1,len(values))
            model,baseline,rows=fit_marginal(values,z,PHASES[1])
            self.assertEqual(model['kind'],'empirical_zero_positive_mixture'); self.assertEqual(model['positive_n'],4)
            self.assertEqual(rows,[]); self.assertEqual(model,baseline)
            forecast=marginal_forecast(model,np.zeros(2),np.array([0.,9.]))
            self.assertEqual(forecast['median'].tolist(),[0.,0.]); self.assertTrue(np.isneginf(forecast['log_score'][1]))

        def test_constant_model(self):
            model,_,_=fit_marginal(np.zeros(100),np.zeros(100),'test')
            forecast=marginal_forecast(model,np.zeros(2),np.array([0.,1.]))
            self.assertEqual(forecast['log_score'][0],0); self.assertTrue(np.isneginf(forecast['log_score'][1]))

        def test_distribution_and_selected_candidates(self):
            z=(np.log1p(self.data[Q].to_numpy())-np.log1p(self.data[Q]).mean())/np.log1p(self.data[Q]).std(ddof=0)
            selected,baseline,rows=fit_candidates(self.data[PHASES[0]].to_numpy(),z,'test')
            self.assertEqual(len(rows),6); self.assertEqual(sum(row['selected'] for row in rows),1)
            self.assertTrue(selected['accepted']); self.assertEqual(baseline['structure'],'no_Q')
            self.assertEqual(len(selected['coefficients_abcd']),4)

        def test_cluster_sandwich(self):
            y=self.data[PHASES[0]].to_numpy(); logs=np.log(y)
            model={'kind':'parametric_positive_with_zero_mass','family':'lognormal','structure':'no_Q',
                   'coefficients_abcd':[logs.mean(),0,np.log(logs.std(ddof=0)),0],'p_zero':0.,'positive_n':len(y)}
            result=cluster_coefficient_uncertainty(y,np.zeros(len(y)),self.data[ENTITY].to_numpy(),model)
            self.assertEqual(result['status'],'FIXED_MODEL_DEPENDENCY_CLUSTER_SANDWICH')
            self.assertEqual(result['free_parameters'],['a','c'])
            self.assertTrue(np.all(np.linalg.eigvalsh(result['covariance'])>=-1e-12))

        def test_no_unsupported_values_hidden_in_score(self):
            part=pd.DataFrame({'outcome':['x','x'],ENTITY:['A','B'],'selected_log_score':[0.,-np.inf],
                               'no_Q_log_score':[0.,-np.inf],'observed':[0.,9.],'predicted_mean':[0.,0.],
                               'predicted_median':[0.,0.],'no_Q_predicted_median':[0.,0.],'p10':[0.,0.],'p90':[0.,0.]})
            row=prediction_metrics(part).iloc[0]
            self.assertEqual(row.unsupported_selected_values,1)
            self.assertTrue(pd.isna(row.mean_selected_log_score)); self.assertTrue(pd.isna(row.mean_selected_minus_no_Q))

        def test_consumer_contract_detects_weibull(self):
            normal={'kind':'parametric_positive_with_zero_mass','family':'lognormal','coefficients_abcd':[2.,.1,-.5,0.],'p_zero':0.}
            integration={'kind':'empirical_zero_positive_mixture','positive_values':[1.,2.],'p_zero':.99}
            bundle={'models':{PHASES[0]:dict(normal),PHASES[1]:integration,PHASES[2]:dict(normal)}}
            good=downstream_compatibility(bundle)
            self.assertTrue(good.loc[good.consumer.eq('06/07'),'compatible'].all())
            bundle['models'][PHASES[0]]['family']='weibull'
            bad=downstream_compatibility(bundle)
            self.assertFalse(bad.loc[bad.contract.str.startswith(PHASES[0]),'compatible'].iloc[0])

        def test_PIT_reproducible_and_bounded(self):
            model={'kind':'empirical_zero_positive_mixture','p_zero':.5,'positive_values':[1.,2.]}
            values=np.array([0.,0.,1.,2.]); z=np.zeros(4)
            a=randomized_pit(values,z,model,np.random.default_rng(1)); b=randomized_pit(values,z,model,np.random.default_rng(1))
            np.testing.assert_array_equal(a,b); self.assertTrue(((a>0)&(a<1)).all())

        def project(self,folder):
            root=folder/'input'; base=root/'02_results/01_sample_and_data'; base.mkdir(parents=True); (root/'00_data').mkdir()
            path=base/'03_2_model_ready_dataset.xlsx'; self.data.to_excel(path,index=False,engine='openpyxl')
            return root,path

        def test_complete_synthetic_calibration_and_hashes(self):
            with tempfile.TemporaryDirectory(prefix='thesis_script05_test_') as directory:
                folder=Path(directory); root,path=self.project(folder); before=sha(path)
                with contextlib.redirect_stdout(io.StringIO()): output=run(root,folder/'output',123)
                self.assertEqual(before,sha(path))
                manifest=json.loads((output/'05_run_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['status'],'COMPLETE'); self.assertEqual(len(manifest['outputs']),11)
                for entry in manifest['outputs']: self.assertEqual(entry['sha256'],sha(output/entry['path']))
                spec=json.loads((output/'05_3_model_parameters.json').read_text(encoding='utf-8'))
                self.assertEqual(spec['training_n'],240); self.assertEqual(len(spec['cross_validation']['model_files']),5)
                assignments=pd.read_csv(output/'05_4_cv_assignments.csv',dtype={'procedure_code':str})
                for group in [ENTITY,'cv_project_group','cv_dependency_group']: self.assertEqual(assignments.groupby(group).cv_fold.nunique().max(),1)
                audit=pd.read_excel(output/'05_2_calibration_audit.xlsx',sheet_name='family_fixed_model_sensitivity')
                self.assertEqual(set(audit.n),{240,238,236}); self.assertEqual(audit.cohort.nunique(),6)
                oof=pd.read_csv(output/'05_5_out_of_fold_predictions.csv'); self.assertEqual(len(oof),960)
                with self.assertRaises(FileExistsError): run(root,folder/'output',123)
                (output/'05_4_cv_assignments.csv').write_text('corrupt',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'fingerprint'): verify_outputs(output,self.data,spec)

        def test_failed_write_does_not_publish(self):
            with tempfile.TemporaryDirectory(prefix='thesis_script05_test_') as directory:
                folder=Path(directory); root,path=self.project(folder); before=sha(path)
                with mock.patch.dict(globals(),{'build_calibration':mock.Mock(side_effect=PermissionError('synthetic locked output'))}):
                    with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(PermissionError): run(root,folder/'output')
                self.assertFalse((folder/'output/02_results/02_statistical_analysis').exists()); self.assertEqual(before,sha(path))
                self.assertEqual(list((folder/'output/02_results').glob('.05_*.tmp')),[])

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CalibrationTests))
    if not result.wasSuccessful(): raise RuntimeError('Synthetic calibration tests failed; do not use real inputs')



AMOUNT='source00_reference_amount'
GOVTYPE='source00_entity_type'
GOV='calibration_government'
LEVELS=['GOBIERNO LOCAL','GOBIERNO REGIONAL','GOBIERNO NACIONAL']
PRIMARY=['M0','M1','M2','M3','M4']
ABLATIONS=['M2_noQ','M3_noQ','M4_noQ']


def prepare_covariates(data):
    data=data.copy()
    for col in [AMOUNT,GOVTYPE]:
        if col not in data:raise ValueError(f'Missing covariate: {col}')
    data[AMOUNT]=pd.to_numeric(data[AMOUNT],errors='coerce')
    if not np.isfinite(data[AMOUNT]).all() or data[AMOUNT].le(0).any():raise ValueError('Procedure amount must be positive, finite and complete')
    if not data[GOVTYPE].isin(LEVELS+['FONAFE']).all():raise ValueError('Unknown traced entity type; no automatic recoding')
    if 'source00_source_currency' in data and not data.source00_source_currency.isin(['Soles','Nuevos Soles','PEN']).all():raise ValueError('Unknown currency')
    data[GOV]=data[GOVTYPE];data['procedure_amount_log_nominal_PEN']=np.log(data[AMOUNT])
    return data


def grouped_partition(data,nfolds=3,seed=SEED):
    result=assign_folds(data,nfolds,seed)
    sizes=result.groupby('cv_dependency_group').size()
    counts=pd.crosstab(result.cv_dependency_group,result[GOV]).reindex(columns=LEVELS+['FONAFE'],fill_value=0)
    groups=sorted(sizes.index);rng=np.random.default_rng(seed);tie=dict(zip(groups,rng.random(len(groups))))
    ordered=sorted(groups,key=lambda g:(-int(counts.loc[g,LEVELS[2]]>0),-int(counts.loc[g].max()),tie[g]))
    loads=np.zeros((nfolds,4));totals=np.zeros(nfolds);mapping={}
    for g in ordered:
        vector=counts.loc[g].to_numpy(float);dom=int(np.argmax(vector))
        choices=np.flatnonzero(loads[:,dom]==loads[:,dom].min());choices=choices[totals[choices]==totals[choices].min()]
        f=int(rng.choice(choices));mapping[g]=f+1;loads[f]+=vector;totals[f]+=sizes[g]
    result['cv_fold']=result.cv_dependency_group.map(mapping).astype(int)
    if set(result.cv_fold)!=set(range(1,nfolds+1)):raise ValueError('Empty grouped partition')
    return result


def check_split(train,test):
    if set(train.procedure_code)&set(test.procedure_code):raise ValueError('Code leakage')
    for col in [ENTITY,'cv_project_group','cv_dependency_group']:
        if set(train[col])&set(test[col]):raise ValueError(f'Group leakage: {col}')


def cov_transform(train):
    q=np.log1p(train[Q].to_numpy(float));a=np.log(train[AMOUNT].to_numpy(float))
    weights=train.loc[train[GOV].isin(LEVELS),GOV].value_counts(normalize=True).reindex(LEVELS,fill_value=0.)
    if (weights<=0).any():raise ValueError('Government level missing in training')
    if q.std(ddof=0)<=0 or a.std(ddof=0)<=0:raise ValueError('Constant training covariate')
    return {'Q_log1p_mean':float(q.mean()),'Q_log1p_std':float(q.std(ddof=0)),
        'amount_log_mean':float(a.mean()),'amount_log_std':float(a.std(ddof=0)),'government_weights':weights.to_dict(),
        'amount_unit':'nominal_PEN_procedure_reference_amount_not_item',
        'FONAFE_policy':'Special label retained; centered government contrasts zero. Training-weighted average log-location contrast; no reassignment or independent FONAFE coefficient.',
        'price_scope':'Nominal amounts, no deflator in approved inputs; year diagnostics do not establish equal purchasing power.'}


def design(data,t,architecture,outcome):
    q=(np.log1p(data[Q].to_numpy(float))-t['Q_log1p_mean'])/t['Q_log1p_std']
    amount=(np.log(data[AMOUNT].to_numpy(float))-t['amount_log_mean'])/t['amount_log_std']
    base=architecture.replace('_noQ','');hasq=base!='M0' and not architecture.endswith('_noQ')
    cols=[np.ones(len(data))];names=['intercept']
    if hasq:cols.append(q);names.append('Q_standardized_log1p')
    if base in ['M2','M4']:
        regular=data[GOV].isin(LEVELS).to_numpy()
        for level,label in [(LEVELS[1],'government_regional_centered'),(LEVELS[2],'government_national_centered')]:
            cols.append(np.where(regular,data[GOV].eq(level).to_numpy(float)-t['government_weights'][level],0.));names.append(label)
    if base in ['M3','M4']:cols.append(amount);names.append('procedure_amount_standardized_ln_nominal_PEN')
    # Keep the earlier Q-only dispersion specification fixed across M1--M4.
    shapeq=hasq and outcome in [TOTAL,PHASES[2]]
    w=np.column_stack([np.ones(len(data)),q]) if shapeq else np.ones((len(data),1))
    return np.column_stack(cols),w,names,['log_sigma_intercept']+(['log_sigma_Q'] if shapeq else [])


def fit_cov_model(train,architecture,outcome,t):
    y=train[outcome].to_numpy(float)
    if outcome==PHASES[1] and not (y>0).any():return {'kind':'constant','value':0.,'p_zero':1.,'positive_n':0}
    if outcome==PHASES[1]:return {'kind':'empirical_zero_positive_mixture','p_zero':float((y==0).mean()),'positive_values':y[y>0].tolist(),'positive_n':int((y>0).sum())}
    if (y<=0).any():raise ValueError(f'Positive lognormal contract violated: {outcome}')
    x,w,names,snames=design(train,t,architecture,outcome)
    if np.linalg.matrix_rank(x)!=x.shape[1]:raise ValueError('Rank-deficient location design')
    ly=np.log(y);beta=np.linalg.lstsq(x,ly,rcond=None)[0];gamma=np.zeros(w.shape[1]);gamma[0]=np.log(max((ly-x@beta).std(ddof=0),.05))
    initial=np.r_[beta,gamma];k=x.shape[1];bounds=[(-20,20)]+[(-5,5)]*(k-1)+[(-6,4)]+[(-3,3)]*(w.shape[1]-1)
    def objective(theta):
        mu=x@theta[:k];ls=w@theta[k:];v=np.exp(-2*ls);e=ly-mu
        return float(np.sum(ly+ls+.5*np.log(2*np.pi)+.5*e**2*v)),np.r_[-x.T@(e*v),w.T@(1-e**2*v)]
    alt=initial.copy();alt[:k]=0;alt[0]=ly.mean()
    fits=[optimize.minimize(objective,np.clip(start,np.array(bounds)[:,0]+1e-4,np.array(bounds)[:,1]-1e-4),jac=True,method='L-BFGS-B',bounds=bounds,options={'maxiter':1500,'ftol':1e-11,'gtol':1e-6}) for start in [initial,alt]]
    accepted=[f for f in fits if f.success and np.isfinite(f.fun) and all(lo+1e-5<v<hi-1e-5 for v,(lo,hi) in zip(f.x,bounds))]
    if not accepted:raise RuntimeError(f'No converged interior fit {architecture}/{outcome}: {[str(f.message) for f in fits]}')
    best=min(accepted,key=lambda f:f.fun)
    return {'kind':'covariate_lognormal_v3','family':'lognormal','architecture':architecture,'location_names':names,'location_coefficients':best.x[:k].tolist(),
        'log_sigma_names':snames,'log_sigma_coefficients':best.x[k:].tolist(),'positive_n':len(y),'p_zero':0.,'parameters':len(best.x),
        'training_log_likelihood':-float(best.fun),'converged':True,'deterministic_starts':2}


def cov_bundle(train,architecture,outcomes=None):
    t=cov_transform(train)
    return {'architecture':architecture,'training_n':len(train),'transform':t,'training_procedure_codes':sorted(train.procedure_code.astype(str).tolist()),
            'models':{o:fit_cov_model(train,architecture,o,t) for o in (outcomes or [TOTAL]+PHASES)}}


def cov_forecast(data,bundle,outcome):
    model=bundle['models'][outcome];y=data[outcome].to_numpy(float)
    if outcome==PHASES[1]:return marginal_forecast(model,np.zeros(len(data)),y)
    x,w,_,_=design(data,bundle['transform'],bundle['architecture'],outcome)
    rv=stats.lognorm(s=np.exp(w@np.asarray(model['log_sigma_coefficients'])),scale=np.exp(x@np.asarray(model['location_coefficients'])))
    return {'mean':rv.mean(),'median':rv.ppf(.5),'p10':rv.ppf(.1),'p90':rv.ppf(.9),'log_score':rv.logpdf(y)}


def cov_prediction(data,bundle,fold):
    rows=[]
    for outcome in bundle['models']:
        pred=cov_forecast(data,bundle,outcome);frame=data[['procedure_code',ENTITY,'cv_dependency_group',GOV]].copy()
        frame['notice_year']=data.source00_notice_date.dt.year;frame['fold']=fold;frame['model']=bundle['architecture'];frame['architecture']=bundle['architecture'];frame['outcome']=outcome;frame['observed']=data[outcome].to_numpy(float)
        for field in ['mean','median','p10','p90','log_score']:frame[field]=pred[field]
        rows.append(frame)
    return pd.concat(rows,ignore_index=True)


def cov_metrics(predictions,groups=('model','outcome')):
    rows=[]
    for key,part in predictions.groupby(list(groups),sort=True,dropna=False):
        if not isinstance(key,tuple):key=(key,)
        score=part.log_score.to_numpy(float);obs=part.observed.mean();pred=part['mean'].mean()
        rows.append({**dict(zip(groups,key)),'n':len(part),'entities':part[ENTITY].nunique(),'components':part.cv_dependency_group.nunique(),
            'log_score':float(score.mean()) if np.isfinite(score).all() else np.nan,'unsupported_values':int((~np.isfinite(score)).sum()),
            'MAE_median':float((part.observed-part['median']).abs().mean()),'macro_entity_MAE':float((part.observed-part['median']).abs().groupby(part[ENTITY]).mean().mean()),
            'observed_mean':float(obs),'predicted_mean':float(pred),'bias_days':float(pred-obs),'bias_percent':float(100*(pred/obs-1)) if obs else np.nan,
            'coverage80':float(((part.observed>=part.p10)&(part.observed<=part.p90)).mean()),'below_p10':float((part.observed<part.p10).mean()),'above_p90':float((part.observed>part.p90).mean())})
    return pd.DataFrame(rows)


def paired_gain(predictions,left,right):
    a=predictions[predictions.model.eq(left)].set_index(['procedure_code','outcome']);b=predictions[predictions.model.eq(right)].set_index(['procedure_code','outcome']).reindex(a.index)
    gain=a.log_score-b.log_score
    if not np.isfinite(gain).all():return {'gain':None,'cluster_se':None,'ci95_low':None,'ci95_high':None}
    mean=float(gain.mean());v=(gain-mean).groupby(a.cv_dependency_group).sum();g=len(v);se=float(np.sqrt(g/(g-1)*np.square(v).sum())/len(a)) if g>1 else None
    return {'gain':mean,'cluster_se':se,'ci95_low':mean-1.96*se if se is not None else None,'ci95_high':mean+1.96*se if se is not None else None}


def select_architecture(pred,train):
    metrics=cov_metrics(pred).set_index('model');national=cov_metrics(pred[pred[GOV].eq(LEVELS[2])]).set_index('model')
    eligible=PRIMARY[1:];best=max(eligible,key=lambda m:metrics.loc[m,'log_score']);audit=[];t=cov_transform(train)
    for m in eligible:
        tol=paired_gain(pred,best,m)['cluster_se'] or 0.;competitive=metrics.loc[best,'log_score']-metrics.loc[m,'log_score']<=tol+1e-12
        guard=(national.loc[m,'MAE_median']<=1.10*national.loc['M1','MAE_median'] and national.loc[m,'coverage80']>=national.loc['M1','coverage80']-.05 and abs(national.loc[m,'bias_percent'])<=abs(national.loc['M1','bias_percent'])+10.)
        x,w,_,_=design(train,t,m,TOTAL)
        audit.append({'model':m,'best_inner_score':best,'inner_log_score':metrics.loc[m,'log_score'],'paired_one_se_tolerance':tol,'competitive':bool(competitive),'national_guard':bool(guard),'parameters_total':x.shape[1]+w.shape[1]})
    candidates=[v for v in audit if v['competitive'] and v['national_guard']]
    fallback=not bool(candidates)
    if fallback:candidates=[v for v in audit if v['national_guard']]
    chosen=min(candidates,key=lambda v:(v['parameters_total'],-v['inner_log_score'],v['model']))['model']
    for v in audit:v.update(selected=v['model']==chosen,fallback_guard_over_global_tolerance=fallback)
    return chosen,audit


def inner_comparison(train,seed,context):
    split=grouped_partition(train,3,seed);pred=[];assignment=[]
    for f in [1,2,3]:
        a=split[split.cv_fold.ne(f)];b=split[split.cv_fold.eq(f)];check_split(a,b)
        assignment.append({'context':context,'inner_fold':f,'train_codes':sorted(a.procedure_code.tolist()),'validation_codes':sorted(b.procedure_code.tolist())})
        for m in PRIMARY:pred.append(cov_prediction(b,cov_bundle(a,m,[TOTAL]),f))
    predictions=pd.concat(pred,ignore_index=True);chosen,audit=select_architecture(predictions,train)
    return chosen,predictions,[{'context':context,**row} for row in audit],assignment


def covariance_parameters(train,bundle,outcome):
    model=bundle['models'][outcome];x,w,names,snames=design(train,bundle['transform'],bundle['architecture'],outcome)
    y=np.log(train[outcome].to_numpy(float));beta=np.array(model['location_coefficients']);gamma=np.array(model['log_sigma_coefficients']);k=len(beta);theta=np.r_[beta,gamma]
    def scores(t):
        e=y-x@t[:k];v=np.exp(-2*(w@t[k:]));return np.column_stack([x*(e*v)[:,None],w*(e**2*v-1)[:,None]])
    h=1e-5;H=np.column_stack([-(scores(theta+np.eye(len(theta))[i]*h).sum(axis=0)-scores(theta-np.eye(len(theta))[i]*h).sum(axis=0))/(2*h) for i in range(len(theta))]);H=(H+H.T)/2
    if np.linalg.matrix_rank(H)<len(theta):return {'status':'SINGULAR_HESSIAN'}
    sums=pd.DataFrame(scores(theta)).groupby(train.cv_dependency_group.to_numpy()).sum().to_numpy();g=len(sums);inv=np.linalg.inv(H);cov=inv@(sums.T@sums)@inv.T*g/(g-1);cov=(cov+cov.T)/2
    return {'status':'FIXED_MODEL_COMPONENT_SANDWICH','names':names+snames,'covariance':cov.tolist(),'standard_errors':np.sqrt(np.maximum(np.diag(cov),0)).tolist(),'components':g,
        'limitation':'Fixed architecture/design; excludes selection, cutpoint, copula and sparse-mass uncertainty. Six national entities do not support robust national inference.'}


def build_calibration(root,output,input_hash,script_hash,seed):
    source=root/'02_results/01_sample_and_data/03_2_model_ready_dataset.xlsx'
    data=prepare_covariates(validate(pd.read_excel(source,dtype={'procedure_code':str,ENTITY:str}))).sort_values('procedure_code').reset_index(drop=True)
    data=grouped_partition(data,3,seed);allpred=[];selected=[];audits=[];nested=[];foldfiles=[];inner_metrics=[]
    cvdir=output/'05_cv_models';cvdir.mkdir()
    log(f'NESTED CALIBRATION {VERSION}: {len(data)} records, outer=3 inner=3 seed={seed}')
    data['scenario_out_of_fold']='';data['tertile_sensitivity_out_of_fold']='';data['cv_Q_outside_training_range']=False
    for fold in [1,2,3]:
        train=data[data.cv_fold.ne(fold)];test=data[data.cv_fold.eq(fold)];check_split(train,test)
        log(f'Outer {fold}: training={len(train)} heldout={len(test)}; internal selection only')
        chosen,ip,audit,assignments=inner_comparison(train,seed+fold,f'outer_{fold}')
        audits.extend(audit);nested.extend(assignments);im=cov_metrics(ip);im.insert(0,'context',f'outer_{fold}');inner_metrics.append(im)
        cuts=scenario_cuts(train);tcuts=tertile_cuts(train);mask=data.cv_fold.eq(fold)
        data.loc[mask,'scenario_out_of_fold']=classify(test[Q],cuts)
        data.loc[mask,'tertile_sensitivity_out_of_fold']=classify_tertiles(test[Q],tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS'
        data.loc[mask,'cv_Q_outside_training_range']=test[Q].lt(train[Q].min())|test[Q].gt(train[Q].max())
        bundles={}
        for architecture in PRIMARY+ABLATIONS:
            bundle=cov_bundle(train,architecture,[TOTAL] if architecture in ABLATIONS else None);bundles[architecture]=bundle
            frame=cov_prediction(test,bundle,fold);allpred.append(frame)
            if architecture==chosen:frame=frame.copy();frame['model']='NESTED_SELECTED';selected.append(frame)
        payload={'schema_version':VERSION,'fold':fold,'selected_architecture':chosen,'bundles':bundles,
            'training_procedure_codes':sorted(train.procedure_code.tolist()),'validation_procedure_codes':sorted(test.procedure_code.tolist()),'scenario_cuts':cuts,'tertile_cuts':tcuts,'seed':seed+fold}
        file=cvdir/f'fold_{fold:02d}.json';atomic_json(file,payload)
        foldfiles.append({'fold':fold,'path':file.relative_to(output).as_posix(),'sha256':sha(file)})
        log(f'Outer {fold} internally selected {chosen}; held-out forecasts saved')
    predictions=pd.concat(allpred+selected,ignore_index=True)
    log('Final architecture selected by separate full-cohort inner CV; outer errors not used')
    chosen,ip,audit,assignments=inner_comparison(data,seed+100,'full_training_selection')
    audits.extend(audit);nested.extend(assignments);im=cov_metrics(ip);im.insert(0,'context','full_training_selection');inner_metrics.append(im)
    application={m:cov_bundle(data,m) for m in PRIMARY};final=application[chosen];model=final['models'];u={}
    for phase in [PHASES[0],PHASES[2]]:
        x,w,_,_=design(data,final['transform'],chosen,phase)
        u[phase]=stats.norm.ppf(np.clip(stats.lognorm.cdf(data[phase],s=np.exp(w@np.array(model[phase]['log_sigma_coefficients'])),scale=np.exp(x@np.array(model[phase]['location_coefficients']))),1e-6,1-1e-6))
    corr=np.eye(3);corr[0,2]=corr[2,0]=float(np.corrcoef(u[PHASES[0]],u[PHASES[2]])[0,1])
    cuts=scenario_cuts(data);tcuts=tertile_cuts(data);data['asymmetry_scenario']=classify(data[Q],cuts)
    data['tertile_sensitivity_scenario']=classify_tertiles(data[Q],tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS'
    family_rows=[];sensitivity=[];index=data.set_index('procedure_code',drop=False)
    if all(a in index.index and b in index.index for _,a,b in FAMILIES):
        pairs=[(a,b) for _,a,b in FAMILIES];remove={v for pair in pairs for v in pair}
        views=[('full',set()),('exclude_four',remove)]+[(f'keep_{a}_{b}',remove-{a,b}) for a in pairs[0] for b in pairs[1]];reference=None
        for label,excluded in views:
            part=data[~data.procedure_code.isin(excluded)]
            fitted={'architecture':chosen,'transform':final['transform'],'models':{o:fit_cov_model(part,chosen,o,final['transform']) for o in [TOTAL]+PHASES}}
            value=float(cov_forecast(data,fitted,TOTAL)['mean'].mean())
            if reference is None:reference=value
            sensitivity.append({'view':label,'n':len(part),'model':chosen,'standardized_mean_total':value,'relative_change_percent':100*(value/reference-1),
                'policy':'Fixed model and full-cohort transform; common full-cohort covariate profile. Sensitivity, not deduplication.'})
        for name,a,b in FAMILIES:
            for code in [a,b]:family_rows.append({'family':name,'procedure_code':code,'fold':int(index.loc[code,'cv_fold'])})
    summary=cov_metrics(predictions);gov=cov_metrics(predictions,('model','outcome',GOV));year=cov_metrics(predictions,('model','outcome','notice_year'));contrasts=[]
    totalpred=predictions[predictions.outcome.eq(TOTAL)]
    for left,right,question in [('M1','M0','Q versus intercept'),('M2','M1','government adjustment'),('M3','M1','amount adjustment'),('M4','M1','both adjustments')]+[(m,m+'_noQ','Q conditional on matched covariates') for m in ['M2','M3','M4']]:
        contrasts.append({'left':left,'right':right,'question':question,**paired_gain(totalpred,left,right)})
    assignments=data[['procedure_code',ENTITY,'cv_project_group','cv_dependency_group','cv_group_basis','cv_fold',GOV,'scenario_out_of_fold','tertile_sensitivity_out_of_fold','cv_Q_outside_training_range']]
    assignments.to_csv(output/'05_4_cv_assignments.csv',index=False,encoding='utf-8-sig');predictions.to_csv(output/'05_5_out_of_fold_predictions.csv',index=False,encoding='utf-8-sig')
    data.to_csv(output/'05_1_classified_dataset.csv',index=False,encoding='utf-8-sig');save_workbook(output/'05_1_classified_dataset.xlsx',{'classified_dataset':data})
    atomic_json(output/'05_6_nested_assignments.json',{'seed':seed,'splits':nested})
    records=lambda df:json.loads(df.to_json(orient='records'))
    spec={**final,'schema_version':VERSION,'artifact_role':'full_cohort_application_NOT_validation','input_sha256':input_hash,'script_sha256':script_hash,
        'date_nature':DATE_NATURE,'target':TOTAL,'duration_unit':'calendar_days','origin':'query_close','selected_architecture':chosen,'seed':seed,
        'interpretation':'Retrospective calibration of published schedules conditional on Q; not causal or operational prediction at initial notice.',
        'selection_policy':{'eligible':PRIMARY[1:],'M0':'benchmark only; Q retained as primary explanatory variable',
            'primary':'Inner OOF TOTAL continuous log-density; simplest within paired component-cluster one-SE of best',
            'national_guard':'MAE <=110% of M1; coverage80 >=M1-0.05; absolute bias <=M1+10 percentage points',
            'fallback':'If competitive set fails guard, choose simplest guarded architecture; all fallbacks audited',
            'national_adequacy_warning':'Coverage80 below 0.60 or absolute bias above 30% signals inadequate national calibration; diagnostic thresholds, not proof of adequacy above them',
            'no_outer_selection':True,'frozen_family':'lognormal from earlier exploratory calibration; no independently external family selection'},
        'scenarios':{'cuts':cuts,'rules':{'low':'Q<P25','medium':'P25<=Q<=P75','high':'Q>P75'}},'sensitivity_scenarios':{'tertiles':{'cuts':tcuts}},
        'cross_validation':{'kind':'nested_component_grouped_3x3','model_files':foldfiles,'seed':seed,
            'scope':'Internal development evaluation of previously explored cohort; not external or future-year validation',
            'groups':'Connected entity/project components plus related families; government/size balance without outcomes',
            'outer_models':'Fixed candidates descriptive comparison; NESTED_SELECTED evaluates internal selection rule'},
        'application_candidates':application,'parameter_uncertainty':{o:covariance_parameters(data,final,o) for o in [TOTAL,PHASES[0],PHASES[2]]},
        'dependence':{'kind':'gaussian_copula','phase_order':PHASES,'latent_correlation':corr.tolist(),'scope':'Adjusted residual copula refitted; integration independent working assumption; joint phase-sum OOF not validated'},
        'compatibility':{'ready_for_existing_06_09':False,'reason':'v3 covariate location vectors and transforms require explicit consumer updates; no silent abcd substitution',
            'required':'Joint Q/government/procedure-amount profiles; category policy; schema update; grouped OOF validation'},
        'limitations':['Nominal procedure amounts, not item values or inflation-adjusted budgets','Six national entities; singleton FONAFE has no estimable institutional effect',
            'Discrete days approximated by continuous positive densities; no rounded-day PMF validation','Four positive integration delays: empirical support can miss held-out values',
            'Conservative grouping can miss undocumented links','Fixed-model covariance excludes architecture selection, cuts and copula uncertainty'],
        'oof_metrics':records(summary),'oof_government':records(gov),'oof_year':records(year),'Q_contrasts':contrasts,
        'classified_csv_sha256':sha(output/'05_1_classified_dataset.csv'),'cv_assignments_sha256':sha(output/'05_4_cv_assignments.csv')}
    params=[]
    for arch,bundle in application.items():
        for outcome,m in bundle['models'].items():
            for kind in ['location','log_sigma']:
                for name,value in zip(m.get(kind+'_names',[]),m.get(kind+'_coefficients',[])):params.append({'model':arch,'outcome':outcome,'component':kind,'parameter':name,'estimate':value})
    save_workbook(output/'05_2_calibration_audit.xlsx',{'model_comparison':summary,'oof_by_government':gov,'oof_by_year':year,'oof_by_fold':cov_metrics(predictions,('model','outcome','fold')),
        'selection_audit':pd.DataFrame(audits),'inner_metrics':pd.concat(inner_metrics,ignore_index=True),'Q_incremental_information':pd.DataFrame(contrasts),
        'selected_models':pd.DataFrame(params),'related_families':pd.DataFrame(family_rows),'family_sensitivity':pd.DataFrame(sensitivity),'cv_assignments':assignments,
        'downstream_compatibility':pd.DataFrame([{'consumer':c,'compatible':False,'reason':spec['compatibility']['reason']} for c in ['06','07','08','09']]),'limitations':pd.DataFrame({'limitation':spec['limitations']})})
    atomic_json(output/'05_3_model_parameters.json',spec)
    log(f'Final application={chosen}; OOF forecast rows={len(predictions)}; all {len(data)} records retained')
    return spec


def verify_outputs(output,data_source,spec):
    data=pd.read_csv(output/'05_1_classified_dataset.csv',dtype={'procedure_code':str,ENTITY:str});excel=pd.read_excel(output/'05_1_classified_dataset.xlsx',dtype={'procedure_code':str,ENTITY:str})
    if sha(output/'05_1_classified_dataset.csv')!=spec['classified_csv_sha256'] or sha(output/'05_4_cv_assignments.csv')!=spec['cv_assignments_sha256']:raise ValueError('Output fingerprint mismatch')
    if set(data.procedure_code)!=set(data_source.procedure_code.astype(str)) or len(data)!=len(data_source):raise ValueError('Cohort changed')
    for col in data_source.columns:
        if col not in data:raise ValueError(f'Missing original field {col}')
    for col in data:
        left,right=data[col],excel[col]
        if pd.api.types.is_numeric_dtype(right):equal=np.allclose(pd.to_numeric(left),right,equal_nan=True,rtol=1e-12,atol=1e-12)
        elif pd.api.types.is_datetime64_any_dtype(right):equal=pd.to_datetime(left).fillna(pd.Timestamp.min).eq(right.fillna(pd.Timestamp.min)).all()
        else:equal=left.fillna('').astype(str).eq(right.fillna('').astype(str)).all()
        if not equal:raise ValueError(f'Excel/CSV mismatch {col}')
    for col in [ENTITY,'cv_project_group','cv_dependency_group']:
        if data.groupby(col).cv_fold.nunique().max()!=1:raise ValueError('Outer group leakage')
    index=data.set_index('procedure_code',drop=False)
    for entry in spec['cross_validation']['model_files']:
        file=output/entry['path']
        if sha(file)!=entry['sha256']:raise ValueError('Fold hash mismatch')
        b=json.loads(file.read_text(encoding='utf-8'));a=set(b['training_procedure_codes']);v=set(b['validation_procedure_codes'])
        if a&v or a|v!=set(data.procedure_code):raise ValueError('Outer coverage/leakage')
        if v!=set(data.loc[data.cv_fold.eq(entry['fold']),'procedure_code']):raise ValueError('Outer assignment mismatch')
        check_split(index.loc[list(a)],index.loc[list(v)])
        for bundle in b['bundles'].values():
            if set(bundle['training_procedure_codes'])!=a:raise ValueError('Bundle training mismatch')
    nested=json.loads((output/'05_6_nested_assignments.json').read_text(encoding='utf-8'))
    for context in {v['context'] for v in nested['splits']}:
        seen=[]
        for split in [v for v in nested['splits'] if v['context']==context]:
            a=set(split['train_codes']);b=set(split['validation_codes']);check_split(index.loc[list(a)],index.loc[list(b)]);seen.extend(b)
            expected=set(data.procedure_code) if context=='full_training_selection' else set(data.loc[data.cv_fold.ne(int(context.split('_')[-1])),'procedure_code'])
            if a|b!=expected:raise ValueError('Inner split outside outer training')
        if len(seen)!=len(set(seen)) or set(seen)!=expected:raise ValueError('Inner OOF coverage')
    pred=pd.read_csv(output/'05_5_out_of_fold_predictions.csv',dtype={'procedure_code':str});models=PRIMARY+ABLATIONS+['NESTED_SELECTED']
    if set(pred.model)!=set(models) or pred.duplicated(['procedure_code','outcome','model']).any():raise ValueError('Prediction duplicates/model mismatch')
    for m in models:
        for outcome in ([TOTAL] if m in ABLATIONS else [TOTAL]+PHASES):
            if set(pred.loc[pred.model.eq(m)&pred.outcome.eq(outcome),'procedure_code'])!=set(data.procedure_code):raise ValueError('Incomplete OOF coverage')
    with pd.ExcelFile(output/'05_2_calibration_audit.xlsx') as book:
        for sheet in book.sheet_names:pd.read_excel(book,sheet_name=sheet)
    return data


def run_self_tests():
    # Keep the approved 17 helper/transaction tests, then test the v3 path.
    global build_calibration,verify_outputs
    newbuild,newverify=build_calibration,verify_outputs
    try:
        build_calibration,verify_outputs=legacy_build_calibration,legacy_verify_outputs
        legacy_run_self_tests()
    finally:build_calibration,verify_outputs=newbuild,newverify
    import unittest
    import contextlib
    import io
    def fixture():
        rng=np.random.default_rng(501);n=240;q=rng.integers(0,100,n);amount=np.exp(rng.normal(16,.7,n));gov=np.repeat([LEVELS[2]]*8+[LEVELS[1]]*16+[LEVELS[0]]*35+['FONAFE'],4)
        a=np.maximum(1,np.round(np.exp(2+.2*np.log1p(q)+.1*(np.log(amount)-16)+rng.normal(0,.4,n))))
        b=np.maximum(1,np.round(np.exp(2.7+.1*np.log1p(q)+rng.normal(0,.5,n))));integration=np.zeros(n);integration[[20,65,140,207]]=[1,2,2,8]
        d=pd.DataFrame({'procedure_code':[str(600000+i) for i in range(n)],Q:q,AMOUNT:amount,GOVTYPE:gov,PHASES[0]:a,PHASES[1]:integration,PHASES[2]:b,TOTAL:a+integration+b,
            ENTITY:['E'+str(i//4) for i in range(n)],'source00_procedure_description':['ROAD CUI '+str(2100000+i//4) for i in range(n)],
            'source00_notice_date':pd.to_datetime(['2020-01-01']*n),'eligible_common_model':True,'date_nature':DATE_NATURE,'duration_unit':'calendar_days',
            'modeled_origin':'query_formulation_start','source02_count_status':'OK','source02_queries_observations_count':q})
        d[BOUNDARIES[0]]=d.source00_notice_date+pd.Timedelta(days=1)
        for phase,start,end in zip(PHASES,BOUNDARIES,BOUNDARIES[1:]):d[end]=d[start]+pd.to_timedelta(d[phase],unit='D')
        return prepare_covariates(validate(d))
    class NestedTests(unittest.TestCase):
        def setUp(self):self.data=fixture()
        def test_covariate_validation(self):
            d=self.data.copy();d.loc[0,AMOUNT]=0
            with self.assertRaises(ValueError):prepare_covariates(d)
            d=self.data.copy();d.loc[0,GOVTYPE]='UNKNOWN'
            with self.assertRaises(ValueError):prepare_covariates(d)
        def test_training_transform_and_FONAFE(self):
            t=cov_transform(self.data);d=self.data[self.data[GOV].eq('FONAFE')];x,_,names,_=design(d,t,'M4',TOTAL)
            self.assertTrue(np.all(x[:,[names.index('government_regional_centered'),names.index('government_national_centered')]]==0))
            changed=self.data.copy();changed.loc[0,AMOUNT]*=100
            self.assertNotEqual(t['amount_log_mean'],cov_transform(changed)['amount_log_mean']);self.assertEqual(t,cov_transform(self.data))
        def test_partitions_reproducible_without_outcomes(self):
            a=grouped_partition(self.data);d=self.data.copy();d[TOTAL]=np.arange(len(d))*1000;b=grouped_partition(d.sample(frac=1,random_state=1))
            pd.testing.assert_series_equal(a.set_index('procedure_code').cv_fold.sort_index(),b.set_index('procedure_code').cv_fold.sort_index())
            for f in [1,2,3]:check_split(a[a.cv_fold.ne(f)],a[a.cv_fold.eq(f)])
        def test_Q_ablations_and_parameter_contract(self):
            t=cov_transform(self.data)
            for m in PRIMARY+ABLATIONS:
                x,w,names,_=design(self.data,t,m,TOTAL);self.assertEqual('Q_standardized_log1p' in names,m not in ['M0']+ABLATIONS)
                self.assertTrue(np.isfinite(x).all());self.assertTrue(np.isfinite(w).all())
            bundle=cov_bundle(self.data,'M4',[TOTAL]);self.assertEqual(bundle['models'][TOTAL]['kind'],'covariate_lognormal_v3')
            p=cov_forecast(self.data,bundle,TOTAL);self.assertTrue((p['p10']<=p['median']).all());self.assertTrue((p['median']<=p['p90']).all())
        def test_nested_end_to_end_and_hashes(self):
            with tempfile.TemporaryDirectory(prefix='nested05_') as directory:
                root=Path(directory)/'root';folder=root/'02_results/01_sample_and_data';folder.mkdir(parents=True);(root/'00_data').mkdir()
                source=folder/'03_2_model_ready_dataset.xlsx';self.data.drop(columns=[GOV,'procedure_amount_log_nominal_PEN']).to_excel(source,index=False);before=sha(source)
                with contextlib.redirect_stdout(io.StringIO()):out=run(root,Path(directory)/'output',SEED)
                self.assertEqual(before,sha(source));spec=json.loads((out/'05_3_model_parameters.json').read_text(encoding='utf-8'))
                self.assertIn(spec['selected_architecture'],PRIMARY[1:]);self.assertFalse(spec['compatibility']['ready_for_existing_06_09'])
                manifest=json.loads((out/'05_run_manifest.json').read_text(encoding='utf-8'))
                for row in manifest['outputs']:self.assertEqual(row['sha256'],sha(out/row['path']))
                self.assertEqual(len(spec['cross_validation']['model_files']),3)
                with self.assertRaises(FileExistsError):run(root,Path(directory)/'output',SEED)
                (out/'05_4_cv_assignments.csv').write_text('corrupt',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'fingerprint'):verify_outputs(out,self.data,spec)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NestedTests))
    if not result.wasSuccessful():raise RuntimeError('Nested synthetic tests failed; do not use real inputs')



SIMULATION_SCHEMA='sixa-calibration-bundle/1.0'


def object_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def simulation_dependence(data,bundle):
    latent=[]
    for phase in [PHASES[0],PHASES[2]]:
        x,w,_,_=design(data,bundle['transform'],bundle['architecture'],phase)
        model=bundle['models'][phase]
        pit=stats.lognorm.cdf(data[phase],s=np.exp(w@np.array(model['log_sigma_coefficients'])),scale=np.exp(x@np.array(model['location_coefficients'])))
        latent.append(stats.norm.ppf(np.clip(pit,1e-6,1-1e-6)))
    correlation=np.eye(3);correlation[0,2]=correlation[2,0]=float(np.corrcoef(latent)[0,1])
    if not np.isfinite(correlation).all() or np.linalg.eigvalsh(correlation).min()<=0:raise ValueError('Invalid export residual copula')
    return {'kind':'gaussian_copula','phase_order':PHASES,'latent_correlation':correlation.tolist(),
        'scope':'Architecture-specific residual correlation computed from existing fitted marginals, with PIT clipped to [1e-6,1-1e-6]. Integration independent working assumption. No marginal refit or joint OOF validation.'}


def verify_simulation_export(folder):
    manifest=json.loads((folder/'05_export_manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['outputs']:
        if sha(folder/entry['path'])!=entry['sha256']:raise ValueError('Simulation export fingerprint mismatch')
    bundle=json.loads((folder/'05_7_simulation_bundle.json').read_text(encoding='utf-8'))
    if bundle['schema_version']!=SIMULATION_SCHEMA or bundle['reference_model']!='M2' or set(bundle['models'])!={'M1','M2','M4'}:raise ValueError('Simulation model contract mismatch')
    profile=bundle['joint_profiles'];path=folder/profile['path']
    if sha(path)!=profile['sha256']:raise ValueError('Joint profile hash mismatch')
    data=pd.read_csv(path,dtype={'procedure_code':str,ENTITY:str})
    if len(data)!=profile['n'] or data.procedure_code.duplicated().any():raise ValueError('Joint profile count/IDs mismatch')
    if not np.array_equal(classify(data[Q].to_numpy(),bundle['scenarios']['primary']['cuts']),data.asymmetry_scenario.to_numpy()):raise ValueError('Profile scenario mismatch')
    for architecture,b in bundle['models'].items():
        body={k:v for k,v in b.items() if k!='model_sha256'}
        if object_sha(body)!=b['model_sha256']:raise ValueError('Model payload hash mismatch')
        for outcome in [TOTAL,PHASES[0],PHASES[2]]:
            x,w,names,snames=design(data,b['transform'],architecture,outcome);m=b['models'][outcome]
            if names!=m['location_names'] or snames!=m['log_sigma_names']:raise ValueError('Design/coefficient order mismatch')
            for nameskey,valueskey in [('location_names','location_coefficients'),('log_sigma_names','log_sigma_coefficients')]:
                if len(m[nameskey])!=len(m[valueskey]) or not np.isfinite(m[valueskey]).all():raise ValueError('Invalid exported coefficients')
            mu=x@np.array(m['location_coefficients']);sigma=np.exp(w@np.array(m['log_sigma_coefficients']))
            if not np.isfinite(np.exp(mu+.5*sigma**2)).all():raise ValueError('Nonfinite profile prediction')
        matrix=np.array(b['dependence']['latent_correlation'])
        if matrix.shape!=(3,3) or not np.allclose(matrix,matrix.T) or not np.allclose(np.diag(matrix),1) or np.linalg.eigvalsh(matrix).min()<=0:raise ValueError('Invalid model copula')
    return bundle


def export_existing_calibration(project_root,source,output_root):
    """Publish a new, verified consumer bundle without optimizing any marginal.

    The original fitted artifact/code fingerprints are retained separately from
    this export's code fingerprint. Original calibration artifacts stay intact.
    """
    root=Path(project_root).resolve();source=Path(source).resolve();output_root=Path(output_root).resolve()
    output=output_root/'02_results/02_statistical_analysis'
    if output_root==root or output_root==root/'00_data' or (root/'00_data') in output_root.parents:raise ValueError('Use an isolated output root')
    if output.exists() or output.is_symlink():raise FileExistsError('Refusing existing export directory')
    manifest_path=source/'05_run_manifest.json';prior=json.loads(manifest_path.read_text(encoding='utf-8'))
    if prior['status']!='COMPLETE':raise ValueError('Source calibration is incomplete')
    source_hashes={}
    for entry in prior['outputs']:
        file=source/entry['path'];source_hashes[entry['path']]=sha(file)
        if source_hashes[entry['path']]!=entry['sha256']:raise ValueError('Source calibration fingerprint mismatch')
    spec_path=source/'05_3_model_parameters.json';spec=json.loads(spec_path.read_text(encoding='utf-8'))
    if spec.get('selected_architecture')!='M2':raise ValueError('Export requires the approved M2 reference; no reselection')
    data=prepare_covariates(pd.read_csv(source/'05_1_classified_dataset.csv',dtype={'procedure_code':str,ENTITY:str}))
    if len(data)!=spec['training_n'] or data.procedure_code.duplicated().any():raise ValueError('Calibration cohort mismatch')
    if spec['classified_csv_sha256']!=sha(source/'05_1_classified_dataset.csv'):raise ValueError('Source profile fingerprint mismatch')
    protected=protected_hashes(root);source_manifest_hash=sha(manifest_path)
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.05_export_',suffix='.tmp',dir=output.parent))
    try:
        cuts=spec['scenarios']['cuts'];tcuts=spec['sensitivity_scenarios']['tertiles']['cuts']
        columns=['procedure_code',ENTITY,'cv_project_group','cv_dependency_group',GOV,Q,AMOUNT,'source00_notice_date']
        profiles=data[columns].copy();profiles['notice_year']=pd.to_datetime(profiles.source00_notice_date).dt.year
        profiles['asymmetry_scenario']=classify(profiles[Q].to_numpy(),cuts)
        profiles['tertile_sensitivity_scenario']=classify_tertiles(profiles[Q].to_numpy(),tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS'
        profiles['empirical_row_weight']=1./len(profiles)
        profile_path=staging/'05_8_joint_profiles.csv';profiles.to_csv(profile_path,index=False,encoding='utf-8-sig')
        models={}
        for architecture in ['M1','M2','M4']:
            b=json.loads(json.dumps(spec['application_candidates'][architecture]))
            b['schema_version']=SIMULATION_SCHEMA;b['role']='full_cohort_retrospective_reference' if architecture=='M2' else 'full_cohort_comparable_sensitivity'
            b['active_inputs']=[Q]+([GOV] if architecture in ['M2','M4'] else [])+([AMOUNT] if architecture=='M4' else [])
            b['dependence']=spec['dependence'] if architecture=='M2' else simulation_dependence(data,b)
            b['parameter_uncertainty']=spec['parameter_uncertainty'] if architecture=='M2' else {'status':'NOT_EXPORTED_FOR_ALTERNATIVE','scope':'Point-estimate simulation only; do not borrow M2 coefficient uncertainty'}
            # Training IDs remain in the hashed original artifact; consumer profiles
            # retain code/entity/component linkage without duplicating this list.
            b.pop('training_procedure_codes',None)
            b['model_sha256']=object_sha(b);models[architecture]=b
        support=[]
        for (government,scenario),part in profiles.groupby([GOV,'asymmetry_scenario'],sort=True):
            support.append({'government':government,'scenario':scenario,'n':len(part),'entities':part[ENTITY].nunique(),
                'Q_min':int(part[Q].min()),'Q_max':int(part[Q].max()),'procedure_amount_PEN_min':float(part[AMOUNT].min()),
                'procedure_amount_PEN_max':float(part[AMOUNT].max()),'procedure_amount_PEN_median':float(part[AMOUNT].median())})
        result={'schema_version':SIMULATION_SCHEMA,'reference_model':'M2','alternative_models':['M1','M4'],'models':models,
            'provenance':{'calibration_schema_version':spec['schema_version'],'calibration_code_sha256':spec['script_sha256'],
                'export_code_sha256':sha(Path(__file__)),'calibration_parameters_sha256':sha(spec_path),
                'calibration_manifest_sha256':source_manifest_hash,'input_sha256':spec['input_sha256'],
                'source_directory':str(source),'exported_utc':datetime.now(timezone.utc).isoformat(),'seed':spec['seed'],
                'parameter_policy':'Existing application coefficients/transforms copied exactly. No marginal fitting, model selection or cross-validation repeated; only missing alternative residual copulas evaluated.'},
            'scope':{'date_nature':DATE_NATURE,'target':TOTAL,'phase_order':PHASES,'duration_unit':'calendar_days','origin':'query_close',
                'interpretation':spec['interpretation'],'total_policy':'Direct TOTAL marginal and simulated sum of phases are different distributions; do not substitute one for the other.',
                'national_warning':'Sparse national groups; consult original nested grouped validation. No robust national generalization.',
                'FONAFE_warning':'One reference observation; unvalidated training-centered institutional contrast fallback, not a fitted FONAFE effect.'},
            'design_contract':{'location':'mu = ordered location design dot location_coefficients',
                'dispersion':'sigma = exp(ordered log_sigma design dot log_sigma_coefficients); log_sigma is log SD of log duration, not SD in days',
                'Q_standardized_log1p':'(ln(1+Q)-Q_log1p_mean)/Q_log1p_std',
                'procedure_amount_standardized_ln_nominal_PEN':'(ln(procedure_reference_amount_PEN)-amount_log_mean)/amount_log_std',
                'intercept':1.,'log_sigma_intercept':1.,'log_sigma_Q':'same standardized log1p Q',
                'government_regional_centered':'I(GOBIERNO REGIONAL)-training_weight_regional for LOCAL/REGIONAL/NACIONAL; zero for FONAFE',
                'government_national_centered':'I(GOBIERNO NACIONAL)-training_weight_national for LOCAL/REGIONAL/NACIONAL; zero for FONAFE',
                'government_source':GOVTYPE,'allowed_governments':LEVELS+['FONAFE'],'unknown_category':'Reject; no automatic fallback',
                'amount_source':AMOUNT,'amount_unit':'nominal PEN at procedure level, not item or awarded amount; no inflation adjustment',
                'currency_labels':'Soles and Nuevos Soles denote PEN without currency conversion',
                'domain':'Q finite nonnegative integer; amount finite strictly positive; use only active model inputs in design'},
            'simulation_contract':{'random_generator':'numpy.random.default_rng(explicit_user_seed)',
                'joint_phases':'Draw three standard normal scores with the selected model latent_correlation, map with standard normal CDF to uniforms; invert each phase marginal.',
                'positive_phase_quantile':'exp(mu + sigma * standard_normal_ppf(u)); clip u to [1e-12,1-1e-12] for numerical evaluation',
                'integration_quantile':'0 if u<=p_zero; otherwise quantile(positive_values,(u-p_zero)/(1-p_zero),method=inverted_cdf). Constant kind uses value.',
                'discretization':'Continuous fitted day intervals; no implicit rounding or +1; any later rounding rule requires separate validation',
                'uncertainty':'Monte Carlo variation at fixed fitted parameters is not parameter, selection or institutional uncertainty'},
            'scenarios':{'primary':{'cuts':cuts,'interpolation':'linear','rules':{'low':'Q<P25','medium':'P25<=Q<=P75','high':'Q>P75'}},
                'tertiles_sensitivity':{'cuts':tcuts,'rules':{'low':'Q<=P33','medium':'P33<Q<=P67','high':'Q>P67'}}},
            'joint_profiles':{'path':profile_path.name,'sha256':sha(profile_path),'n':len(profiles),'columns':list(profiles.columns),
                'conditional_sampling':'Filter whole observed rows by Q scenario, government and an explicitly declared procedure-amount band; normalize row weights within supported subset and sample complete tuples. Never independently resample Q, government and amount.',
                'fixed_profile':'For a user-specified tuple Q/government/amount, evaluate the conditional marginals directly. Such a hypothetical tuple is not evidence of empirical joint support.',
                'empty_subset':'Return unsupported profile; do not silently widen amount band or borrow another government.',
                'dependence':'Entity, connected-component and related-family linkage retained. Row-weight sampling describes empirical profiles, not independent observations or a cluster bootstrap.',
                'related_families':FAMILIES},
            'empirical_support':{'global_Q_range':[int(profiles[Q].min()),int(profiles[Q].max())],
                'global_procedure_amount_PEN_range':[float(profiles[AMOUNT].min()),float(profiles[AMOUNT].max())],
                'year_range':[int(profiles.notice_year.min()),int(profiles.notice_year.max())],'government_scenario_cells':support,
                'policy':'Flag extrapolation outside observed ranges and sparse/empty conditional cells. Being inside marginal ranges does not establish joint support or generalization.'},
            'limitations':spec['limitations'],'consumer_status':'Complete point-estimate calibration export; SIXA and 06-09 adapters not implemented or validated.'}
        atomic_json(staging/'05_7_simulation_bundle.json',result)
        manifest={'schema_version':SIMULATION_SCHEMA,'status':'COMPLETE','provenance':result['provenance'],
            'protected_files':protected,'outputs':[{'path':f.name,'bytes':f.stat().st_size,'sha256':sha(f)} for f in [staging/'05_7_simulation_bundle.json',profile_path]]}
        atomic_json(staging/'05_export_manifest.json',manifest);verify_simulation_export(staging)
        if protected_hashes(root)!=protected or sha(manifest_path)!=source_manifest_hash or any(sha(source/name)!=value for name,value in source_hashes.items()):raise ValueError('Source/protected files changed during export')
        if output.exists():raise FileExistsError('Export target appeared')
        staging.rename(output)
        print(f'EXPORT COMPLETE | no marginal refitting | {output}')
        return output
    except Exception:
        if staging.exists() and not staging.is_symlink() and staging.resolve().parent==output.parent.resolve() and staging.name.startswith('.05_export_'):shutil.rmtree(staging)
        raise



def run_export_tests():
    import unittest
    import contextlib
    import io
    from unittest import mock
    def fixture(root):
        folder=root/'calibration';folder.mkdir();(root/'00_data').mkdir();(root/'02_results/01_sample_and_data').mkdir(parents=True)
        rng=np.random.default_rng(6001);n=120;q=rng.integers(0,100,n);a=np.exp(rng.normal(16,.6,n))
        g=[LEVELS[0]]*40+[LEVELS[1]]*40+[LEVELS[2]]*39+['FONAFE']
        p1=np.maximum(1,np.round(np.exp(2+.15*np.log1p(q)+rng.normal(0,.4,n))));p3=np.maximum(1,np.round(np.exp(2.8+.1*np.log1p(q)+rng.normal(0,.4,n))));p2=np.zeros(n);p2[[20,65,98,107]]=[1,2,2,8]
        d=prepare_covariates(pd.DataFrame({'procedure_code':[str(500000+i) for i in range(n)],Q:q,AMOUNT:a,GOVTYPE:g,PHASES[0]:p1,PHASES[1]:p2,PHASES[2]:p3,TOTAL:p1+p2+p3,
            ENTITY:['E'+str(i) for i in range(n)],'cv_project_group':['P'+str(i) for i in range(n)],'cv_dependency_group':['D'+str(i) for i in range(n)],'source00_notice_date':['2020-01-01']*n}))
        file=folder/'05_1_classified_dataset.csv';d.to_csv(file,index=False)
        apps={m:cov_bundle(d,m) for m in ['M1','M2','M4']}
        spec={'selected_architecture':'M2','training_n':n,'schema_version':VERSION,'script_sha256':'synthetic-fitting-code','seed':SEED,'input_sha256':'synthetic-input',
            'classified_csv_sha256':sha(file),'application_candidates':apps,'scenarios':{'cuts':scenario_cuts(d)},'sensitivity_scenarios':{'tertiles':{'cuts':tertile_cuts(d)}},
            'parameter_uncertainty':{'status':'SYNTHETIC_ONLY'},'dependence':simulation_dependence(d,apps['M2']),'interpretation':'Synthetic retrospective schedules','limitations':['Synthetic only']}
        atomic_json(folder/'05_3_model_parameters.json',spec)
        atomic_json(folder/'05_run_manifest.json',{'status':'COMPLETE','outputs':[{'path':f.name,'sha256':sha(f)} for f in [file,folder/'05_3_model_parameters.json']]})
        return d,spec,folder
    class ExportTests(unittest.TestCase):
        def test_exact_parameters_joint_profiles_no_refit_and_corruption(self):
            with tempfile.TemporaryDirectory(prefix='export05_') as temporary:
                root=Path(temporary);data,spec,source=fixture(root)
                before={p.name:sha(p) for p in source.iterdir()}
                with mock.patch.object(optimize,'minimize',side_effect=AssertionError('Export must not fit')):
                    with contextlib.redirect_stdout(io.StringIO()):out=export_existing_calibration(root,source,root/'export')
                b=verify_simulation_export(out)
                for m in ['M1','M2','M4']:
                    self.assertEqual(b['models'][m]['models'],spec['application_candidates'][m]['models'])
                    self.assertEqual(b['models'][m]['transform'],spec['application_candidates'][m]['transform'])
                self.assertEqual(b['models']['M2']['dependence'],spec['dependence'])
                self.assertEqual(before,{p.name:sha(p) for p in source.iterdir()})
                profiles=pd.read_csv(out/'05_8_joint_profiles.csv',dtype={'procedure_code':str})
                for col in [Q,AMOUNT]:np.testing.assert_allclose(data[col],profiles[col])
                self.assertEqual(data[GOV].tolist(),profiles[GOV].tolist())
                self.assertEqual(int(profiles[GOV].eq('FONAFE').sum()),1)
                with self.assertRaises(FileExistsError):export_existing_calibration(root,source,root/'export')
                (out/'05_8_joint_profiles.csv').write_text('corrupt',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'fingerprint'):verify_simulation_export(out)
        def test_M4_uses_amount_from_exported_coefficients(self):
            with tempfile.TemporaryDirectory(prefix='export05_') as temporary:
                root=Path(temporary);data,spec,source=fixture(root)
                with contextlib.redirect_stdout(io.StringIO()):out=export_existing_calibration(root,source,root/'export')
                b=verify_simulation_export(out);profile=data.iloc[[0]].copy();changed=profile.copy();changed[AMOUNT]*=2
                for m in ['M1','M2']:
                    np.testing.assert_allclose(cov_forecast(profile,b['models'][m],TOTAL)['median'],cov_forecast(changed,b['models'][m],TOTAL)['median'])
                model=b['models']['M4'];coef=model['models'][TOTAL]['location_coefficients'][-1]
                ratio=cov_forecast(changed,model,TOTAL)['median']/cov_forecast(profile,model,TOTAL)['median']
                np.testing.assert_allclose(ratio,np.exp(coef*np.log(2)/model['transform']['amount_log_std']))
                self.assertNotEqual(float(ratio[0]),1.)
        def test_corrupt_source_refused_without_publication(self):
            with tempfile.TemporaryDirectory(prefix='export05_') as temporary:
                root=Path(temporary);_,_,source=fixture(root);(source/'05_3_model_parameters.json').write_text('corrupt',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'Source calibration fingerprint'):export_existing_calibration(root,source,root/'export')
                self.assertFalse((root/'export').exists())
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExportTests))
    if not result.wasSuccessful():raise RuntimeError('Simulation export tests failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path)
    parser.add_argument('--output-root',type=Path,help='Required fresh independent output root')
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--export-existing-calibration',type=Path,help='Verified existing calibration directory; export M1/M2/M4 without marginal refitting')
    args=parser.parse_args()
    if args.self_test:
        run_self_tests()
        return run_export_tests()
    if args.output_root is None: parser.error('--output-root is required; existing results are never replaced')
    root=args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()),None)
    if root is None: parser.error('Project root not located; use --project-root')
    if args.export_existing_calibration is not None:
        return export_existing_calibration(root,args.export_existing_calibration,args.output_root)
    run(root,args.output_root,args.seed)


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'CALIBRATION FAILED: {type(exc).__name__}: {exc}',file=sys.stderr); sys.exit(1)
