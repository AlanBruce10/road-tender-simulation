"""Define Q scenarios and calibrate conditional duration models for Script 06.

Uses Script 03's eligible cohort only. No imputation or additional exclusions.
Primary scenarios: Q<P25, P25<=Q<=P75, Q>P75. Tertiles: sensitivity only.
Five reproducible project-grouped folds cover all eligible procedures.
Each fold is calibrated on its training complement; a separate final fit uses all rows.
Dependencies: pandas numpy scipy openpyxl. No API or SEACE connection required.
"""
import argparse
import hashlib
import json
import platform
import re
import shutil
import unicodedata
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import optimize, stats

VERSION='2.1-P25-P75-primary-tertiles-sensitivity'
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
    required={'procedure_code',Q,TOTAL,*PHASES,*BOUNDARIES,'source00_notice_date','eligible_common_model','date_nature'}
    if required-set(df):raise ValueError(f'Missing Script 03 columns: {sorted(required-set(df))}')
    df['procedure_code']=df.procedure_code.astype(str).str.strip().str.replace(r'\.0$','',regex=True)
    if not df.procedure_code.str.fullmatch(r'\d+').all() or df.procedure_code.duplicated().any():
        raise ValueError('Missing/invalid/duplicate procedure codes')
    if not boolean(df.eligible_common_model).all() or not df.date_nature.eq(DATE_NATURE).all():
        raise ValueError('Use the eligible published-schedule dataset from Script 03')
    for col in [Q,TOTAL]+PHASES:
        df[col]=pd.to_numeric(df[col],errors='coerce')
        if not np.isfinite(df[col]).all() or (df[col]<0).any():raise ValueError(f'Invalid values: {col}')
    if df[Q].mod(1).ne(0).any():raise ValueError('Q must be an integer count')
    if df[TOTAL].le(0).any():raise ValueError('The current positive-total model requires T>0; no records silently discarded')
    if not np.allclose(df[PHASES].sum(axis=1),df[TOTAL],rtol=0,atol=0):raise ValueError('Phase sum differs from post-query-close total')
    for col in BOUNDARIES+['source00_notice_date']:
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
            result=optimize.minimize(objective,initial[indices],method='L-BFGS-B',
                                     bounds=[bounds_all[i] for i in indices],options={'maxiter':2000,'ftol':1e-11})
            beta=np.zeros(4);beta[indices]=result.x
            ll=-objective(result.x);k=len(indices)
            hit_bound=any(abs(v-lo)<1e-5 or abs(v-hi)<1e-5 for v,(lo,hi) in zip(result.x,[bounds_all[i] for i in indices]))
            accepted=bool(result.success and np.isfinite(ll) and ll>-1e90 and not hit_bound)
            row={'outcome':outcome,'family':family,'structure':structure,'positive_n':len(y),
                 'converged':bool(result.success),'boundary_solution':hit_bound,'accepted':accepted,
                 'log_likelihood':ll,'parameters':k,'AIC':2*k-2*ll,'BIC':np.log(len(y))*k-2*ll,
                 'optimizer_message':str(result.message)}
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


def fit_dependence(train,z,models):
    # Sparse/constant phases are explicitly independent in the working copula.
    active=[i for i,p in enumerate(PHASES) if models[p]['kind']=='parametric_positive_with_zero_mass']
    corr=np.eye(len(PHASES));rng=np.random.default_rng(SEED)
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
            'seed_for_zero_mass_PIT':SEED}


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


def assign_folds(data,nfolds=5):
    result=data.copy()
    grouping=[project_group(row) for row in result.to_dict('records')]
    result['cv_project_group']=[v[0] for v in grouping]
    result['cv_group_basis']=[v[1] for v in grouping]
    sizes=result.cv_project_group.value_counts().sort_index()
    if len(sizes)<nfolds:raise ValueError('Too few distinct project groups for five folds')
    rng=np.random.default_rng(SEED)
    # Assign larger groups first; seeded tie-breaking, independent of outcomes.
    ranked=pd.DataFrame({'group':sizes.index,'size':sizes.values,'tie':rng.random(len(sizes))})
    ranked=ranked.sort_values(['size','tie'],ascending=[False,True])
    totals=np.zeros(nfolds,dtype=int);mapping={}
    for row in ranked.itertuples(index=False):
        options=np.flatnonzero(totals==totals.min());fold=int(rng.choice(options))
        mapping[row.group]=fold+1;totals[fold]+=row.size
    result['cv_fold']=result.cv_project_group.map(mapping).astype(int)
    if result.groupby('cv_project_group').cv_fold.nunique().max()!=1:
        raise RuntimeError('Project group crossed validation folds')
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
    return cuts


