"""Descriptive/structural sensitivity using approved historical and saved artifacts.

Stage 1: no simulation, calibration, copula perturbation or hypothesis verdict.
"""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd

VERSION='2.0-artifact-reuse-sensitivity'
Q='queries_observations_count'
VERIFIED_Q='source02_queries_observations_count'
TARGET='query_close_to_award_calendar_days'
GROUP='cv_dependency_group'
GOV='calibration_government'
AMOUNT='source00_reference_amount'
MODELS=['M1','M2','M4']
SCENARIOS=['low','medium','high']


def approved08():
    import types
    path=Path(__file__).with_name('08_model_validation.py');module=types.ModuleType('approved08');module.__file__=str(path)
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),module.__dict__)
    return module


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def task_rng(seed,task):
    key=hashlib.sha256(task.encode()).digest()
    return np.random.default_rng(np.random.SeedSequence(seed,spawn_key=tuple(int.from_bytes(key[i:i+4],'little') for i in range(0,16,4))))


def classify_history(history,bundle,expected_n=None):
    h=history.copy()
    required={'procedure_code',Q,VERIFIED_Q,TARGET,GROUP,GOV,AMOUNT,'source00_notice_date'}
    if required-set(h):raise ValueError('Missing approved historical columns')
    if h.procedure_code.isna().any() or h.procedure_code.duplicated().any() or (expected_n is not None and len(h)!=expected_n):raise ValueError('Historical IDs/cardinality invalid')
    for col in [Q,VERIFIED_Q,TARGET,AMOUNT]:
        h[col]=pd.to_numeric(h[col],errors='coerce')
        if not np.isfinite(h[col]).all():raise ValueError('Nonfinite historical inputs')
    if not np.array_equal(h[Q],h[VERIFIED_Q]) or h[Q].lt(0).any() or h[Q].mod(1).ne(0).any():raise ValueError('Q must equal verified consultation/observation count, never duration')
    if h[AMOUNT].le(0).any() or h[TARGET].lt(0).any():raise ValueError('Invalid amount/duration')
    if not h[GOV].isin(['GOBIERNO LOCAL','GOBIERNO REGIONAL','GOBIERNO NACIONAL','FONAFE']).all() or h[GROUP].isna().any():raise ValueError('Invalid institutional/component identifiers')
    primary=bundle['scenarios']['primary'];tertile=bundle['scenarios']['tertiles_sensitivity']
    expected_primary={'low':'Q<P25','medium':'P25<=Q<=P75','high':'Q>P75'}
    expected_tertile={'low':'Q<=P33','medium':'P33<Q<=P67','high':'Q>P67'}
    if primary['rules']!=expected_primary or tertile['rules']!=expected_tertile:raise ValueError('Unsupported exported tie rules')
    for name,scheme in [('primary',primary),('tertiles',tertile)]:
        cuts=scheme['cuts']
        if cuts is None or len(cuts)!=2 or not np.isfinite(cuts).all() or cuts[0]>=cuts[1]:raise ValueError('Invalid exported scenario cuts')
        low=h[Q]<cuts[0] if name=='primary' else h[Q]<=cuts[0]
        labels=np.where(low,'low',np.where(h[Q]>cuts[1],'high','medium'));h['scenario_'+name]=labels
        source='asymmetry_scenario' if name=='primary' else 'tertile_sensitivity_scenario'
        if source in h and not np.array_equal(h[source],labels):raise ValueError('Historical/exported scenario mismatch')
        if set(labels)!=set(SCENARIOS):raise ValueError('Empty historical scenario')
    dates=pd.to_datetime(h.source00_notice_date,errors='coerce')
    if dates.isna().any() or not dates.dt.year.between(2020,2025).all():raise ValueError('Invalid approved notice year')
    h['notice_year']=dates.dt.year
    return h


def load_sources(calibration,bundle_dir,simulation,validation):
    calibration=Path(calibration).resolve();bundle_dir=Path(bundle_dir).resolve();simulation=Path(simulation).resolve();validation=Path(validation).resolve()
    a=approved08();core,h,oof,sim,hashes=a.load_inputs(calibration,bundle_dir,simulation)
    manifest,h08=a.verify_manifest(validation,'08_run_manifest.json',core)
    if manifest['schema_version']!='2.0-separated-internal-and-marginal-oof' or manifest['input_hashes']!=hashes:raise ValueError('08/source provenance mismatch')
    a.verify_outputs(Path(validation),core)
    bundle,profiles,_=core.load_contract(bundle_dir);h=classify_history(h,bundle,2004)
    internal=json.loads((Path(validation)/'08_A_internal_diagnostics.json').read_text(encoding='utf-8'))
    marginal=json.loads((Path(validation)/'08_B_oof_marginal_evaluation.json').read_text(encoding='utf-8'))
    limits=json.loads((Path(validation)/'08_C_methodological_limits.json').read_text(encoding='utf-8'))
    if not marginal['joint_phase_sum_oof_validation'].startswith('NOT_AVAILABLE') or len(internal['configurations'])!=9:raise ValueError('Evidence scope mismatch')
    for key,v in sim['configurations'].items():
        if key not in internal['configurations']:raise ValueError('Missing 08 model/scenario')
        ref=internal['configurations'][key]['comparisons'][TARGET]['simulated']
        for field,source in [('mean','mean'),('median','median'),('std','std_dev'),('P90','P90'),('P95','P95')]:
            if not np.isclose(ref[field],v[source],rtol=1e-12,atol=1e-10):raise ValueError('07/08 statistic mismatch')
        for threshold in core.THRESHOLDS:
            if ref['exceed_'+str(threshold)]!=v['exceedances'][str(threshold)]:raise ValueError('07/08 exceedance mismatch')
    return core,h,bundle,sim,internal,marginal,limits,{**hashes,**h08}


