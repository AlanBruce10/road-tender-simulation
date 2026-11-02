"""Exploratory analysis of the common eligible Script 03 cohort.
The full Script 03 dataset is retained unchanged. Related-record exclusions occur
only in explicitly labeled sensitivity views, never in the baseline or source.
Spearman is primary; entity-cluster percentile bootstrap intervals are exploratory.
IID p-values remain for compatibility and are not used for dependence-aware claims.
Use --output-root for a fresh isolated output root, or --self-test for synthetic tests.
No scenarios, imputation, distribution fitting or causal interpretation is introduced.
Run: python 04_exploratory_analysis.py
Dependencies: pandas numpy scipy openpyxl matplotlib.
"""
import argparse
import hashlib
import json
import sys
import warnings
import itertools
import importlib.metadata
import math
import shutil
import tempfile
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VERSION = '2.1-clustered-exploration-and-family-sensitivity'
Q = 'queries_observations_count'
TOTAL = 'query_to_award_calendar_days'
CLOSE_TOTAL = 'query_close_to_award_calendar_days'
STAGES = ['query', 'absolution', 'integration', 'offers', 'evaluation', 'award']
BOUNDARIES = [f'{stage}_{edge}' for stage in STAGES for edge in ('start', 'end')]
INTERVALS = [(f'{a}_to_{b}_calendar_days', a, b) for a,b in zip(BOUNDARIES,BOUNDARIES[1:])]
AGGREGATES = ['absolution_calendar_days','integration_calendar_days','post_integration_calendar_days']
TIME_VARIABLES = [TOTAL,CLOSE_TOTAL] + AGGREGATES + [x[0] for x in INTERVALS]
LOG_LINES = []


def log(message=''):
    print(message,flush=True)
    LOG_LINES.append(str(message))


def truth(series):
    return series.astype(str).str.strip().str.lower().isin(['true','1','1.0'])


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe_cv(series):
    """
    Coefficient of variation = standard deviation / mean.

    Returns NaN when the mean is zero or undefined.
    """
    x = pd.to_numeric(series, errors="coerce").dropna()

    if len(x) < 2:
        return np.nan

    mean = x.mean()

    if np.isclose(mean, 0):
        return np.nan

    return x.std(ddof=1) / mean


def descriptive_statistics(df, variables):
    """
    Calculate descriptive statistics without modifying observations.
    """
    rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce").dropna()

        n = len(x)
        missing = int(pd.to_numeric(df[variable], errors="coerce").isna().sum())

        if n == 0:
            rows.append({
                "variable": variable,
                "n": 0,
                "missing": missing,
            })
            continue

        q1 = x.quantile(0.25)
        median = x.quantile(0.50)
        q3 = x.quantile(0.75)
        iqr = q3 - q1

        rows.append({
            "variable": variable,
            "n": n,
            "missing": int(missing),
            "mean": x.mean(),
            "median": median,
            "std_dev": x.std(ddof=1) if n > 1 else np.nan,
            "variance": x.var(ddof=1) if n > 1 else np.nan,
            "coefficient_of_variation": safe_cv(x),
            "minimum": x.min(),
            "p25": q1,
            "p50": median,
            "p75": q3,
            "maximum": x.max(),
            "iqr": iqr,
            "p05": x.quantile(.05), "p10": x.quantile(.1),
            "p90": x.quantile(.9), "p95": x.quantile(.95), "p99": x.quantile(.99),
            "skewness": stats.skew(
                x,
                bias=False,
                nan_policy="omit"
            ) if n >= 3 and x.nunique() > 1 else np.nan,
            "excess_kurtosis": stats.kurtosis(
                x,
                fisher=True,
                bias=False,
                nan_policy="omit"
            ) if n >= 4 and x.nunique() > 1 else np.nan,
        })

    return pd.DataFrame(rows)


def iqr_outlier_diagnostics(df, variables):
    """
    Flag observations outside the conventional 1.5*IQR limits.

    Important:
    This is a diagnostic only. No observation is removed.
    """
    summary_rows = []
    detail_rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce")

        valid = x.dropna()

        if valid.empty:
            continue

        q1 = valid.quantile(0.25)
        q3 = valid.quantile(0.75)
        iqr = q3 - q1

        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        mask = (x < lower_bound) | (x > upper_bound)
        outlier_count = int(mask.fillna(False).sum())

        summary_rows.append({
            "variable": variable,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "outlier_count": outlier_count,
            "outlier_percent": (
                100 * outlier_count / len(valid)
                if len(valid) > 0
                else np.nan
            ),
        })

        selected_columns = [
            "procedure_code",
            "procedure_description",
            variable,
        ]

        flagged = df.loc[
            mask.fillna(False),
            selected_columns
        ].copy()

        if not flagged.empty:
            flagged.insert(2, "variable", variable)
            flagged = flagged.rename(columns={variable: "observed_value"})
            flagged["lower_bound"] = lower_bound
            flagged["upper_bound"] = upper_bound

            detail_rows.append(flagged)

    summary = pd.DataFrame(summary_rows)

    if detail_rows:
        details = pd.concat(detail_rows, ignore_index=True)
    else:
        details = pd.DataFrame(
            columns=[
                "procedure_code",
                "procedure_description",
                "variable",
                "observed_value",
                "lower_bound",
                "upper_bound",
            ]
        )

    return summary, details


def normality_diagnostics(df, variables):
    """Do not test a continuous IID normal null on discrete clustered records.

    Keep the legacy sheet/columns, distinguish constant/insufficient/count data,
    and describe shape rather than use Shapiro as a distribution-selection rule.
    """
    rows=[]
    for variable in variables:
        x=pd.to_numeric(df[variable],errors='coerce').dropna()
        status=('INSUFFICIENT_DATA' if len(x)<3 else 'CONSTANT_VARIABLE' if x.nunique()<2
                else 'NOT_APPLICABLE_DISCRETE_COUNT' if variable==Q
                else 'NOT_TESTED_DISCRETE_DAYS_AND_CLUSTERING')
        rows.append({'variable':variable,'n':len(x),'shapiro_w':np.nan,'shapiro_p_value':np.nan,
                     'interpretation_alpha_0_05':status,'unique_values':x.nunique(),
                     'zero_percent':100*x.eq(0).mean() if len(x) else np.nan})
    return pd.DataFrame(rows)


