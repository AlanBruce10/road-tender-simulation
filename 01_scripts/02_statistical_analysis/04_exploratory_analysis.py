"""Exploratory analysis of the common eligible Script 03 cohort.
No scenario assignment, exclusions, imputation, distribution selection or simulation.
Run: python 04_exploratory_analysis.py
Dependencies: pandas numpy scipy openpyxl matplotlib.
"""
import argparse
import hashlib
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

VERSION = '2.0-fiche-based-exploration'
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
    return series.astype(str).str.strip().str.lower().isin(['true','1'])


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
        missing = df[variable].isna().sum()

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
            "skewness": stats.skew(
                x,
                bias=False,
                nan_policy="omit"
            ) if n >= 3 else np.nan,
            "excess_kurtosis": stats.kurtosis(
                x,
                fisher=True,
                bias=False,
                nan_policy="omit"
            ) if n >= 4 else np.nan,
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
    """
    Perform normality diagnostics.

    Shapiro-Wilk is a diagnostic for the observed sample. Results are treated as diagnostics, not as automatic
    distribution-selection rules.
    """
    rows = []

    for variable in variables:
        x = pd.to_numeric(df[variable], errors="coerce").dropna()

        n = len(x)

        if n < 3 or x.nunique() < 2 or n > 5000:
            rows.append({
                "variable": variable,
                "n": n,
                "shapiro_w": np.nan,
                "shapiro_p_value": np.nan,
                "interpretation_alpha_0_05": "INSUFFICIENT_DATA",
            })
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            w_stat, p_value = stats.shapiro(x)

        interpretation = (
            "REJECT_NORMALITY"
            if p_value < 0.05
            else "DO_NOT_REJECT_NORMALITY"
        )

        rows.append({
            "variable": variable,
            "n": n,
            "shapiro_w": w_stat,
            "shapiro_p_value": p_value,
            "interpretation_alpha_0_05": interpretation,
        })

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
    return profile(temp,'diagnostic_Q_band')


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


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path)
    args=parser.parse_args()
    root=args.project_root.resolve() if args.project_root else next((p for p in Path(__file__).resolve().parents if (p/'00_data').is_dir()),None)
    if root is None:parser.error('Cannot locate repository root; use --project-root PATH')
    input_file=root/'02_results'/'01_sample_and_data'/'03_2_model_ready_dataset.xlsx'
    output=root/'02_results'/'02_statistical_analysis'
    logs=root/'03_logs'/'02_statistical_analysis'
    for folder in (output,logs):folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    logfile=logs/f'04_exploratory_analysis_{stamp}.log'
    try:
        df=pd.read_excel(input_file,dtype={'procedure_code':str})
        log(f'EXPLORATORY ANALYSIS | {VERSION} | procedures={len(df)}')
        log('Input: eligible Script 03 cohort; published schedule dates; calendar-day durations')
        checks=validate(df)
        missingness=pd.DataFrame({'variable':df.columns,'missing_count':df.isna().sum().to_numpy()})
        missingness['missing_percent']=100*missingness.missing_count/len(df)
        metadata=pd.DataFrame([
            {'item':'version','value':VERSION},
            {'item':'input','value':str(input_file.relative_to(root))},
            {'item':'input_sha256','value':digest(input_file)},
            {'item':'script_sha256','value':digest(Path(__file__))},
            {'item':'run_utc','value':datetime.now(timezone.utc).isoformat()},
            {'item':'packages','value':f'Python {sys.version.split()[0]}; pandas {pd.__version__}; numpy {np.__version__}; scipy {scipy.__version__}; matplotlib {matplotlib.__version__}'},
            {'item':'interpretation','value':'Exploration only; no scenarios, causal effects, fits or simulation established'},
            {'item':'test_policy','value':'Two-sided exploratory correlations; BH adjusted within each Pearson/Spearman family; p-values are nominal and do not account for entity clustering'},
            {'item':'bands','value':'Q=0 separate; positive Q empirical quartiles with tied cutpoints dropped; diagnostic only'},
            {'item':'amounts','value':'Reference amounts summarized separately by source currency; no monetary exclusion'},
            {'item':'normality','value':'Shapiro diagnostic only; constant, small or n>5000 samples not tested; Q is a discrete count'},
            {'item':'outliers','value':'1.5 IQR flags retained; no trimming or winsorization'},
        ])
        quality={'quality_checks':checks,'missingness':missingness,'run_metadata':metadata}
        for source in ['source02_document_type','source02_processing_method','source02_count_status']:
            if source in df:
                quality[source.replace('source02_','')]=df[source].value_counts(dropna=False).rename_axis('category').reset_index(name='procedures')
        save_workbook(output/'04_2_data_quality_diagnostics.xlsx',quality)
        if checks.failures.sum():
            raise ValueError('Analytical contract failed; see 04_2_data_quality_diagnostics.xlsx. No records silently excluded.')
        if 'source00_procedure_description' in df:
            df['procedure_description']=df.source00_procedure_description
        else:df['procedure_description']=''
        variables=[Q]+TIME_VARIABLES
        descriptive=descriptive_statistics(df,variables)
        tail_rows=[]
        for v in variables:
            x=df[v]
            tail_rows.append({'variable':v,'zero_count':int(x.eq(0).sum()),'zero_percent':100*x.eq(0).mean(),
                              'unique_values':x.nunique(),'p05':x.quantile(.05),'p10':x.quantile(.1),
                              'p90':x.quantile(.9),'p95':x.quantile(.95),'p99':x.quantile(.99)})
        outlier_summary,outlier_details=iqr_outlier_diagnostics(df,variables)
        normality=normality_diagnostics(df,variables)
        frequency=df[Q].value_counts().sort_index().rename_axis(Q).reset_index(name='procedures')
        descriptives={'descriptive_statistics':descriptive,'tails_and_zeros':pd.DataFrame(tail_rows),
                      'Q_frequency':frequency,'normality_diagnostics':normality,
                      'outlier_summary':outlier_summary,'outlier_details':outlier_details,
                      'diagnostic_Q_bands':exploratory_bands(df),'duration_by_exact_Q':profile(df,Q)}
        # Year and entity composition are context checks, not new sample restrictions.
        if 'source00_notice_date' in df:
            df['notice_year']=pd.to_datetime(df.source00_notice_date,errors='coerce').dt.year.astype('Int64').astype(str)
            descriptives['notice_year_profile']=profile(df,'notice_year')
        if 'source00_entity_type' in df:descriptives['entity_type_profile']=profile(df,'source00_entity_type')
        if 'source00_reference_amount' in df:
            money=df.copy();money['reference_amount']=pd.to_numeric(money.source00_reference_amount,errors='coerce')
            currency=money['source00_source_currency'].fillna('UNKNOWN') if 'source00_source_currency' in money else pd.Series('UNKNOWN',index=money.index)
            money['source_currency']=currency.replace('', 'UNKNOWN')
            amt=[]
            for cur,g in money.groupby('source_currency',dropna=False):
                r=descriptive_statistics(g,['reference_amount']);r.insert(0,'currency',cur);amt.append(r)
            descriptives['reference_amount_by_currency']=pd.concat(amt,ignore_index=True)
        save_workbook(output/'04_1_descriptive_statistics.xlsx',descriptives)
        assoc=association_analysis(df)
        assoc['pearson_p_BH']=bh_adjust(assoc.pearson_p_value)
        assoc['spearman_p_BH']=bh_adjust(assoc.spearman_p_value)
        cov_summary,cov_table=covariance_diagnostic(df)
        dependence=correlation_table(df,[x[0] for x in INTERVALS])
        save_workbook(output/'04_3_association_analysis.xlsx',{
            'Q_duration_correlations':assoc,'interval_spearman':dependence,
            'interval_covariance':cov_table,'total_variance_decomposition':cov_summary,
            'analysis_data':df[['procedure_code',Q]+TIME_VARIABLES],'interpretation':metadata})
        # Export compact diagnostic plots. No fitted model or implied causal trend.
        figure_dir=output/'figures';figure_dir.mkdir(exist_ok=True)
        fig,axes=plt.subplots(1,2,figsize=(11,4))
        axes[0].hist(df[Q],bins='auto',color='#176b87');axes[0].set(xlabel='Combined Q',ylabel='Procedures',title='Consultation/observation volume')
        axes[1].hist(df[TOTAL],bins='auto',color='#367c59');axes[1].set(xlabel='Published schedule duration (calendar days)',ylabel='Procedures',title='Query start to award end')
        fig.tight_layout();fig.savefig(figure_dir/'04_distributions.png',dpi=180);plt.close(fig)
        fig,axes=plt.subplots(1,2,figsize=(11,4))
        for axis,outcome,title in zip(axes,[TOTAL,CLOSE_TOTAL],['From query start','From query close']):
            axis.scatter(df[Q],df[outcome],s=10,alpha=.25,color='#176b87')
            axis.set(xlabel='Combined Q',ylabel='Published schedule duration (calendar days)',title=title)
        fig.tight_layout();fig.savefig(figure_dir/'04_Q_and_durations.png',dpi=180);plt.close(fig)
        for outcome in [TOTAL,CLOSE_TOTAL]:
            row=assoc.loc[assoc.outcome.eq(outcome)].iloc[0]
            log(f'{outcome}: median={df[outcome].median():.1f}, p90={df[outcome].quantile(.9):.1f}; Q Spearman rho={row.spearman_rho:.4f}')
        log(f'Verified Q=0: {int(df[Q].eq(0).sum())}; Q median={df[Q].median():.1f}; Q maximum={df[Q].max():.0f}')
        log('COMPLETE | no records removed; no scenario thresholds or distributions selected')
        log(f'Outputs: {output}')
    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}')
        raise
    finally:
        logfile.write_text('\n'.join(LOG_LINES)+'\n',encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception:sys.exit(1)