def descriptive_group(part,describe):
    q=part[Q].to_numpy();return {'n':len(part),'components':part[GROUP].nunique(),
        'Q_min':float(q.min()),'Q_mean':float(q.mean()),'Q_median':float(np.median(q)),'Q_P90':float(np.quantile(q,.9)),'Q_max':float(q.max()),
        **describe(part[TARGET].to_numpy())}


def extreme_contrast(part,label,describe,min_records=2,min_components=1):
    low=part[part[label].eq('low')];high=part[part[label].eq('high')]
    counts={'n_low':len(low),'n_high':len(high),'components_low':low[GROUP].nunique(),'components_high':high[GROUP].nunique()}
    if len(low)<min_records or len(high)<min_records or low[GROUP].nunique()<min_components or high[GROUP].nunique()<min_components:return {**counts,'status':'INSUFFICIENT_SUPPORT','SD_ratio_high_low':None,'mean_difference_high_low':None,'SD_difference_high_low':None,'direction':None}
    a=describe(low[TARGET].to_numpy());b=describe(high[TARGET].to_numpy())
    if a['std']==0:return {**counts,'status':'UNDEFINED_ZERO_LOW_SD','SD_ratio_high_low':None,'mean_difference_high_low':b['mean']-a['mean'],'SD_difference_high_low':b['std']-a['std'],'direction':None}
    ratio=b['std']/a['std'];return {**counts,'status':'DESCRIPTIVE_DEFINED','SD_ratio_high_low':ratio,'mean_difference_high_low':b['mean']-a['mean'],'SD_difference_high_low':b['std']-a['std'],'direction':'higher' if ratio>1 else ('lower' if ratio<1 else 'equal')}


def bootstrap_contrasts(history,reps,seed,describe):
    if reps==0:return {'status':'NOT_REQUESTED','scope':'Descriptive point estimates only'}
    if reps<100:raise ValueError('At least 100 component-bootstrap replicates required')
    groups=sorted(history[GROUP].unique());indices={g:np.flatnonzero(history[GROUP].to_numpy()==g) for g in groups}
    rng=task_rng(seed,'historical_partition_contrasts');draws={s:[] for s in ['primary','tertiles']}
    for _ in range(reps):
        sampled=history.iloc[np.concatenate([indices[g] for g in rng.choice(groups,len(groups),replace=True)])]
        for scheme in draws:
            value=extreme_contrast(sampled,'scenario_'+scheme,describe)
            if value['SD_ratio_high_low'] is not None:draws[scheme].append(value['SD_ratio_high_low'])
    output={}
    for scheme,values in draws.items():
        supported=all(history.loc[history['scenario_'+scheme].eq(s),GROUP].nunique()>=20 for s in ['low','high']) and len(values)>=.9*reps and np.ptp(values)>0
        output[scheme]={'status':'POINTWISE_OBSERVATIONAL_INTERVAL' if supported else 'INSUFFICIENT_OR_DEGENERATE_SUPPORT','finite_replicates':len(values),'requested_replicates':reps,'SD_ratio_interval':np.quantile(values,[.025,.975]).tolist() if supported else None}
    return {'status':'COMPLETED','seed':seed,'task':'historical_partition_contrasts','components':len(groups),'results':output,
        'scope':'Whole globally sampled dependency components retain all members across scenarios and years. No simulated trajectories resampled. Pointwise observational uncertainty only; no causal or predictive robustness claim.'}


def model_comparisons(simulation):
    rows=[]
    for scenario in SCENARIOS:
        reference=simulation['configurations']['M2:scenario:'+scenario]
        for model in MODELS:
            v=simulation['configurations'][model+':scenario:'+scenario]
            row={'model':model,'scenario':scenario,'simulation_N':v['N'],'evidence':'INTERNAL_SIMULATION_COMPARISON','difference_convention':'model minus M2','precision_warnings':v['precision_diagnostics']}
            for field in ['mean','median','std_dev','P90','P95']:row[field]=v[field];row['difference_'+field]=v[field]-reference[field]
            for threshold in [30,45,60,75,90,120,150,180]:
                col='exceed_'+str(threshold);row[col]=v['exceedances'][str(threshold)];row['difference_'+col+'_pp']=100*(v['exceedances'][str(threshold)]-reference['exceedances'][str(threshold)])
            row['precision_warnings']=[v for v in v['precision_diagnostics'] if not v['pass']];rows.append(row)
    return rows