def association_analysis(df):
    """
    Evaluate bivariate association between query/observation counts
    and each duration variable using Pearson and Spearman correlations.

    Pearson:
        linear association.

    Spearman:
        monotonic rank-based association, less dependent on normality.

    No causal interpretation is made here.
    """
    predictor = "queries_observations_count"
    rows = []

    for outcome in TIME_VARIABLES:
        pair = df[[predictor, outcome]].dropna()

        x = pair[predictor].astype(float)
        y = pair[outcome].astype(float)

        n = len(pair)

        if n < 3 or x.nunique() < 2 or y.nunique() < 2:
            rows.append({
                "predictor": predictor,
                "outcome": outcome,
                "n": n,
                "pearson_r": np.nan,
                "pearson_p_value": np.nan,
                "spearman_rho": np.nan,
                "spearman_p_value": np.nan,
            })
            continue

        pearson_r, pearson_p = stats.pearsonr(x, y)
        spearman_rho, spearman_p = stats.spearmanr(x, y)

        rows.append({
            "predictor": predictor,
            "outcome": outcome,
            "n": n,
            "pearson_r": pearson_r,
            "pearson_p_value": pearson_p,
            "spearman_rho": spearman_rho,
            "spearman_p_value": spearman_p,
        })

    return pd.DataFrame(rows)


def bh_adjust(values):
    p=np.asarray(values,dtype=float)
    adjusted=np.full(len(p),np.nan)
    valid=np.flatnonzero(np.isfinite(p))
    order=valid[np.argsort(p[valid])]
    if len(order):
        ranked=p[order]*len(order)/np.arange(1,len(order)+1)
        adjusted[order]=np.minimum(1,np.minimum.accumulate(ranked[::-1])[::-1])
    return adjusted


def correlation_table(df,variables):
    # Excludes aggregate outcomes to avoid part/whole correlations in stage dependence.
    return df[variables].corr(method='spearman').rename_axis('variable').reset_index()


def profile(df, group):
    rows=[]
    for label,g in df.groupby(group,observed=True,dropna=False):
        for outcome in (TOTAL,CLOSE_TOTAL):
            t=g[outcome]
            rows.append({'group_variable':group,'group':str(label),'outcome':outcome,'n':len(g),
                         'Q_min':g[Q].min(),'Q_max':g[Q].max(),'Q_median':g[Q].median(),
                         'mean':t.mean(),'median':t.median(),'std_dev':t.std(ddof=1),
                         'p25':t.quantile(.25),'p75':t.quantile(.75),'p90':t.quantile(.9),
                         'iqr':t.quantile(.75)-t.quantile(.25),'minimum':t.min(),'maximum':t.max()})
    return pd.DataFrame(rows)


def exploratory_bands(df):
    # Positive-Q quartiles are diagnostic summaries, NOT low/medium/high scenarios.
    # Equal Q values remain together; tied cutpoints can produce fewer than four bands.
    group=pd.Series('Q=0',index=df.index,dtype=object)
    mask=df[Q]>0
    if mask.any():
        if df.loc[mask,Q].nunique()==1:
            group.loc[mask]='positive_Q_constant'
        else:
            bins=pd.qcut(df.loc[mask,Q],4,duplicates='drop')
            group.loc[mask]=bins.astype(str).to_numpy()
    temp=df.copy();temp['diagnostic_Q_band']=group
    result=profile(temp,'diagnostic_Q_band')
    return result.sort_values(['Q_min','outcome'],kind='stable').reset_index(drop=True)


def covariance_diagnostic(df):
    columns=[x[0] for x in INTERVALS]
    covariance=df[columns].cov()
    marginal=float(np.trace(covariance.to_numpy()))
    totalvar=float(df[TOTAL].var(ddof=1))
    contribution=float(covariance.to_numpy().sum()-marginal)
    return pd.DataFrame([
        {'metric':'variance_of_total','value':totalvar},
        {'metric':'sum_of_interval_variances','value':marginal},
        {'metric':'twice_sum_of_pairwise_covariances','value':contribution},
        {'metric':'variance_identity_residual','value':totalvar-marginal-contribution},
        {'metric':'independence_based_sd','value':np.sqrt(marginal)},
        {'metric':'observed_total_sd','value':np.sqrt(totalvar)},
    ]),covariance.rename_axis('variable').reset_index()


def save_workbook(path,sheets):
    temp=path.with_suffix('.tmp.xlsx')
    with pd.ExcelWriter(temp,engine='openpyxl') as writer:
        for name,frame in sheets.items():
            frame.to_excel(writer,sheet_name=name,index=False)
            sheet=writer.sheets[name];sheet.freeze_panes='B2'
            if len(frame.columns):sheet.auto_filter.ref=sheet.dimensions
    try:temp.replace(path)
    except PermissionError as exc:raise PermissionError(f'Close {path.name} in Excel and rerun') from exc


def validate(df):
    required=['procedure_code',Q,'eligible_common_model','date_nature','source02_count_status']
    required += TIME_VARIABLES + ['schedule_'+b+'_date' for b in BOUNDARIES]
    missing=sorted(set(required)-set(df.columns))
    if missing:raise ValueError(f'Script 03 eligible output missing columns: {missing}')
    if len(df)<3:raise ValueError('At least three eligible procedures are required')
    if df.procedure_code.isna().any() or df.procedure_code.duplicated().any():
        raise ValueError('Missing or duplicate procedure_code')
    checks=[]
    def add(label,mask):
        failures=int(pd.Series(mask,index=df.index).fillna(True).sum())
        checks.append({'check':label,'failures':failures,'status':'FAIL' if failures else 'PASS'})
    add('all_rows_eligible',~truth(df.eligible_common_model))
    add('published_schedule_date_nature',df.date_nature.ne('published_schedule_not_verified_actual_events'))
    add('count_status_OK',df.source02_count_status.ne('OK'))
    for v in [Q]+TIME_VARIABLES:
        df[v]=pd.to_numeric(df[v],errors='coerce')
        add('finite_nonnegative_'+v,~np.isfinite(df[v]) | df[v].lt(0))
    add('integer_Q',df[Q].mod(1).ne(0))
    for b in BOUNDARIES:
        col='schedule_'+b+'_date'
        df[col]=pd.to_datetime(df[col],errors='coerce').dt.normalize()
        add('complete_'+b,df[col].isna())
    for name,a,b in INTERVALS:
        expected=(df['schedule_'+b+'_date']-df['schedule_'+a+'_date']).dt.days
        add('date_arithmetic_'+name,~np.isclose(df[name],expected,rtol=0,atol=0))
    spans=[(TOTAL,'query_start','award_end'),(CLOSE_TOTAL,'query_end','award_end'),
           ('absolution_calendar_days','query_end','absolution_end'),
           ('integration_calendar_days','absolution_end','integration_end'),
           ('post_integration_calendar_days','integration_end','award_end')]
    for name,a,b in spans:
        expected=(df['schedule_'+b+'_date']-df['schedule_'+a+'_date']).dt.days
        add('date_arithmetic_'+name,~np.isclose(df[name],expected,rtol=0,atol=0))
    summed=df[[i[0] for i in INTERVALS]].sum(axis=1,min_count=len(INTERVALS))
    add('interval_sum_matches_total',~np.isclose(summed,df[TOTAL],rtol=0,atol=0))
    return pd.DataFrame(checks)