def calibrate(training,fit_id):
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
            'models':models,'no_Q_benchmarks':baselines,'dependence':fit_dependence(training,z,models)}
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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path)
    args=parser.parse_args()
    root=args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()),None)
    if root is None:parser.error('Project root not located; use --project-root PATH')
    source=root/'02_results'/'01_sample_and_data'/'03_2_model_ready_dataset.xlsx'
    output=root/'02_results'/'02_statistical_analysis';logs=root/'03_logs'/'02_statistical_analysis'
    output.mkdir(parents=True,exist_ok=True);logs.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    logfile=logs/f'05_scenarios_and_calibration_{stamp}.log'
    try:
        input_hash=sha(source);script_hash=sha(Path(__file__))
        data=validate(pd.read_excel(source,dtype={'procedure_code':str})).sort_values('procedure_code').reset_index(drop=True)
        data=assign_folds(data)
        log(f'SCENARIOS AND CALIBRATION | {VERSION} | eligible={len(data)}')
        log('All study years retained; five project-grouped folds; no fixed 2025 holdout')
        candidates=[];marginal_audit=[];fold_bundles=[];fold_rows=[]
        data['scenario_out_of_fold']=''
        data['tertile_sensitivity_out_of_fold']=''
        data['cv_Q_outside_training_range']=False
        for fold in range(1,6):
            mask=data.cv_fold.eq(fold);training=data.loc[~mask].copy();heldout=data.loc[mask].copy()
            if set(training.cv_project_group)&set(heldout.cv_project_group):raise RuntimeError('Project leakage between training and validation')
            log(f'Fold {fold}/5: calibrating {len(training)} | reserved for validation {len(heldout)}')
            bundle,rows=calibrate(training,f'fold_{fold:02d}')
            bundle.update(schema_version=VERSION,artifact_role='cross_validation_training_fit',fold=fold,
                          input_sha256=input_hash,script_sha256=script_hash,
                          validation_procedure_codes=sorted(heldout.procedure_code.tolist()),
                          validation_n=len(heldout),date_nature=DATE_NATURE,target=TOTAL,
                          phase_order=PHASES,duration_unit='calendar_days',origin='query_close')
            data.loc[mask,'scenario_out_of_fold']=classify(heldout[Q].to_numpy(),bundle['scenarios']['cuts'])
            tcuts=bundle['sensitivity_scenarios']['tertiles']['cuts']
            data.loc[mask,'tertile_sensitivity_out_of_fold']=(classify_tertiles(heldout[Q].to_numpy(),tcuts) if tcuts else 'NOT_ESTIMABLE_TIED_CUTS')
            lo,hi=bundle['training_Q_range']
            data.loc[mask,'cv_Q_outside_training_range']=heldout[Q].lt(lo)|heldout[Q].gt(hi)
            fold_rows.append({'fold':fold,'training_n':len(training),'validation_n':len(heldout),
                              'training_project_groups':training.cv_project_group.nunique(),
                              'validation_project_groups':heldout.cv_project_group.nunique(),
                              'primary_P25':bundle['scenarios']['cuts'][0],'primary_P75':bundle['scenarios']['cuts'][1],
                              'sensitivity_P33':tcuts[0] if tcuts else None,'sensitivity_P67':tcuts[1] if tcuts else None,
                              'validation_Q_outside_training_range':int(data.loc[mask,'cv_Q_outside_training_range'].sum())})
            candidates.extend(rows);marginal_audit.extend(audit_marginals(training,bundle));fold_bundles.append(bundle)
        if data.scenario_out_of_fold.eq('').any() or sum(b['validation_n'] for b in fold_bundles)!=len(data):
            raise RuntimeError('Cross-validation coverage incomplete')
        log(f'Final application fit: calibrating all {len(data)} procedures')
        final,rows=calibrate(data,'full_cohort_application_fit')
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
            'cross_validation':{'kind':'seeded_group_balanced_5_fold','seed':SEED,'folds':5,'all_procedures_n':len(data),
                                'grouping':'Explicit unambiguous CUI; otherwise exact normalized entity+description; procedure code fallback',
                                'scope':'New procedures/projects from the pooled 2020-2025 cohort; not future-year or unseen-entity performance',
                                'limitations':'Project detection is conservative exact linkage, not guaranteed full project resolution. Entities may occur in multiple folds. Full cohort previously explored by Script 04.',
                                'validation_rule':'Use only the fold model excluding each procedure/project for out-of-fold predictions; never validate with this full-cohort fit',
                                'scenario_rule':'Primary and sensitivity out-of-fold scenarios use training-only cuts; final application labels use full-cohort cuts'},
            'hypothesis_contract':{'primary_groups':'Q < P25 versus Q > P75; boundaries assigned to medium',
                'H1':'sigma_high > sigma_low','H0':'sigma_high <= sigma_low','alpha':0.05,
                'outcome':TOTAL,'evidence':'Observed eligible procedure durations, not simulated replicas as additional evidence',
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
            'selection':'Minimum BIC among converged interior positive-duration candidate fits, within each training set separately. No held-out outcome used for candidate selection.',
            'limitations':['Positive continuous marginals approximate integer calendar days; rounding/ties require explicit handling in validation.',
                           'Zero probability constant in Q. Sparse positive phases use empirical values; their Q relationship and unobserved tails are not estimated.',
                           'Residual copula constant across Q; sparse phases assumed independent; assumptions require sensitivity assessment.',
                           'No causal effect, superiority of DES, actual-event accuracy or predictive adequacy established by calibration.'],
            'minimum_positive_parametric_sample':MIN_POSITIVE,
            'versions':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'scipy':scipy.__version__}}
        notes=pd.DataFrame([
            ('population','Every eligible procedure remains in classification and participates once as validation and four times as training in five-fold CV.'),
            ('final_fit','Uses the entire eligible cohort for subsequent application. Its fitted values are not out-of-fold validation results.'),
            ('folds','Seeded project-group-balanced allocation using identifiers/descriptions and group sizes only, never outcomes.'),
            ('grouping_limit','Explicit CUI or exact entity-description grouping reduces recognizable repeats; it does not identify all related projects or separate all entities.'),
            ('scenario_method','PRIMARY: linear-interpolated P25/P75 of Q; low Q<P25, high Q>P75, medium includes boundaries. Equal-Q values remain together.'),
            ('sensitivity_method','SENSITIVITY ONLY: previous nearest-rank tertiles with low <=P33 and high >P67. Same conditional-Q models; alternative aggregation, not another primary hypothesis.'),
            ('hypothesis_contrast','Direction is higher observed-duration SD in high versus low Q. No dispersion hypothesis p-value or validation conclusion is calculated here.'),
            ('scenario_validation','Use scenario_out_of_fold for out-of-fold scenario validation; asymmetry_scenario is the final full-cohort classification.'),
            ('model_horizon','Query CLOSE to award END, partitioned into three nonoverlapping blocks. Formulation duration is outside this target.'),
            ('zero_days','Both dates can be complete and equal. Such intervals are observed zeros, not missing values.'),
            ('phase_model','Blocks include waiting between events; no individual query handling times, resource capacities or queues inferred.'),
            ('selection','Training-only positive-component BIC comparison of lognormal/Weibull and no-Q/location-Q/location-and-shape-Q structures.'),
            ('sparse_safeguard',f'Fewer than {MIN_POSITIVE} positive cases or three distinct positive values triggers empirical positives; numerical safeguard, not case exclusion.'),
            ('scope','Calibration artifacts only; simulation in 06 and out-of-fold predictive assessment in 07.'),
            ('leakage','Cuts, Q standardization, zero masses, marginal candidates and residual dependence re-estimated from training data for every fold.'),
            ('validation_limit','Grouped pooled-cohort CV does not establish future-year performance. Earlier whole-cohort exploration prevents claiming a wholly untouched external test.'),
        ],columns=['item','description'])
        if sha(source)!=input_hash:raise RuntimeError('Input changed during calibration; no outputs replaced')
        # Preserve previous artifacts automatically, including superseded year-holdout runs.
        names=['05_1_classified_dataset.xlsx','05_1_classified_dataset.csv','05_2_calibration_audit.xlsx',
               '05_3_model_parameters.json','05_4_cv_assignments.csv','05_cv_models']
        old=[output/name for name in names if (output/name).exists()]
        if old:
            backup=output/'previous_runs'/f'05_{stamp}';backup.mkdir(parents=True)
            for path in old:shutil.move(str(path),str(backup/path.name))
            log(f'Previous calibration artifacts backed up: {backup}')
        cv_dir=output/'05_cv_models';cv_dir.mkdir(exist_ok=True)
        manifest=[]
        for bundle in fold_bundles:
            path=cv_dir/f"fold_{bundle['fold']:02d}.json";atomic_json(path,bundle)
            manifest.append({'fold':bundle['fold'],'path':str(path.relative_to(output)).replace('\\','/'),'sha256':sha(path),
                             'training_n':bundle['training_n'],'validation_n':bundle['validation_n']})
        spec['cross_validation']['model_files']=manifest
        csv=output/'05_1_classified_dataset.csv';temp=csv.with_suffix('.tmp.csv')
        data.to_csv(temp,index=False,encoding='utf-8-sig');temp.replace(csv)
        assignments=data[['procedure_code','cv_project_group','cv_group_basis','cv_fold','scenario_out_of_fold','asymmetry_scenario','tertile_sensitivity_out_of_fold','tertile_sensitivity_scenario','cv_Q_outside_training_range']]
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
            'definitions':notes,'cv_model_manifest':pd.DataFrame(manifest)})
        atomic_json(output/'05_3_model_parameters.json',spec)
        log(f'COMPLETE | classified={len(data)} | out-of-fold coverage={len(data)}/{len(data)} | final fit={len(data)}')
        log(f'Verified Q=0 retained: {int(data[Q].eq(0).sum())}')
        log('No procedures removed. CV predictions must use fold models; full fit is for application.')
        log(f'Parameters and CV artifacts: {output}')
    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}');raise
    finally:logfile.write_text('\n'.join(LOG)+'\n',encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception:sys.exit(1)