def composition(history,label,dimension):
    rows=[]
    for scenario,part in history.groupby(label):
        if dimension=='amount':
            x=part[AMOUNT].to_numpy();rows.append({'scenario':str(scenario),'dimension':'nominal_procedure_amount_PEN','n':len(part),'components':part[GROUP].nunique(),'minimum':float(x.min()),'median':float(np.median(x)),'mean':float(x.mean()),'P90':float(np.quantile(x,.9)),'maximum':float(x.max())})
        else:
            for value,group in part.groupby(dimension):rows.append({'scenario':str(scenario),'dimension':dimension,'category':str(value),'n':len(group),'components':group[GROUP].nunique(),'historical_fraction':len(group)/len(part),
                'support':'SPARSE_DESCRIPTIVE_ONLY' if len(group)<20 or group[GROUP].nunique()<20 else 'DESCRIPTIVE_REPORTED'})
    return rows


def build(history,bundle,simulation,internal,marginal,stage,reps,seed):
    describe=approved08().descriptive;scenario_rows=[];contrasts=[]
    for scheme in ['primary','tertiles']:
        label='scenario_'+scheme
        for scenario in SCENARIOS:scenario_rows.append({'scheme':scheme,'scenario':scenario,**descriptive_group(history[history[label].eq(scenario)],describe)})
        contrasts.append({'scheme':scheme,**extreme_contrast(history,label,describe)})
    bootstrap=bootstrap_contrasts(history,reps,seed,describe)
    dump(stage/'09_A_historical_scenarios.json',{'schema_version':VERSION,'cuts_and_rules':bundle['scenarios'],'groups':scenario_rows,'extreme_contrasts':contrasts,'bootstrap':bootstrap,
        'scope':'Historical partition sensitivity; different memberships and profile composition, not an isolated effect of Q. No invariance or hypothesis verdict.'})
    pd.DataFrame(scenario_rows).to_csv(stage/'09_A_historical_scenarios.csv',index=False)
    comparisons=model_comparisons(simulation);dump(stage/'09_B_model_comparisons.json',{'schema_version':VERSION,'reference':'M2','comparisons':comparisons,'scope':'Saved primary empirical mixtures only. Differences between separately fitted models are descriptive, not causal or equivalence tests.'})
    pd.DataFrame([{k:v for k,v in row.items() if k!='precision_warnings'} for row in comparisons]).to_csv(stage/'09_B_model_comparisons.csv',index=False)
    comp=[]
    for scheme in ['primary','tertiles']:
        for dimension in [GOV,'amount','notice_year',GROUP]:comp.extend({'scheme':scheme,**v} for v in composition(history,'scenario_'+scheme,dimension))
    dump(stage/'09_C_composition_support.json',{'schema_version':VERSION,'profiles':comp,'scope':'Historical code-level composition; equal empirical record weights. Nominal procedure amounts, no inflation adjustment or hypothetical standardization.'})
    years=[];year_composition=[]
    for year,part in history.groupby('notice_year'):
        years.append({'year':int(year),**descriptive_group(part,describe),'primary_extreme_contrast':extreme_contrast(part,'scenario_primary',describe,20,20)})
        for scenario,cell in part.groupby('scenario_primary'):
            if len(cell)>=2:years.append({'year':int(year),'scenario':scenario,**descriptive_group(cell,describe),'support':'SPARSE_DESCRIPTIVE_ONLY' if len(cell)<20 or cell[GROUP].nunique()<20 else 'DESCRIPTIVE_REPORTED'})
        for value,cell in part.groupby(GOV):year_composition.append({'year':int(year),'government':value,'n':len(cell),'components':cell[GROUP].nunique(),'fraction':len(cell)/len(part)})
    dump(stage/'09_D_temporal_descriptions.json',{'schema_version':VERSION,'years':years,'government_composition':year_composition,'scope':'2020–2025 pooled-cohort descriptive stability only; no temporal training, forecasting, prospective test or causal time effect.'})
    tail_rows=[]
    for key,entry in internal['configurations'].items():
        value=entry['comparisons'][TARGET];tail_rows.append({'configuration':key,'evidence':'INTERNAL_FIT_DISCREPANCY','difference_convention':'observed minus simulated',
            'difference_std_days':value['observed_minus_simulated']['std'],'difference_P90_days':value['observed_minus_simulated']['P90'],'difference_P95_days':value['observed_minus_simulated']['P95'],
            **{'difference_exceed_'+str(t)+'_pp':value['observed_minus_simulated']['exceed_'+str(t)] for t in [30,45,60,75,90,120,150,180]},'precision_warnings':entry['simulation_precision_warnings']})
    direction=[]
    for scenario in SCENARIOS:
        subset=[r for r in tail_rows if r['configuration'].endswith(':'+scenario)]
        for metric in ['difference_std_days','difference_P90_days','difference_P95_days']+['difference_exceed_'+str(t)+'_pp' for t in [30,45,60,75,90,120,150,180]]:
            values=[r[metric] for r in subset];direction.append({'scenario':scenario,'metric':metric,'same_sign_across_models':len(set(np.sign(values)))==1,'minimum':min(values),'maximum':max(values),
                'scope':'Descriptive sign consistency, not inferential invariance or practical equivalence.'})
    dump(stage/'09_E_saved_discrepancies.json',{'schema_version':VERSION,'discrepancies':tail_rows,'direction_summary':direction,'marginal_oof_evidence_separate':marginal,
        'scope':'Reuses 08 without selecting/recalibrating models to improve concordance. OOF TOTAL is separate from the phase sum.'})
    correlations={model:bundle['models'][model]['dependence'] for model in MODELS}
    dump(stage/'09_F_scope_limits.json',{'schema_version':VERSION,'residual_dependence':correlations,'dependence_experiment':'PENDING_INDEPENDENT_DESIGN_AND_AUTHORIZATION; no identity-copula comparison or new trajectories implemented.',
        'interpretation':'Residual correlations are conditional on the model profile. Small residual correlation does not imply marginal independence or negligible tail differences.',
        'limits':['Numerical uncertainty differs from observational, parameter and selection uncertainty','Approved convergence N applies only to original primary empirical mixtures','No new simulated terciles, fixed-profile interventions, alternative distributions, hypothetical populations or parameter draws','No causal effect or predictive robustness inferred from observed scenario/year differences','National/FONAFE support remains limited; M1-high individual SD precision warning preserved','No hypothesis decisions or arbitrary quality classifications']})