# Fixed documentary families: the base unit remains the published code-level
# record. These views are not a definitive deduplication or a new scope filter.
FAMILIES = [('COMAS_RESTART', '811044', '848861'),
            ('OLMOS_ITEMS_RESTART', '995451', '1058629')]
ENTITY = 'source00_entity_code'
MAIN_OUTCOMES = [TOTAL, CLOSE_TOTAL]
SEED = 20261101
BOOTSTRAP_REPS = 2000
MIN_GROUP_N = 20
REPORTING_LIMITS = {'mean_or_sd_relative_percent':1.0, 'quantile_absolute_units':1.0,
                    'correlation_absolute_change':0.02}


def analysis_contract(df):
    required=['procedure_code',Q,ENTITY,'source00_notice_date','duration_unit','modeled_origin',
              'observed_actual_event_dates_verified','source02_queries_observations_count']
    missing=sorted(set(required)-set(df))
    if missing: raise ValueError(f'Missing analysis context columns: {missing}')
    ids=df.procedure_code.astype('string')
    if ids.isna().any() or ids.str.strip().eq('').any() or not ids.eq(ids.str.strip()).all():
        raise ValueError('Empty or whitespace-padded procedure identifiers')
    # Numeric source cells are not accepted as timestamps by pandas inference.
    for boundary in BOUNDARIES:
        col='schedule_'+boundary+'_date'
        if col not in df: raise ValueError(f'Missing boundary: {col}')
        if df[col].dropna().map(lambda x:isinstance(x,(int,float,np.number))).any():
            raise ValueError(f'Numeric date cell requires explicit upstream resolution: {col}')
    checks=validate(df)
    extra=[]
    def add(name,mask):
        n=int(pd.Series(mask,index=df.index).fillna(True).sum())
        extra.append({'check':name,'failures':n,'status':'FAIL' if n else 'PASS'})
    add('calendar_day_unit',df.duration_unit.ne('calendar_days'))
    add('published_start_origin',df.modeled_origin.ne('query_formulation_start'))
    add('actual_events_not_verified',df.observed_actual_event_dates_verified.astype(str).str.lower().ne('false'))
    add('Q_matches_count_source',~np.isclose(df[Q],pd.to_numeric(df.source02_queries_observations_count,errors='coerce'),rtol=0,atol=0))
    add('entity_code_available',df[ENTITY].isna() | df[ENTITY].astype(str).str.strip().eq(''))
    for col in [c for c in df if c.startswith('qc_')]: add('upstream_'+col,~truth(df[col]))
    return pd.concat([checks,pd.DataFrame(extra)],ignore_index=True)


def variable_dictionary():
    rows=[{'variable':Q,'start':'','end':'','unit':'numbered_document_records',
           'meaning':'Combined consultation/observation records, not separate question counts or a validated information-asymmetry construct'}]
    spans=[(TOTAL,'query_start','award_end'),(CLOSE_TOTAL,'query_end','award_end'),
           ('absolution_calendar_days','query_end','absolution_end'),
           ('integration_calendar_days','absolution_end','integration_end'),
           ('post_integration_calendar_days','integration_end','award_end')]+INTERVALS
    for name,a,b in spans:
        rows.append({'variable':name,'start':'schedule_'+a+'_date','end':'schedule_'+b+'_date',
                     'unit':'calendar_days','meaning':'Published date difference end minus start; no inclusive +1; may include waiting; zero means coincident dates, not verified absence of work'})
    return pd.DataFrame(rows)


def family_registry(df):
    records=[]
    indexed=df.set_index('procedure_code')
    for family,a,b in FAMILIES:
        if a not in indexed.index or b not in indexed.index:
            raise ValueError(f'Related-family sensitivity requires both codes: {a}, {b}')
        if str(indexed.loc[a,ENTITY])!=str(indexed.loc[b,ENTITY]):
            raise ValueError(f'Family {family} spans entity clusters; review bootstrap grouping')
        for code,role in [(a,'initial_record'),(b,'restart_record')]:
            row=indexed.loc[code]
            records.append({'family':family,'procedure_code':code,'role':role,'entity_code':str(row[ENTITY]),
                            Q:row[Q],TOTAL:row[TOTAL],CLOSE_TOTAL:row[CLOSE_TOTAL],
                            'interpretation':'Same item/restarted award' if family=='COMAS_RESTART' else 'Different items of the same mixed road/pedestrian procedure; restart for item 2',
                            'policy':'Related records retained in baseline; alternatives are sensitivity views, not definitive deduplication'})
    return pd.DataFrame(records)


def sensitivity_cohorts(df):
    family_registry(df)
    related={c for _,a,b in FAMILIES for c in (a,b)}
    cohorts={'full':df.copy(),'exclude_four':df.loc[~df.procedure_code.isin(related)].copy()}
    for retained in itertools.product(*[(a,b) for _,a,b in FAMILIES]):
        remove=related-set(retained)
        cohorts['retain_'+'_'.join(retained)]=df.loc[~df.procedure_code.isin(remove)].copy()
    expected=[len(df),len(df)-4]+[len(df)-2]*4
    if [len(x) for x in cohorts.values()]!=expected:
        raise ValueError('Sensitivity cohort counts do not match family contract')
    return cohorts


def column_correlations(matrix):
    """Pearson correlations of column 0 with the remaining columns; constants NA."""
    z=matrix-matrix.mean(axis=0)
    ss=np.square(z).sum(axis=0)
    denominator=np.sqrt(ss[0]*ss[1:])
    return np.divide(z[:,0] @ z[:,1:],denominator,out=np.full(matrix.shape[1]-1,np.nan),where=denominator>0)


def cluster_intervals(df,reps=BOOTSTRAP_REPS,seed=SEED,min_clusters=20):
    """Resample whole entities with replacement, preserving repeated-family rows.

    Recompute average ranks in every resample, so discrete ties and changing
    multiplicities are respected. Percentile 95% CIs are pointwise/exploratory;
    they assume independent, exchangeable entity clusters, not random sampling
    of all Peruvian tenders. No bootstrap p-values or causal claims are produced.
    """
    groups=[g.index.to_numpy() for _,g in df.reset_index(drop=True).groupby(ENTITY,sort=True)]
    g=len(groups)
    matrix=df[[Q]+TIME_VARIABLES].to_numpy(float)
    draws={'pearson':np.full((reps,len(TIME_VARIABLES)),np.nan),
           'spearman':np.full((reps,len(TIME_VARIABLES)),np.nan)}
    if g>=min_clusters:
        rng=np.random.default_rng(seed)
        for i in range(reps):
            idx=np.concatenate([groups[j] for j in rng.integers(0,g,size=g)])
            sample=matrix[idx]
            draws['pearson'][i]=column_correlations(sample)
            draws['spearman'][i]=column_correlations(stats.rankdata(sample,axis=0,method='average'))
    rows=[]
    for j,outcome in enumerate(TIME_VARIABLES):
        row={'outcome':outcome,'entity_clusters':g,'bootstrap_reps':reps}
        for method,values in draws.items():
            valid=values[:,j][np.isfinite(values[:,j])]
            row[method+'_cluster_valid_reps']=len(valid)
            enough=len(valid)>=max(10,math.ceil(.9*reps))
            low,high=np.quantile(valid,[.025,.975]) if enough else (np.nan,np.nan)
            row[method+'_cluster_ci_low']=low; row[method+'_cluster_ci_high']=high
            row[method+'_cluster_status']=('TOO_FEW_CLUSTERS' if g<min_clusters else
                'POINTWISE_PERCENTILE_CI' if enough else 'CONSTANT_OR_UNSTABLE_RESAMPLES')
        rows.append(row)
    return pd.DataFrame(rows)


def group_associations(df,group,min_n=MIN_GROUP_N):
    rows=[]
    for label,part in df.groupby(group,observed=True,dropna=False,sort=True):
        for outcome in MAIN_OUTCOMES:
            supported=len(part)>=min_n and part[Q].nunique()>1 and part[outcome].nunique()>1
            rows.append({'group_variable':group,'group':str(label),'outcome':outcome,'n':len(part),
                         'spearman_rho':stats.spearmanr(part[Q],part[outcome]).statistic if supported else np.nan,
                         'status':'DESCRIPTIVE_ONLY' if supported else 'SMALL_OR_CONSTANT_GROUP',
                         'minimum_group_n':min_n})
    return pd.DataFrame(rows)


def within_group_associations(df):
    """Pooled centered within-group fractional ranks; distinct descriptive estimand.

    Groups need >=3 records and variation in both variables. Included-record
    counts are reported; this never removes rows from the baseline analysis.
    """
    rows=[]
    for group in ['notice_year',ENTITY,'entity_year']:
        for outcome in MAIN_OUTCOMES:
            parts=[]
            for _,part in df.groupby(group,observed=True,dropna=False,sort=True):
                if len(part)>=3 and part[Q].nunique()>1 and part[outcome].nunique()>1:
                    ranks=stats.rankdata(part[[Q,outcome]].to_numpy(float),axis=0,method='average')/len(part)
                    parts.append(ranks-ranks.mean(axis=0))
            matrix=np.concatenate(parts) if parts else None
            value=column_correlations(matrix)[0] if matrix is not None else np.nan
            rows.append({'group_variable':group,'outcome':outcome,'supported_groups':len(parts),
                         'n_used':len(matrix) if matrix is not None else 0,'n_baseline':len(df),
                         'centered_within_group_rank_correlation':value,
                         'interpretation':'Descriptive conditional variation only; no p-value, no causal adjustment'})
    return pd.DataFrame(rows)


def sensitivity_analysis(cohorts):
    descriptions=[]; associations=[]; membership=[]
    for name,part in cohorts.items():
        desc=descriptive_statistics(part,[Q]+TIME_VARIABLES); desc.insert(0,'cohort',name); descriptions.append(desc)
        assoc=association_analysis(part)[['predictor','outcome','n','pearson_r','spearman_rho']]
        assoc.insert(0,'cohort',name); associations.append(assoc)
        related={c for _,a,b in FAMILIES for c in (a,b)}
        membership.append({'cohort':name,'n':len(part),'retained_related_codes':';'.join(sorted(set(part.procedure_code)&related)),
                           'policy':'Reference full dataset' if name=='full' else 'Sensitivity only; not definitive deduplication'})
    desc=pd.concat(descriptions,ignore_index=True); assoc=pd.concat(associations,ignore_index=True)
    baseline=desc.loc[desc.cohort.eq('full')].set_index('variable')
    baseassoc=assoc.loc[assoc.cohort.eq('full')].set_index('outcome')
    differences=[]; assocdiff=[]
    metrics=['mean','std_dev','p25','p50','p75','p90','p95','p99']
    for name in cohorts:
        if name=='full': continue
        for row in desc.loc[desc.cohort.eq(name)].to_dict('records'):
            for metric in metrics:
                before=baseline.loc[row['variable'],metric]; after=row[metric]
                delta=after-before
                relative=100*delta/abs(before) if np.isfinite(before) and before!=0 else np.nan
                flag=(abs(relative)>REPORTING_LIMITS['mean_or_sd_relative_percent'] if metric in ('mean','std_dev') and np.isfinite(relative)
                      else abs(delta)>REPORTING_LIMITS['quantile_absolute_units'] if metric not in ('mean','std_dev') else False)
                differences.append({'cohort':name,'variable':row['variable'],'metric':metric,'baseline':before,
                                    'sensitivity':after,'absolute_change':delta,'relative_change_percent':relative,
                                    'exceeds_reporting_threshold':bool(flag)})
        for row in assoc.loc[assoc.cohort.eq(name)].to_dict('records'):
            for method in ['pearson_r','spearman_rho']:
                before=baseassoc.loc[row['outcome'],method]; delta=row[method]-before
                assocdiff.append({'cohort':name,'outcome':row['outcome'],'method':method,'baseline':before,
                                  'sensitivity':row[method],'absolute_change':delta,
                                  'exceeds_reporting_threshold':bool(abs(delta)>REPORTING_LIMITS['correlation_absolute_change'])})
    return {'cohorts':pd.DataFrame(membership),'descriptive_statistics':desc,'Q_duration_correlations':assoc,
            'descriptive_changes':pd.DataFrame(differences),'association_changes':pd.DataFrame(assocdiff),
            'reporting_thresholds':pd.DataFrame([{'criterion':k,'threshold':v,'interpretation':'Operational reporting aid, not a validated engineering equivalence margin or hypothesis test'} for k,v in REPORTING_LIMITS.items()])}