def verify_publication(folder,core):
    manifest=json.loads((folder/'09_run_manifest.json').read_text(encoding='utf-8'))
    expected={'09_A_historical_scenarios.json','09_A_historical_scenarios.csv','09_B_model_comparisons.json','09_B_model_comparisons.csv','09_C_composition_support.json','09_D_temporal_descriptions.json','09_E_saved_discrepancies.json','09_F_scope_limits.json'}
    if {v['path'] for v in manifest['outputs']}!=expected:raise ValueError('Incomplete sensitivity publication')
    for entry in manifest['outputs']:
        if Path(entry['path']).name!=entry['path'] or core.sha(folder/entry['path'])!=entry['sha256']:raise ValueError('Sensitivity output hash mismatch')
    a=json.loads((folder/'09_A_historical_scenarios.json').read_text());b=json.loads((folder/'09_B_model_comparisons.json').read_text());f=json.loads((folder/'09_F_scope_limits.json').read_text())
    if len(a['groups'])!=6 or len(b['comparisons'])!=9 or not f['dependence_experiment'].startswith('PENDING'):raise ValueError('Sensitivity scope mismatch')


def run(calibration,bundle_dir,simulation,validation,output_root,reps=0,seed=2026110309):
    output=Path(output_root).resolve()/'02_results/04_model_validation'
    if output.exists() or output.is_symlink():raise FileExistsError('Existing sensitivity output; use fresh root')
    core,history,bundle,sim,internal,marginal,limits,hashes=load_sources(calibration,bundle_dir,simulation,validation)
    script_hash=core.sha(__file__);start=time.perf_counter();output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.09_',dir=output.parent) as tmp:
        stage=Path(tmp);build(history,bundle,sim,internal,marginal,stage,reps,seed)
        if any(core.sha(p)!=h for p,h in hashes.items()) or core.sha(__file__)!=script_hash:raise ValueError('Protected source changed')
        dump(stage/'09_run_manifest.json',{'schema_version':VERSION,'input_hashes':hashes,'script_sha256':script_hash,'bootstrap_reps':reps,'seed':seed,'elapsed_seconds':time.perf_counter()-start,
            'outputs':[{'path':p.name,'bytes':p.stat().st_size,'sha256':core.sha(p)} for p in sorted(stage.iterdir())]})
        verify_publication(stage,core)
        if output.exists() or output.is_symlink():raise FileExistsError('Sensitivity output appeared')
        stage.rename(output)
    return output