def save_figures(df,folder):
    folder.mkdir()
    fig,axes=plt.subplots(1,3,figsize=(15,4))
    for axis,var,label in zip(axes,[Q,TOTAL,CLOSE_TOTAL],['Combined record count Q','Query start to award end','Query close to award end']):
        axis.hist(df[var],bins='auto',color='#176b87')
        axis.set(xlabel='Records' if var==Q else 'Published schedule days',ylabel='Eligible records',title=label)
    fig.tight_layout(); fig.savefig(folder/'04_distributions.png',dpi=160); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for axis,var,label in zip(axes,MAIN_OUTCOMES,['Query start','Query close']):
        plot=axis.hexbin(df[Q],df[var],gridsize=35,mincnt=1,cmap='Blues',bins='log')
        fig.colorbar(plot,ax=axis,label='Record count (log color scale)')
        axis.set(xlabel='Combined record count Q',ylabel='Published schedule days',title=label+' to award end')
    fig.tight_layout(); fig.savefig(folder/'04_Q_and_durations.png',dpi=160); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    for axis,var in zip(axes,MAIN_OUTCOMES):
        x=np.sort(df[var].to_numpy()); axis.step(x,np.arange(1,len(x)+1)/len(x),where='post',color='#176b87')
        axis.set(xlabel='Published schedule days',ylabel='Empirical cumulative probability',title='Query '+('start' if var==TOTAL else 'close')+' to award end')
        axis.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(folder/'04_empirical_cdf.png',dpi=160); plt.close(fig)
    fig,axis=plt.subplots(figsize=(11,5))
    variables=[x[0] for x in INTERVALS]
    labels=[a.replace('_',' ')+' → '+b.replace('_',' ') for _,a,b in INTERVALS]
    axis.barh(labels,[100*df[v].eq(0).mean() for v in variables],color='#367c59')
    axis.set(xlabel='Records with coincident dates (%)',xlim=(0,100),title='Published interval zeros; not verified absence of activity')
    axis.invert_yaxis(); fig.tight_layout(); fig.savefig(folder/'04_interval_zeros.png',dpi=160); plt.close(fig)


def build_analysis(df,output,metadata,reps,seed):
    df=df.copy()
    original_missing=pd.DataFrame({'variable':df.columns,'missing_count':df.isna().sum().to_numpy()})
    original_missing['missing_percent']=100*original_missing.missing_count/len(df)
    checks=analysis_contract(df)
    if checks.failures.sum(): raise ValueError('Analysis contract failed: '+checks.loc[checks.failures.gt(0)].to_json(orient='records'))
    df['procedure_description']=df.get('source00_procedure_description',pd.Series('',index=df.index))
    df['notice_year']=pd.to_datetime(df.source00_notice_date,errors='coerce').dt.year.astype('Int64').astype(str)
    df['entity_year']=df[ENTITY].astype(str)+'|'+df.notice_year
    registry=family_registry(df)
    cohorts=sensitivity_cohorts(df)
    log(f'Baseline records={len(df)}; sensitivity sizes={[len(x) for x in cohorts.values()]}')
    descriptions=descriptive_statistics(df,[Q]+TIME_VARIABLES)
    out_summary,out_details=iqr_outlier_diagnostics(df,[Q]+TIME_VARIABLES)
    tails=pd.DataFrame([{'variable':v,'zero_count':int(df[v].eq(0).sum()),'zero_percent':100*df[v].eq(0).mean(),
                        'unique_values':df[v].nunique(),**{'p'+str(int(q*100)).zfill(2):df[v].quantile(q) for q in [.05,.1,.9,.95,.99]}} for v in [Q]+TIME_VARIABLES])
    sizes=df.groupby(ENTITY).size()
    cluster_profile=pd.DataFrame([{'records':len(df),'entities':len(sizes),'singleton_entities':int(sizes.eq(1).sum()),
                                   'largest_entity_records':int(sizes.max()),'records_in_repeated_entities':int(sizes.loc[sizes.gt(1)].sum())}])
    policy=[
        ('interpretation','Published schedule differences, not independently verified actual elapsed times; all associations are noncausal'),
        ('Q','One combined numbered consultation/observation document-record count; verified zero acts retained; proxy interpretation needs theory'),
        ('association','Spearman primary, average ranks for ties; Pearson supplementary. Existing p-value/BH columns are IID-only compatibility diagnostics and do not support dependence-aware conclusions'),
        ('bootstrap',f'{reps} whole-entity resamples, seed={seed}; percentile 95% pointwise CIs. Independent exchangeable entities assumed; no survey weights or population-representative inference'),
        ('family_policy','All four related records retained in baseline; four alternative one-per-pair views and exclusion-of-four view; no definitive deduplication. Families nested within entity bootstrap clusters'),
        ('heterogeneity','Year/type/entity profiles; group associations only if n>=20 and variation. Within-group fractional ranks require n>=3 and variation; different descriptive estimand, no p-values'),
        ('normality','No Shapiro decisions for discrete, tied and clustered observations; constants and counts explicitly marked. Normality not assumed for descriptive moments or rank correlations'),
        ('quantiles','pandas linear empirical interpolation; fractional quantiles are summaries, not fractional-day observations'),
        ('outliers','1.5 IQR flags retained; IQR=0 flags are concentration diagnostics, not errors'),
        ('reporting_thresholds',json.dumps(REPORTING_LIMITS)+'; descriptive aids, not formal equivalence margins'),
        ('horizons','Both start-to-award and close-to-award reported. The former includes the consultation window; Script 05 uses close-to-award'),
    ]
    meta=pd.DataFrame([{'item':k,'value':json.dumps(v,ensure_ascii=False,default=str) if isinstance(v,(dict,list)) else str(v)} for k,v in metadata.items()]+[{'item':k,'value':v} for k,v in policy])
    quality={'quality_checks':checks,'missingness':original_missing,'run_metadata':meta,
             'variable_dictionary':variable_dictionary(),'related_families':registry,'entity_cluster_profile':cluster_profile}
    for source in ['source02_document_type','source02_processing_method','source02_count_status']:
        if source in df: quality[source.replace('source02_','')]=df[source].value_counts(dropna=False).rename_axis('category').reset_index(name='procedures')
    descriptives={'descriptive_statistics':descriptions,'tails_and_zeros':tails,
                  'Q_frequency':df[Q].value_counts().sort_index().rename_axis(Q).reset_index(name='procedures'),
                  'normality_diagnostics':normality_diagnostics(df,[Q]+TIME_VARIABLES),
                  'outlier_summary':out_summary,'outlier_details':out_details,
                  'diagnostic_Q_bands':exploratory_bands(df),'duration_by_exact_Q':profile(df,Q),
                  'notice_year_profile':profile(df,'notice_year'),'entity_profile':profile(df,ENTITY),'run_metadata':meta}
    if 'source00_entity_type' in df: descriptives['entity_type_profile']=profile(df,'source00_entity_type')
    if 'source00_reference_amount' in df:
        money=df.copy(); money['reference_amount']=pd.to_numeric(money.source00_reference_amount,errors='coerce')
        money['source_currency']=money.get('source00_source_currency',pd.Series('UNKNOWN',index=money.index)).fillna('UNKNOWN').replace('','UNKNOWN')
        amount=[]
        for cur,g in money.groupby('source_currency',dropna=False):
            row=descriptive_statistics(g,['reference_amount']); row.insert(0,'currency',cur); amount.append(row)
        descriptives['reference_amount_by_currency']=pd.concat(amount,ignore_index=True)
    assoc=association_analysis(df)
    assoc['pearson_p_BH']=bh_adjust(assoc.pearson_p_value); assoc['spearman_p_BH']=bh_adjust(assoc.spearman_p_value)
    assoc['p_value_scope']='IID_ONLY_NOT_ENTITY_DEPENDENCE_ADJUSTED'
    log(f'Entity bootstrap: {len(sizes)} clusters; {reps} resamples')
    assoc=assoc.merge(cluster_intervals(df,reps,seed),on='outcome',validate='one_to_one')
    cov_summary,cov_table=covariance_diagnostic(df)
    residual=cov_summary.loc[cov_summary.metric.eq('variance_identity_residual'),'value'].iloc[0]
    if not np.isclose(residual,0,atol=1e-8,rtol=0): raise ValueError('Interval variance decomposition does not reconcile')
    associations={'Q_duration_correlations':assoc,'interval_spearman':correlation_table(df,[x[0] for x in INTERVALS]),
                  'interval_covariance':cov_table,'total_variance_decomposition':cov_summary,
                  'analysis_data':df[['procedure_code',Q]+TIME_VARIABLES],'interpretation':meta,
                  'year_associations':group_associations(df,'notice_year'),'entity_associations':group_associations(df,ENTITY),
                  'within_group_associations':within_group_associations(df)}
    if 'source00_entity_type' in df: associations['entity_type_associations']=group_associations(df,'source00_entity_type')
    sensitivity=sensitivity_analysis(cohorts); sensitivity['related_families']=registry; sensitivity['run_metadata']=meta
    workbooks={'04_1_descriptive_statistics.xlsx':descriptives,'04_2_data_quality_diagnostics.xlsx':quality,
               '04_3_association_analysis.xlsx':associations,'04_4_family_sensitivity.xlsx':sensitivity}
    for name,sheets in workbooks.items(): save_workbook(output/name,sheets)
    save_figures(df,output/'figures')
    main_summary=descriptions.loc[descriptions.variable.isin([Q]+MAIN_OUTCOMES)].to_dict('records')
    return workbooks,{'descriptive_main':main_summary,'sensitivity_cohorts':sensitivity['cohorts'].to_dict('records'),
                      'entity_cluster_profile':cluster_profile.to_dict('records'),'quality_failures':int(checks.failures.sum())}