def self_test():
    import unittest
    import copy
    from unittest import mock
    a=approved08();core=a.core06()
    def fixture(count=120):
        q=np.arange(count);h=pd.DataFrame({'procedure_code':[str(1000+i) for i in range(count)],Q:q,VERIFIED_Q:q,TARGET:(q%25+10).astype(float),GROUP:['D'+str(i//3) for i in range(count)],GOV:['GOBIERNO LOCAL']*(count-1)+['FONAFE'],AMOUNT:100.+q,'source00_notice_date':['2020-01-01']*count})
        primary=np.quantile(q,[.25,.75]).tolist();tertiles=[float(q[int(np.ceil(count/3))-1]),float(q[int(np.ceil(count*2/3))-1])]
        bundle={'scenarios':{'primary':{'cuts':primary,'rules':{'low':'Q<P25','medium':'P25<=Q<=P75','high':'Q>P75'}},'tertiles_sensitivity':{'cuts':tertiles,'rules':{'low':'Q<=P33','medium':'P33<Q<=P67','high':'Q>P67'}}},'models':{m:{'dependence':{'phase_order':['a','b','c'],'latent_correlation':np.eye(3).tolist()}} for m in MODELS}}
        h=classify_history(h,bundle);h['asymmetry_scenario']=h.scenario_primary;h['tertile_sensitivity_scenario']=h.scenario_tertiles
        configurations={};internal={}
        for model,offset in [('M1',1.),('M2',0.),('M4',-.5)]:
            for scenario in SCENARIOS:
                key=model+':scenario:'+scenario;part=h[h.scenario_primary.eq(scenario)];d=a.descriptive(part[TARGET]);v={'model':model,'scenario':scenario,'N':50,'exceedances':{str(t):d['exceed_'+str(t)] for t in core.THRESHOLDS},'precision_diagnostics':[{'metric':'std','halfwidth':.543690,'tolerance':.5,'pass':False}] if model=='M1' and scenario=='high' else []}
                for field,source in [('mean','mean'),('median','median'),('std_dev','std'),('P90','P90'),('P95','P95')]:v[field]=d[source]+offset
                configurations[key]=v;internal[key]={'comparisons':{TARGET:{'observed_minus_simulated':{k:-offset if not k.startswith('exceed_') else 0. for k in d}}},'simulation_precision_warnings':v['precision_diagnostics']}
        return h,bundle,{'configurations':configurations},{'configurations':internal},{'joint_phase_sum_oof_validation':'NOT_AVAILABLE','metrics':[]}
    class Tests(unittest.TestCase):
        def test_Q_identity_and_2004_ids(self):
            h,b,_,_,_=fixture(2004);self.assertEqual(len(classify_history(h,b,2004)),2004)
            altered=h.copy();altered[Q]=altered[TARGET]
            with self.assertRaisesRegex(ValueError,'verified'):classify_history(altered,b,2004)
            for bad in [h.iloc[:-1],pd.concat([h,h.iloc[[0]]])]:
                with self.assertRaises(ValueError):classify_history(bad,b,2004)
        def test_rules_ties_and_partition_coverage(self):
            h,b,_,_,_=fixture();h=h.iloc[:8].copy();h[Q]=[0,3,4,6,7,8,9,10];h[VERIFIED_Q]=h[Q];h=h.drop(columns=['asymmetry_scenario','tertile_sensitivity_scenario'])
            b['scenarios']['primary']['cuts']=[3,7];b['scenarios']['tertiles_sensitivity']['cuts']=[4,8]
            v=classify_history(h,b);self.assertEqual(v.scenario_primary.tolist(),['low','medium','medium','medium','medium','high','high','high']);self.assertEqual(v.scenario_tertiles.tolist(),['low','low','low','medium','medium','medium','high','high'])
            self.assertEqual(sum(len(g) for _,g in v.groupby('scenario_primary')),len(h))
        def test_statistics_and_degeneracy(self):
            v=a.descriptive(np.array([1.,30.,60.]));self.assertEqual(v['median'],30);self.assertEqual(v['exceed_30'],1/3)
            h,b,_,_,_=fixture();h[TARGET]=10.;v=extreme_contrast(h,'scenario_primary',a.descriptive);self.assertIsNone(v['SD_ratio_high_low']);self.assertEqual(v['status'],'UNDEFINED_ZERO_LOW_SD')
        def test_model_comparisons_and_N_invariance(self):
            _,_,sim,_,_=fixture();first=model_comparisons(sim)
            self.assertEqual(next(v for v in first if v['model']=='M1')['difference_mean'],1.)
            altered=copy.deepcopy(sim)
            for v in altered['configurations'].values():v['N']*=1000
            second=model_comparisons(altered)
            for x,y in zip(first,second):self.assertEqual({k:v for k,v in x.items() if k!='simulation_N'},{k:v for k,v in y.items() if k!='simulation_N'})
        def test_component_bootstrap_and_stream_order(self):
            h,_,_,_,_=fixture(240);one=bootstrap_contrasts(h,100,9,a.descriptive);task_rng(9,'unrelated').random(20);two=bootstrap_contrasts(h,100,9,a.descriptive);self.assertEqual(one,two)
            original=extreme_contrast;checked=[]
            def inspect_draw(sample,label,describe,*args):
                counts=pd.Series(sample.index).value_counts()
                for _,part in h.groupby(GROUP):self.assertEqual(len({int(counts.get(i,0)) for i in part.index}),1)
                checked.append(True);return original(sample,label,describe,*args)
            with mock.patch.dict(globals(),{'extreme_contrast':inspect_draw}):bootstrap_contrasts(h,100,9,a.descriptive)
            self.assertEqual(len(checked),200)
            # The imported audited component helper must duplicate all members
            # equally; the 09 sampler uses the same full-component construction.
            idx=a.component_draw(h,task_rng(9,'check'));counts=pd.Series(idx).value_counts()
            for _,part in h.groupby(GROUP):self.assertEqual(len({int(counts.get(i,0)) for i in part.index}),1)
        def test_support_and_temporal_validation(self):
            h,b,_,_,_=fixture();rows=composition(h,'scenario_primary',GOV);self.assertTrue(any(x.get('category')=='FONAFE' and x['support']=='SPARSE_DESCRIPTIVE_ONLY' for x in rows))
            h.loc[0,'source00_notice_date']='2026-01-01'
            with self.assertRaises(ValueError):classify_history(h,b)
        def test_loader_rejects_contracts_and_provenance(self):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(FileNotFoundError):load_sources(tmp,tmp,tmp,tmp)
            module=approved08();module.load_inputs=mock.Mock(return_value=(core,None,None,None,{'input':'hash'}));module.verify_manifest=mock.Mock(return_value=({'schema_version':'wrong','input_hashes':{}},{}))
            with mock.patch.dict(globals(),{'approved08':lambda:module}):
                with self.assertRaisesRegex(ValueError,'provenance'):load_sources('a','b','c','d')
        def test_actual_validation_manifest_rejection(self):
            h,b,sim,internal,marginal=fixture();module=approved08();module.load_inputs=mock.Mock(return_value=(core,h,None,sim,{'input':'hash'}))
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);file=root/'changed.json';file.write_text('changed');dump(root/'08_run_manifest.json',{'schema_version':'2.0-separated-internal-and-marginal-oof','input_hashes':{'input':'hash'},'outputs':[{'path':'changed.json','sha256':'0'*64}]})
                with mock.patch.dict(globals(),{'approved08':lambda:module}):
                    with self.assertRaisesRegex(ValueError,'hash'):load_sources(root,root,root,root)
                dump(root/'08_run_manifest.json',{'schema_version':'incompatible','input_hashes':{},'outputs':[]})
                with mock.patch.dict(globals(),{'approved08':lambda:module}):
                    with self.assertRaisesRegex(ValueError,'provenance'):load_sources(root,root,root,root)
        def test_no_simulation_or_fixed_verdict(self):
            text=Path(__file__).read_text(encoding='utf-8').split('def self_test():')[0]
            for token in ['simulate_profiles(', 'stats.levene', 'CONFIRMED (p', 'coefficients_abcd', 'lognorm.ppf']:self.assertNotIn(token,text)
        def test_publication_failure_and_scope(self):
            h,b,sim,internal,marginal=fixture()
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);protected=root/'protected';protected.write_text('intact');fingerprint=core.sha(protected)
                with mock.patch.dict(globals(),{'load_sources':lambda *args:(core,h,b,sim,internal,marginal,{}, {str(protected):fingerprint})}):
                    out=run(root,root,root,root,root/'success',100,9);verify_publication(out,core)
                    value=json.loads((out/'09_E_saved_discrepancies.json').read_text());self.assertEqual(value['marginal_oof_evidence_separate']['joint_phase_sum_oof_validation'],'NOT_AVAILABLE')
                    warning=next(v for v in value['discrepancies'] if v['configuration']=='M1:scenario:high')['precision_warnings'][0];self.assertEqual(warning['halfwidth'],.543690)
                    with self.assertRaises(FileExistsError):run(root,root,root,root,root/'success',100,9)
                    with mock.patch.dict(globals(),{'verify_publication':mock.Mock(side_effect=ValueError('deliberate publication failure'))}):
                        with self.assertRaisesRegex(ValueError,'deliberate'):run(root,root,root,root,root/'failure',100,9)
                    self.assertFalse((root/'failure/02_results/04_model_validation').exists());self.assertFalse(list((root/'failure/02_results').glob('.09_*')));self.assertEqual(core.sha(protected),fingerprint)
                    (out/'09_B_model_comparisons.csv').write_text('altered')
                    with self.assertRaisesRegex(ValueError,'hash'):verify_publication(out,core)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise RuntimeError('Synthetic sensitivity tests failed')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ['calibration-dir','bundle-dir','simulation-dir','validation-dir','output-root']:parser.add_argument('--'+option,type=Path)
    parser.add_argument('--bootstrap-reps',type=int,default=0,help='0 omits intervals; otherwise at least 100 component replicates')
    parser.add_argument('--seed',type=int,default=2026110309);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:return self_test()
    if any(getattr(args,k) is None for k in ['calibration_dir','bundle_dir','simulation_dir','validation_dir','output_root']):parser.error('All five directories required')
    print(run(args.calibration_dir,args.bundle_dir,args.simulation_dir,args.validation_dir,args.output_root,args.bootstrap_reps,args.seed))


PILOT_N = 50_000
PILOT_REPLICATES = 30
PILOT_SEED = 202611030901
PILOT_NAMESPACE = 'residual_dependence_pilot_v1:'
PILOT_SCHEMA = 'sixa-residual-dependence-pilot/1.0'
PILOT_THRESHOLDS = (30, 45, 60, 75, 90, 120, 150, 180)
PILOT_TOLERANCES = {
    'mean': .05, 'std': .10, 'median': .10, 'P90': .25, 'P95': .25,
    **{f'exceed_{threshold}': .10 for threshold in PILOT_THRESHOLDS},
}
PILOT_FAMILY_SIZE = 117


def pilot_statistics(total):
    quantiles = np.quantile(total, [.5, .9, .95], method='linear')
    return {
        'mean': float(np.mean(total)), 'std': float(np.std(total, ddof=1)),
        **dict(zip(('median', 'P90', 'P95'), map(float, quantiles))),
        **{f'exceed_{threshold}': float(np.mean(total > threshold))
           for threshold in PILOT_THRESHOLDS},
    }


def pilot_pair(core, profiles, model, configuration, replicate, n,
               order=('adjusted', 'identity')):
    from copy import deepcopy

    identity = deepcopy(model)
    identity['dependence']['latent_correlation'] = np.eye(3).tolist()
    key = PILOT_NAMESPACE + configuration
    weights = profiles.empirical_row_weight.to_numpy(float)
    selector = core.stream(PILOT_SEED, key + ':profiles', n, replicate)
    indices = selector.choice(len(profiles), size=n, p=weights / weights.sum())
    selected = profiles.iloc[indices]
    models = {'adjusted': model, 'identity': identity}
    statistics = {}
    integration = None
    for arm in order:
        rng = core.stream(PILOT_SEED, key + ':normals', n, replicate)
        phases = core.simulate_profiles(selected, models[arm], rng)
        if phases.shape != (n, 4) or not np.array_equal(
                phases[:, 3], phases[:, :3].sum(axis=1)):
            raise ValueError('Invalid phase sum from Script 06')
        if integration is None:
            integration = phases[:, 1].copy()
        elif not np.array_equal(integration, phases[:, 1]):
            raise ValueError('Integration differs under common random inputs')
        statistics[arm] = pilot_statistics(phases[:, 3])
        del phases
    differences = {
        metric: (statistics['adjusted'][metric] - statistics['identity'][metric])
        * (100 if metric.startswith('exceed_') else 1)
        for metric in PILOT_TOLERANCES
    }
    return {
        'configuration': configuration, 'replicate': replicate, 'N': n,
        'profile_stream': key + ':profiles', 'normal_stream': key + ':normals',
        **statistics, 'differences': differences,
    }


def pilot_precision(rows):
    from scipy.stats import t

    count = len(rows)
    critical = t.ppf([.975, 1 - .05 / (2 * PILOT_FAMILY_SIZE)], count - 1)
    metrics = {}
    for metric, tolerance in PILOT_TOLERANCES.items():
        values = np.array([row['differences'][metric] for row in rows])
        estimate = float(values.mean())
        sd = float(values.std(ddof=1))
        mcse = sd / np.sqrt(count)
        pointwise, simultaneous = critical * mcse
        degenerate = sd == 0
        metrics[metric] = {
            'mean_difference': estimate, 'sd_difference': sd, 'mcse': mcse,
            'unit': 'percentage_points' if metric.startswith('exceed_') else 'days',
            'pointwise_95': [estimate - pointwise, estimate + pointwise],
            'bonferroni_95': [estimate - simultaneous, estimate + simultaneous],
            'pointwise_halfwidth': pointwise, 'bonferroni_halfwidth': simultaneous,
            'tolerance': tolerance,
            'precision_status': ('DEGENERATE_REPLICATE_DIFFERENCES' if degenerate
                                 else 'MET' if simultaneous <= tolerance
                                 else 'PRECISION_NOT_REACHED'),
        }
    return metrics


def load_pilot_inputs(bundle_dir):
    core = approved08().core06()
    folder = Path(bundle_dir).resolve()
    bundle, profiles, hashes = core.load_contract(folder)
    if len(profiles) != 2004 or set(bundle['models']) != set(MODELS):
        raise ValueError('Pilot requires the approved cohort and model set')
    for model in bundle['models'].values():
        correlation = np.asarray(model['dependence']['latent_correlation'])
        if not np.array_equal(correlation[1], [0, 1, 0]) or not np.array_equal(
                correlation[:, 1], [0, 1, 0]):
            raise ValueError('Approved independent integration contract required')
    # Anchor the bundle to the hashes already recorded by the approved Stage 1.
    repository = Path(__file__).resolve().parents[2]
    stage_one = repository / ('02_results/reproducibility/'
                              'script09_real_20261103_stage1_01/02_results/'
                              '04_model_validation/09_run_manifest.json')
    if core.sha(stage_one) != '4ac0e6319f5b9e3d05f37ff33b090d98ae0d15d5e87e44a6f92a0431b704ff0a':
        raise ValueError('Approved Stage 1 provenance anchor changed')
    anchor = json.loads(stage_one.read_text(encoding='utf-8'))['input_hashes']
    for name, digest in hashes.items():
        if [value for path, value in anchor.items() if Path(path).name == name] != [digest]:
            raise ValueError(f'Unapproved pilot input: {name}')
    inputs = {str(folder / name): digest for name, digest in hashes.items()}
    inputs[str(stage_one)] = core.sha(stage_one)
    for script in [Path(__file__).resolve(),
                   repository / '01_scripts/03_stochastic_simulation/06_convergence_analysis.py',
                   Path(__file__).with_name('08_model_validation.py').resolve()]:
        inputs[str(script)] = core.sha(script)
    return core, bundle, profiles, inputs


def publish_pilot(output, core, inputs, replicas, summary):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.09_pilot_', dir=output.parent) as tmp:
        stage = Path(tmp)
        dump(stage / '09_stage2_replicates.json', replicas)
        dump(stage / '09_stage2_precision.json', summary)
        outputs = [{'path': path.name, 'sha256': core.sha(path), 'bytes': path.stat().st_size}
                   for path in sorted(stage.iterdir())]
        dump(stage / '09_stage2_manifest.json', {
            'schema_version': PILOT_SCHEMA, 'inputs': inputs, 'outputs': outputs,
        })
        manifest = json.loads((stage / '09_stage2_manifest.json').read_text(encoding='utf-8'))
        if any(core.sha(path) != digest for path, digest in manifest['inputs'].items()):
            raise ValueError('Pilot input changed before publication')
        for entry in manifest['outputs']:
            path = stage / entry['path']
            if core.sha(path) != entry['sha256'] or path.stat().st_size != entry['bytes']:
                raise ValueError('Pilot output integrity failure')
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        stage.rename(output)


def run_pilot(bundle_dir, output_root):
    import platform
    import scipy

    output = Path(output_root).resolve() / '02_results/04_model_validation_stage2'
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    started = time.perf_counter()
    core, bundle, profiles, inputs = load_pilot_inputs(bundle_dir)
    replicas = []
    results = {}
    for model in MODELS:
        for scenario in SCENARIOS:
            key = f'{model}:{scenario}'
            part = core.select_profiles(profiles, scenario)
            rows = [pilot_pair(core, part, bundle['models'][model], key, replicate, PILOT_N)
                    for replicate in range(PILOT_REPLICATES)]
            replicas.extend(rows)
            results[key] = pilot_precision(rows)
    if sum(map(len, results.values())) != PILOT_FAMILY_SIZE:
        raise ValueError('Pilot comparison family changed')
    summary = {
        'schema_version': PILOT_SCHEMA, 'seed': PILOT_SEED, 'namespace': PILOT_NAMESPACE,
        'N': PILOT_N, 'replicates': PILOT_REPLICATES, 'family_size': PILOT_FAMILY_SIZE,
        'difference': 'adjusted minus identity', 'configurations': results,
        'bundle_schema': bundle['schema_version'],
        'models': {name: {key: model[key] for key in ('model_sha256', 'dependence')}
                   for name, model in bundle['models'].items()},
        'identity_matrix': np.eye(3).tolist(),
        'versions': {'python': platform.python_version(), 'numpy': np.__version__,
                     'pandas': pd.__version__, 'scipy': scipy.__version__},
        'elapsed_seconds_before_publication': time.perf_counter() - started,
        'scope': ('Approximate Monte Carlo precision for fixed calibration. Finite-N '
                  'bias of SD and quantiles remains. One N does not establish population '
                  'convergence. Precision, structural effect and equivalence are distinct. '
                  'No historical inference, joint OOF validation or parameter uncertainty. '
                  'Any extension requires a separate authorized protocol.'),
    }
    publish_pilot(output, core, inputs, replicas, summary)
    return output


def pilot_cli():
    parser = argparse.ArgumentParser(description='Fixed paired residual dependence pilot')
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    print(run_pilot(args.bundle_dir, args.output_root))


if __name__ == '__main__':
    import sys

    if sys.argv[1:2] == ['stage2']:
        del sys.argv[1]
        pilot_cli()
    else:
        main()