def verify_workbooks(output,workbooks):
    for name,sheets in workbooks.items():
        with pd.ExcelFile(output/name,engine='openpyxl') as book:
            if book.sheet_names!=list(sheets): raise ValueError(f'Workbook sheet contract mismatch: {name}')
            for sheet,expected in sheets.items():
                actual=pd.read_excel(book,sheet_name=sheet,keep_default_na=False,dtype=object)
                if list(actual.columns)!=list(expected.columns) or len(actual)!=len(expected):
                    raise ValueError(f'Workbook structure mismatch: {name}/{sheet}')
                for col in expected:
                    for x,y in zip(expected[col],actual[col]):
                        missing_x=pd.isna(x) or (isinstance(x,str) and x=='')
                        missing_y=pd.isna(y) or (isinstance(y,str) and y=='')
                        if missing_x or missing_y: equal=missing_x and missing_y
                        elif isinstance(x,(int,float,np.number)) and isinstance(y,(int,float,np.number)):
                            equal=math.isclose(float(x),float(y),rel_tol=1e-12,abs_tol=1e-12)
                        else: equal=str(x)==str(y)
                        if not equal: raise ValueError(f'Workbook value mismatch: {name}/{sheet}/{col}')
    for path in (output/'figures').glob('*.png'):
        pixels=plt.imread(path)
        if pixels.ndim!=3 or not np.isfinite(pixels).all(): raise ValueError(f'Invalid plot: {path}')


def protected_hashes(root):
    files=sorted((root/'00_data').glob('*.xlsx'))
    files+=sorted(p for p in (root/'02_results/01_sample_and_data').iterdir() if p.is_file())
    return [{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in files]


def run(root,output_root,reps=BOOTSTRAP_REPS,seed=SEED):
    root=Path(root).resolve(); output_root=Path(output_root).resolve()
    if output_root==root or (root/'00_data')==output_root or (root/'00_data') in output_root.parents:
        raise ValueError('Use an independent output root outside original 00_data')
    output=output_root/'02_results/02_statistical_analysis'
    if output.exists() or output.is_symlink(): raise FileExistsError(f'Refusing existing outputs: {output}')
    input_file=root/'02_results/01_sample_and_data/03_2_model_ready_dataset.xlsx'
    before=protected_hashes(root); script_hash=digest(Path(__file__)); LOG_LINES.clear()
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+uuid.uuid4().hex
    metadata={'version':VERSION,'run_id':run_id,'started_utc':datetime.now(timezone.utc).isoformat(),
              'input':str(input_file),'input_sha256':digest(input_file),'script_sha256':script_hash,
              'python':sys.version.split()[0],'packages':{p:importlib.metadata.version(p) for p in ['pandas','numpy','scipy','openpyxl','matplotlib']},
              'bootstrap_reps':reps,'bootstrap_seed':seed,'output_root':str(output_root)}
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.04_'+run_id+'_',suffix='.tmp',dir=output.parent))
    logs=output_root/'03_logs/02_statistical_analysis'; logs.mkdir(parents=True,exist_ok=True)
    logfile=logs/f'04_exploratory_analysis_{run_id}.log'
    try:
        df=pd.read_excel(input_file,dtype={'procedure_code':str,ENTITY:str})
        workbooks,summary=build_analysis(df,staging,metadata,reps,seed)
        verify_workbooks(staging,workbooks)
        if protected_hashes(root)!=before: raise ValueError('Original inputs or 00–03 outputs changed during analysis')
        if digest(Path(__file__))!=script_hash: raise ValueError('Script changed during analysis')
        generated=[{'path':str(p.relative_to(staging)),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(staging.rglob('*')) if p.is_file()]
        manifest={**metadata,'completed_utc':datetime.now(timezone.utc).isoformat(),'status':'COMPLETE',
                  'protected_files':before,'outputs':generated,'summary':summary,'reporting_thresholds':REPORTING_LIMITS}
        (staging/'04_run_manifest.json').write_text(json.dumps(json_safe(manifest),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        if output.exists() or output.is_symlink(): raise FileExistsError('Output appeared during execution; refusing publication')
        staging.rename(output)
        log(f'COMPLETE | Baseline retained; published validated outputs: {output}')
        return output
    except Exception:
        log('FAILED | No definitive outputs published\n'+traceback.format_exc())
        if staging.exists():
            if staging.is_symlink() or staging.resolve().parent!=output.parent.resolve() or not staging.name.startswith('.04_'+run_id+'_'):
                raise RuntimeError('Unsafe temporary cleanup path; staging retained')
            shutil.rmtree(staging)
        raise
    finally:
        with logfile.open('x',encoding='utf-8') as stream: stream.write(json.dumps(metadata,ensure_ascii=False)+'\n'+'\n'.join(LOG_LINES)+'\n')



def json_safe(value):
    if isinstance(value,dict): return {k:json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [json_safe(v) for v in value]
    if isinstance(value,np.generic): return json_safe(value.item())
    if isinstance(value,float) and not math.isfinite(value): return None
    return value


def run_self_tests():
    """Small synthetic tests only; no original datasets are read or modified."""
    import contextlib
    import io
    import unittest
    from unittest import mock
    import openpyxl

    def fixture():
        codes=['811044','848861','995451','1058629']+[str(900000+i) for i in range(36)]
        rows=[]
        for i,code in enumerate(codes):
            entity='COMAS' if i<2 else 'OLMOS' if i<4 else 'E'+str((i-4)//2)
            q=[73,73,42,42][i] if i<4 else (i*7)%23
            row={'procedure_code':code,Q:q,'source02_queries_observations_count':q,
                 'eligible_common_model':True,'source02_count_status':'OK',
                 'date_nature':'published_schedule_not_verified_actual_events',
                 'duration_unit':'calendar_days','modeled_origin':'query_formulation_start',
                 'observed_actual_event_dates_verified':False,ENTITY:entity,
                 'source00_notice_date':pd.Timestamp(2020+i%3,1,1),
                 'source00_entity_type':'LOCAL','source00_procedure_description':'SYNTHETIC ROAD',
                 'source00_reference_amount':1000+i,'source00_source_currency':'PEN',
                 'source02_document_type':'ACTA_NO_FORMULACION' if q==0 else 'PLIEGO',
                 'source02_processing_method':'SYNTHETIC','qc_valid_Q':True}
            durations=[4+i%3,2,0,i%2,0,4,0,1,1+i%4,0,0]
            date=pd.Timestamp(2020+i%3,1,2)
            row['schedule_'+BOUNDARIES[0]+'_date']=date
            for (name,a,b),days in zip(INTERVALS,durations):
                row[name]=days; date+=pd.Timedelta(days=days); row['schedule_'+b+'_date']=date
            for name,a,b in [(TOTAL,'query_start','award_end'),(CLOSE_TOTAL,'query_end','award_end'),
                             ('absolution_calendar_days','query_end','absolution_end'),
                             ('integration_calendar_days','absolution_end','integration_end'),
                             ('post_integration_calendar_days','integration_end','award_end')]:
                row[name]=(row['schedule_'+b+'_date']-row['schedule_'+a+'_date']).days
            rows.append(row)
        return pd.DataFrame(rows)

    class AnalysisTests(unittest.TestCase):
        def setUp(self):
            self.df=fixture()

        def test_descriptive_known_values(self):
            result=descriptive_statistics(pd.DataFrame({Q:[0,1,2,3]}),[Q]).iloc[0]
            self.assertEqual(result['mean'],1.5); self.assertEqual(result['median'],1.5)
            self.assertAlmostEqual(result.std_dev,math.sqrt(5/3)); self.assertAlmostEqual(result.p90,2.7)
            self.assertTrue(np.isnan(safe_cv(pd.Series([0,0]))))

        def test_missing_and_invalid_numeric_counted(self):
            result=descriptive_statistics(pd.DataFrame({Q:[1,None,'invalid']}),[Q]).iloc[0]
            self.assertEqual(result['n'],1); self.assertEqual(result['missing'],2)

        def test_contract(self):
            before=self.df.copy(deep=True)
            self.assertEqual(int(analysis_contract(self.df.copy()).failures.sum()),0)
            pd.testing.assert_frame_equal(self.df,before)

        def test_invalid_Q_and_dates(self):
            part=self.df.copy(); part[Q]=part[Q].astype(float); part.loc[0,Q]=-.5
            self.assertGreater(analysis_contract(part).failures.sum(),0)
            part=self.df.copy(); part.loc[0,TOTAL]+=1
            self.assertGreater(analysis_contract(part).failures.sum(),0)
            part=self.df.copy(); part['schedule_query_start_date']=43831
            with self.assertRaisesRegex(ValueError,'Numeric date'): analysis_contract(part)

        def test_missing_required_and_duplicate_identifiers(self):
            with self.assertRaisesRegex(ValueError,'Missing analysis context'): analysis_contract(self.df.drop(columns=[ENTITY]))
            part=self.df.copy(); part.loc[0,'procedure_code']=part.loc[1,'procedure_code']
            with self.assertRaisesRegex(ValueError,'duplicate'): analysis_contract(part)

        def test_sensitivity_membership(self):
            cohorts=sensitivity_cohorts(self.df)
            self.assertEqual([len(x) for x in cohorts.values()],[40,36,38,38,38,38])
            self.assertEqual(len({tuple(x.procedure_code) for x in list(cohorts.values())[2:]}),4)
            self.assertEqual(len(self.df),40)
            for part in list(cohorts.values())[2:]:
                for _,a,b in FAMILIES: self.assertEqual(int(part.procedure_code.isin([a,b]).sum()),1)

        def test_family_contract(self):
            with self.assertRaisesRegex(ValueError,'requires both'): sensitivity_cohorts(self.df.iloc[1:])
            part=self.df.copy(); part.loc[0,ENTITY]='WRONG_ENTITY'
            with self.assertRaisesRegex(ValueError,'spans entity clusters'): family_registry(part)

        def test_average_tie_ranks(self):
            matrix=np.array([[0,1],[0,2],[1,2],[2,4]],float)
            got=column_correlations(stats.rankdata(matrix,axis=0,method='average'))[0]
            self.assertAlmostEqual(got,stats.spearmanr(matrix[:,0],matrix[:,1]).statistic)

        def test_bootstrap_reference_and_reproducibility(self):
            first=cluster_intervals(self.df,30,123,min_clusters=3)
            second=cluster_intervals(self.df,30,123,min_clusters=3)
            pd.testing.assert_frame_equal(first,second)
            groups=[g.index.to_numpy() for _,g in self.df.groupby(ENTITY,sort=True)]
            rng=np.random.default_rng(123); draws=[]
            for _ in range(30):
                ids=np.concatenate([groups[j] for j in rng.integers(0,len(groups),size=len(groups))])
                sample=self.df.iloc[ids]
                draws.append(stats.spearmanr(sample[Q],sample[TOTAL]).statistic)
            row=first.set_index('outcome').loc[TOTAL]
            self.assertAlmostEqual(row.spearman_cluster_ci_low,np.quantile(draws,.025))
            self.assertAlmostEqual(row.spearman_cluster_ci_high,np.quantile(draws,.975))

        def test_cluster_support_and_constants(self):
            result=cluster_intervals(self.df,30,123,min_clusters=100)
            self.assertTrue(result.spearman_cluster_ci_low.isna().all())
            result=cluster_intervals(self.df,30,123,min_clusters=3).set_index('outcome')
            constant='integration_start_to_integration_end_calendar_days'
            self.assertEqual(result.loc[constant,'spearman_cluster_valid_reps'],0)
            self.assertTrue(pd.isna(result.loc[constant,'spearman_cluster_ci_low']))

        def test_BH_known_values(self):
            np.testing.assert_allclose(bh_adjust([.01,.04,.03,np.nan]),[.03,.04,.04,np.nan],equal_nan=True)

        def test_normality_status(self):
            constant='integration_start_to_integration_end_calendar_days'
            result=normality_diagnostics(self.df,[Q,TOTAL,constant]).set_index('variable')
            self.assertEqual(result.loc[Q,'interpretation_alpha_0_05'],'NOT_APPLICABLE_DISCRETE_COUNT')
            self.assertEqual(result.loc[constant,'interpretation_alpha_0_05'],'CONSTANT_VARIABLE')
            self.assertTrue(result.shapiro_p_value.isna().all())

        def test_variance_identity(self):
            result,_=covariance_diagnostic(self.df)
            residual=result.set_index('metric').loc['variance_identity_residual','value']
            self.assertAlmostEqual(residual,0,places=10)

        def test_group_support(self):
            result=group_associations(self.df,ENTITY)
            self.assertTrue(result.spearman_rho.isna().all())
            part=self.df.copy(); part['notice_year']='2020'; part['entity_year']=part[ENTITY]+'|2020'
            result=within_group_associations(part)
            self.assertTrue(result.n_used.le(len(part)).all())

        def test_reporting_deltas(self):
            cohorts=sensitivity_cohorts(self.df)
            result=sensitivity_analysis(cohorts)
            self.assertEqual(len(result['cohorts']),6)
            rows=result['descriptive_changes']
            row=rows.loc[rows.cohort.eq('exclude_four') & rows.variable.eq(Q) & rows.metric.eq('mean')].iloc[0]
            self.assertAlmostEqual(row.absolute_change,cohorts['exclude_four'][Q].mean()-self.df[Q].mean())

        def synthetic_project(self,folder):
            root=folder/'input'; base=root/'02_results/01_sample_and_data'; base.mkdir(parents=True)
            (root/'00_data').mkdir()
            path=base/'03_2_model_ready_dataset.xlsx'
            self.df.to_excel(path,index=False,engine='openpyxl')
            return root,path

        def test_complete_publication_and_integrity(self):
            with tempfile.TemporaryDirectory(prefix='thesis_script04_test_') as directory:
                folder=Path(directory); root,path=self.synthetic_project(folder); before=digest(path)
                with contextlib.redirect_stdout(io.StringIO()): out=run(root,folder/'output',30,123)
                manifest=json.loads((out/'04_run_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['status'],'COMPLETE'); self.assertEqual(before,digest(path))
                self.assertEqual(len(manifest['outputs']),8)
                for entry in manifest['outputs']: self.assertEqual(entry['sha256'],digest(out/entry['path']))
                baseline=pd.read_excel(out/'04_3_association_analysis.xlsx',sheet_name='analysis_data')
                self.assertEqual(len(baseline),40)
                self.assertEqual(list(baseline.columns),['procedure_code',Q]+TIME_VARIABLES)
                with self.assertRaises(FileExistsError): run(root,folder/'output',30,123)

        def test_failed_write_does_not_publish(self):
            with tempfile.TemporaryDirectory(prefix='thesis_script04_test_') as directory:
                folder=Path(directory); root,path=self.synthetic_project(folder); before=digest(path)
                with mock.patch.dict(globals(),{'save_workbook':mock.Mock(side_effect=PermissionError('synthetic locked file'))}):
                    with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(PermissionError): run(root,folder/'output',30,123)
                self.assertFalse((folder/'output/02_results/02_statistical_analysis').exists())
                self.assertEqual(before,digest(path))
                self.assertEqual(list((folder/'output/02_results').glob('.04_*.tmp')),[])

        def test_corruption_is_detected(self):
            with tempfile.TemporaryDirectory(prefix='thesis_script04_test_') as directory:
                folder=Path(directory); path=folder/'test.xlsx'
                frame=pd.DataFrame({'value':[1,2]}); save_workbook(path,{'data':frame})
                (folder/'figures').mkdir()
                book=openpyxl.load_workbook(path)
                try: book.active.cell(2,1,999); book.save(path)
                finally: book.close()
                with self.assertRaisesRegex(ValueError,'value mismatch'): verify_workbooks(folder,{'test.xlsx':{'data':frame}})

    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AnalysisTests))
    if not result.wasSuccessful(): raise RuntimeError('Synthetic tests failed; real-data execution must not proceed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path)
    parser.add_argument('--output-root',type=Path,help='Fresh independent project-shaped output root (required for analysis)')
    parser.add_argument('--bootstrap-reps',type=int,default=BOOTSTRAP_REPS)
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if args.self_test: return run_self_tests()
    if args.output_root is None: parser.error('--output-root is required; existing official outputs are never overwritten')
    if args.bootstrap_reps<999: parser.error('Use at least 999 bootstrap resamples for the controlled analysis')
    root=args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()),None)
    if root is None: parser.error('Cannot locate project root; use --project-root')
    run(root,args.output_root,args.bootstrap_reps,args.seed)


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'ANALYSIS FAILED: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)
