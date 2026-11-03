"""Internal schedule-distribution diagnostics and saved marginal grouped-CV evidence.

These evidence blocks do not provide joint out-of-sample validation of phase sums.
No recalibration, simulation, IID hypothesis decision or causal interpretation.
"""
import argparse
import json
import tempfile
import time
import platform
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

VERSION='2.0-separated-internal-and-marginal-oof'
TARGET='query_close_to_award_calendar_days'
PHASES=['absolution_calendar_days','integration_calendar_days','post_integration_calendar_days']
SCENARIOS=['low','medium','high']
MODELS=['M1','M2','M4']
GROUP='cv_dependency_group'
GOV='calibration_government'
THRESHOLDS=[30,45,60,75,90,120,150,180]


def core06():
    path=Path(__file__).parents[1]/'03_stochastic_simulation/06_convergence_analysis.py'
    import types
    module=types.ModuleType('approved_core06');module.__file__=str(path)
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),module.__dict__)
    return module


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def verify_manifest(folder,name,core):
    folder=Path(folder).resolve();path=folder/name;manifest=json.loads(path.read_text(encoding='utf-8'));hashes={str(path):core.sha(path)}
    if manifest.get('status','COMPLETE')!='COMPLETE':raise ValueError('Incomplete input publication')
    for entry in manifest['outputs']:
        file=(folder/entry['path']).resolve()
        if not file.is_relative_to(folder) or str(file) in hashes or core.sha(file)!=entry['sha256']:raise ValueError('Input manifest hash/path mismatch')
        hashes[str(file)]=entry['sha256']
    return manifest,hashes


def validate_links(history,profiles,oof,folds):
    ids=set(history.procedure_code)
    if len(ids)!=len(history) or history.procedure_code.isna().any() or len(profiles)!=len(history) or profiles.procedure_code.duplicated().any() or set(profiles.procedure_code)!=ids:raise ValueError('Duplicate/missing historical or profile IDs')
    required=[TARGET]+PHASES
    if not np.isfinite(history[required]).all().all() or history[required].lt(0).any().any() or not np.allclose(history[PHASES].sum(axis=1),history[TARGET],rtol=0,atol=0):raise ValueError('Historical phase identity invalid')
    if not history.date_nature.eq('published_schedule_not_verified_actual_events').all():raise ValueError('Unexpected historical date nature')
    indexed=history.set_index('procedure_code');p=profiles.set_index('procedure_code').reindex(indexed.index)
    for col in [GROUP,GOV,'source00_entity_code','cv_project_group','asymmetry_scenario']:
        if not indexed[col].astype(str).equals(p[col].astype(str)):raise ValueError('Historical/profile linkage mismatch: '+col)
    for col in ['queries_observations_count','source00_reference_amount']:
        if not np.allclose(indexed[col],p[col],rtol=1e-12,atol=1e-8):raise ValueError('Joint profile mismatch')
    cuts=history.queries_observations_count.quantile([.25,.75]).to_numpy()
    labels=np.where(history.queries_observations_count<cuts[0],'low',np.where(history.queries_observations_count>cuts[1],'high','medium'))
    if not np.array_equal(labels,history.asymmetry_scenario):raise ValueError('Historical scenario mismatch')
    if oof.duplicated(['procedure_code','model','outcome']).any() or set(oof.procedure_code)!=ids:raise ValueError('OOF duplicate/missing IDs')
    if not np.isfinite(oof[['observed','mean','median','p10','p90']]).all().all() or (oof.p10>oof.p90).any():raise ValueError('Invalid OOF predictions')
    if np.isnan(oof.log_score).any() or np.isposinf(oof.log_score).any():raise ValueError('Invalid OOF log score')
    for row in oof.itertuples(index=False):
        if row.outcome not in required or row.procedure_code not in indexed.index:raise ValueError('Unknown OOF outcome/ID')
        reference=indexed.loc[row.procedure_code]
        if row.observed!=reference[row.outcome] or row.fold!=reference.cv_fold or getattr(row,GROUP)!=reference[GROUP]:raise ValueError('OOF reference/fold mismatch')
        if getattr(row,GOV)!=reference[GOV] or row.notice_year!=pd.Timestamp(reference.source00_notice_date).year:raise ValueError('OOF subgroup mismatch')
    expected={'M0':required,'M1':required,'M2':required,'M3':required,'M4':required,'NESTED_SELECTED':required,**{m+'_noQ':[TARGET] for m in ['M2','M3','M4']}}
    if set(oof.model)!=set(expected):raise ValueError('OOF model contract mismatch')
    for model,outcomes in expected.items():
        part=oof[oof.model.eq(model)]
        if set(part.outcome)!=set(outcomes):raise ValueError('OOF outcome coverage mismatch')
        for outcome in outcomes:
            if set(part.loc[part.outcome.eq(outcome),'procedure_code'])!=ids:raise ValueError('OOF incomplete model/outcome')
    seen=set()
    for fold in folds:
        train=set(fold['training_procedure_codes']);held=set(fold['validation_procedure_codes'])
        if train&held or train|held!=ids or seen&held:raise ValueError('OOF partition coverage/leakage')
        for col in [GROUP,'source00_entity_code','cv_project_group']:
            if set(indexed.loc[list(train),col])&set(indexed.loc[list(held),col]):raise ValueError('OOF group leakage')
        if held!=set(history.loc[history.cv_fold.eq(fold['fold']),'procedure_code']):raise ValueError('OOF heldout assignment mismatch')
        for model,bundle in fold['bundles'].items():
            if set(bundle['training_procedure_codes'])!=train:raise ValueError('Fold model training mismatch')
        selected=oof[oof.fold.eq(fold['fold'])&oof.model.eq('NESTED_SELECTED')]
        if not selected.architecture.eq(fold['selected_architecture']).all():raise ValueError('Nested selected architecture mismatch')
        seen|=held
    if seen!=ids:raise ValueError('Missing OOF fold')


def load_inputs(calibration,bundle_dir,simulation):
    core=core06();calibration=Path(calibration);simulation=Path(simulation)
    _,h05=verify_manifest(calibration,'05_run_manifest.json',core);m07,h07=verify_manifest(simulation,'07_run_manifest.json',core)
    if m07['schema_version']!='2.0-conditional-orchestrator':raise ValueError('Unsupported Script 07 schema')
    required05=['05_1_classified_dataset.csv','05_3_model_parameters.json','05_5_out_of_fold_predictions.csv','05_6_nested_assignments.json']
    if any(str((calibration/name).resolve()) not in h05 for name in required05) or str((simulation/'07_2_simulation_summary.json').resolve()) not in h07:raise ValueError('Required input absent from manifest')
    spec=json.loads((calibration/'05_3_model_parameters.json').read_text(encoding='utf-8'))
    if spec['schema_version']!='3.0-nested-covariates' or spec['cross_validation']['kind']!='nested_component_grouped_3x3':raise ValueError('Unsupported nested calibration')
    bundle,profiles,bhash=core.load_contract(bundle_dir)
    if bundle['provenance']['calibration_parameters_sha256']!=core.sha(calibration/'05_3_model_parameters.json') or spec['input_sha256']!=bundle['provenance']['input_sha256'] or m07['inputs']!=bhash:raise ValueError('Calibration/07/bundle provenance mismatch')
    history=pd.read_csv(calibration/'05_1_classified_dataset.csv',dtype={'procedure_code':str,'source00_entity_code':str})
    oof=pd.read_csv(calibration/'05_5_out_of_fold_predictions.csv',dtype={'procedure_code':str,'source00_entity_code':str})
    folds=[]
    for entry in spec['cross_validation']['model_files']:
        if core.sha(calibration/entry['path'])!=entry['sha256']:raise ValueError('Fold hash mismatch')
        folds.append(json.loads((calibration/entry['path']).read_text(encoding='utf-8')))
    validate_links(history,profiles,oof,folds)
    splits=json.loads((calibration/'05_6_nested_assignments.json').read_text(encoding='utf-8'))['splits'];index=history.set_index('procedure_code')
    if {v['context'] for v in splits}!={'outer_1','outer_2','outer_3','full_training_selection'}:raise ValueError('Missing nested contexts')
    for context in {s['context'] for s in splits}:
        expected=set(history.procedure_code) if context=='full_training_selection' else set(history.loc[history.cv_fold.ne(int(context.split('_')[-1])),'procedure_code']);seen=[]
        for split in [s for s in splits if s['context']==context]:
            a=set(split['train_codes']);b=set(split['validation_codes'])
            if a&b or a|b!=expected or set(index.loc[list(a),GROUP])&set(index.loc[list(b),GROUP]):raise ValueError('Nested membership leakage')
            seen.extend(b)
        if set(seen)!=expected or len(seen)!=len(expected):raise ValueError('Nested coverage mismatch')
    summary=json.loads((simulation/'07_2_simulation_summary.json').read_text(encoding='utf-8'))
    if summary['schema_version']!=m07['schema_version'] or set(summary['configurations'])!={m+':scenario:'+s for m in MODELS for s in SCENARIOS}:raise ValueError('Incomplete 07 configurations')
    # Full lineage/row pass precedes any analytical calculation.
    index=profiles.set_index('procedure_code')
    for key,value in summary['configurations'].items():
        if str((simulation/value['trajectory_file']).resolve()) not in h07 or key!=value['model']+':scenario:'+value['scenario']:raise ValueError('Unmanifested/mislabeled trajectories')
        count=0
        for part in pd.read_csv(simulation/value['trajectory_file'],compression='gzip',chunksize=100000,dtype={'procedure_code':str,'source00_entity_code':str}):
            if not set(part.procedure_code)<=set(index.index):raise ValueError('Unknown simulated profile')
            origin=index.loc[part.procedure_code]
            if not part.model.eq(value['model']).all() or not part.scenario_primary.eq(value['scenario']).all() or not origin.asymmetry_scenario.eq(value['scenario']).all():raise ValueError('Simulation scenario mismatch')
            for col in [GROUP,'source00_entity_code','cv_project_group',GOV]:
                if not np.array_equal(part[col].to_numpy(),origin[col].to_numpy()):raise ValueError('Trajectory lineage mismatch')
            for col in ['queries_observations_count','source00_reference_amount']:
                if not np.allclose(part[col],origin[col],rtol=1e-12,atol=1e-8):raise ValueError('Trajectory covariate mismatch')
            if not np.array_equal(part.simulation_id,np.arange(count,count+len(part))):raise ValueError('Trajectory ID/count mismatch')
            phases=part[['stage1_absolution_days','stage2_integration_days','stage3_post_integration_days']].to_numpy()
            if not np.isfinite(phases).all() or (phases<0).any() or not np.allclose(phases.sum(axis=1),part.total_duration_days,rtol=1e-12,atol=1e-10):raise ValueError('Trajectory sum invalid')
            count+=len(part)
        if count!=value['N']:raise ValueError('Trajectory cardinality mismatch')
    hashes={**h05,**h07,**{str(Path(bundle_dir)/k):v for k,v in bhash.items()}}
    return core,history,oof,summary,hashes


def descriptive(x):
    x=np.asarray(x,float)
    if len(x)<2 or not np.isfinite(x).all():raise ValueError('Invalid descriptive sample')
    return {'mean':float(x.mean()),'median':float(np.quantile(x,.5)),'std':float(x.std(ddof=1)),
        'P90':float(np.quantile(x,.9)),'P95':float(np.quantile(x,.95)),
        **{'exceed_'+str(t):float(np.mean(x>t)) for t in THRESHOLDS}}


def ecdf_distance(observed,simulated):
    a=np.sort(observed);b=np.sort(simulated);d=0.
    for grid in [np.unique(a),np.unique(b)]:
        # Chunk grids to avoid a combined multi-million-row allocation.
        for start in range(0,len(grid),100000):
            x=grid[start:start+100000]
            d=max(d,float(np.max(np.abs(np.searchsorted(a,x,side='right')/len(a)-np.searchsorted(b,x,side='right')/len(b)))))
    return d


def compare(observed,simulated):
    a=descriptive(observed);b=descriptive(simulated)
    return {'observed':a,'simulated':b,'observed_minus_simulated':{k:(a[k]-b[k])*(100 if k.startswith('exceed_') else 1) for k in a},
        'difference_units':'days for temporal statistics; percentage points for exceedances',
        'ecdf_sup_distance':ecdf_distance(observed,simulated),'wasserstein_days':float(stats.wasserstein_distance(observed,simulated)),
        'observed_zero_fraction':float(np.mean(np.asarray(observed)==0)),'simulated_zero_fraction':float(np.mean(np.asarray(simulated)==0))}


def component_draw(history,rng):
    groups=sorted(history[GROUP].unique());mapping={g:np.flatnonzero(history[GROUP].to_numpy()==g) for g in groups}
    return np.concatenate([mapping[g] for g in rng.choice(groups,len(groups),replace=True)])


def observational_bootstrap(history,reps,seed):
    if reps<100:raise ValueError('At least 100 bootstrap replicates required')
    rng=np.random.default_rng(seed);values={s:[] for s in SCENARIOS}
    groups=sorted(history[GROUP].unique());group_rows={g:np.flatnonzero(history[GROUP].to_numpy()==g) for g in groups}
    for _ in range(reps):
        sampled=history.iloc[np.concatenate([group_rows[g] for g in rng.choice(groups,len(groups),replace=True)])]
        for s in SCENARIOS:
            x=sampled.loc[sampled.asymmetry_scenario.eq(s),TARGET].to_numpy()
            if len(x)>=2:values[s].append(descriptive(x))
    output={}
    for s in SCENARIOS:
        part=history[history.asymmetry_scenario.eq(s)];rows=values[s];supported=part[GROUP].nunique()>=20 and len(rows)>=.9*reps
        output[s]={'components':int(part[GROUP].nunique()),'finite_replicates':len(rows),'requested_replicates':reps,'status':'SUPPORTED_CONDITIONAL_OBSERVATIONAL' if supported else 'INSUFFICIENT_SUPPORT',
            'intervals':{k:np.quantile([r[k] for r in rows],[.025,.975]).tolist() for k in rows[0] if np.ptp([r[k] for r in rows])>0} if supported else {},
            'degenerate_metrics_without_interval':[k for k in rows[0] if np.ptp([r[k] for r in rows])==0] if rows else [],
            'scope':'Whole dependency components sampled globally with replacement, retaining every member across scenarios. Pointwise historical intervals conditional on fixed fitted model and available simulation; not complete calibration/selection uncertainty.'}
    return output


def oof_metrics(oof):
    rows=[]
    for (model,outcome),part in oof.groupby(['model','outcome']):
        score=part.log_score.to_numpy();rows.append({'model':model,'role':'nested_selection_procedure' if model=='NESTED_SELECTED' else 'fixed_candidate_or_ablation',
            'outcome':outcome,'n':len(part),'components':part[GROUP].nunique(),'MAE_median':float(np.mean(np.abs(part.observed-part['median']))),
            'bias_predicted_minus_observed_days':float((part['mean']-part.observed).mean()),
            'coverage80':float(((part.observed>=part.p10)&(part.observed<=part.p90)).mean()),
            'below_p10':float((part.observed<part.p10).mean()),'above_p90':float((part.observed>part.p90).mean()),
            'unsupported_log_scores':int((~np.isfinite(score)).sum()),'mean_log_score':float(score.mean()) if np.isfinite(score).all() else None,
            'scope':'Saved marginal grouped cross-validation inside previously explored cohort. TOTAL is separately fitted, not the joint phase sum. Not external/prospective validation.'})
    return rows


def build_outputs(history,oof,simulation_summary,simulation_dir,stage,reps,seed):
    boot=observational_bootstrap(history,reps,seed);internal={};flat=[];ecdf_rows=[]
    for key,value in simulation_summary['configurations'].items():
        reference=history[history.asymmetry_scenario.eq(value['scenario'])];comparisons={}
        for variable,col in [(TARGET,'total_duration_days')]+list(zip(PHASES,['stage1_absolution_days','stage2_integration_days','stage3_post_integration_days'])):
            arrays=[part[col].to_numpy() for part in pd.read_csv(Path(simulation_dir)/value['trajectory_file'],compression='gzip',usecols=[col],chunksize=100000)]
            simulated=np.concatenate(arrays);del arrays
            observed=reference[variable].to_numpy();result=compare(observed,simulated)
            if variable==TARGET:
                for metric,bounds in boot[value['scenario']]['intervals'].items():
                    multiplier=100 if metric.startswith('exceed_') else 1
                    result.setdefault('conditional_difference_intervals',{})[metric]=[(x-result['simulated'][metric])*multiplier for x in bounds]
            comparisons[variable]=result
            flat.append({'configuration':key,'variable':variable,**result['observed_minus_simulated'],'ecdf_sup_distance':result['ecdf_sup_distance'],'wasserstein_days':result['wasserstein_days'],'historical_n':len(reference)})
            # Exact ECDF at observed knots. Supremum uses both complete supports;
            # this compact table is not an approximation used for distances.
            ordered=np.sort(simulated)
            for knot in np.unique(observed):ecdf_rows.append({'configuration':key,'variable':variable,'knot':float(knot),'observed_ecdf':float(np.mean(observed<=knot)),'simulated_ecdf':float(np.searchsorted(ordered,knot,side='right')/len(ordered))})
            del simulated,ordered
        internal[key]={'evidence':'INTERNAL_FIT_DIAGNOSTIC_PHASE_SUM','historical_n':len(reference),'simulated_n':value['N'],
            'comparisons':comparisons,'simulation_precision_warnings':[r for r in value['precision_diagnostics'] if not r['pass']]}
    write_json(stage/'08_A_internal_diagnostics.json',{'schema_version':VERSION,'configurations':internal,'observational_bootstrap':boot,
        'global_aggregation':'Not produced. Any future global comparison must weight scenarios 476/2004,1043/2004,485/2004, separately per model; never by simulation N.'})
    pd.DataFrame(flat).to_csv(stage/'08_A_internal_differences.csv',index=False);pd.DataFrame(ecdf_rows).to_csv(stage/'08_A_ecdf_at_observed_knots.csv',index=False)
    metrics=oof_metrics(oof);subgroups=[]
    for column in [GOV,'notice_year']:
        for label,part in oof.groupby(column):
            for row in oof_metrics(part):
                supported=row['n']>=20 and row['components']>=20
                if not supported:
                    for field in ['MAE_median','bias_predicted_minus_observed_days','coverage80','below_p10','above_p90','mean_log_score']:row[field]=None
                subgroups.append({column:str(label),**row,'support_status':'DESCRIPTIVE_SUPPORTED' if supported else 'INSUFFICIENT_SUPPORT_NO_ROBUST_CONCLUSION'})
    write_json(stage/'08_B_oof_marginal_evaluation.json',{'schema_version':VERSION,'metrics':metrics,'subgroups':subgroups,'subgroup_support_policy':'At least 20 observations and 20 components to report subgroup metrics; descriptive reporting safeguard, not proof of representativeness. Sparse subgroup metrics suppressed.', 'joint_phase_sum_oof_validation':'NOT_AVAILABLE; saved fold models do not contain joint copulas. No full-cohort copula borrowed.'})
    pd.DataFrame(metrics).to_csv(stage/'08_B_oof_metrics.csv',index=False)
    write_json(stage/'08_C_methodological_limits.json',{'schema_version':VERSION,'evidence_A':'Internal reproduction of historical published-schedule distributions with full-cohort fitted simulation.',
        'evidence_B':'Previously saved marginal grouped cross-validation; fixed candidates distinct from nested selection.',
        'evidence_C':'Joint out-of-sample phase-sum validation unavailable.',
        'warnings':['Simulated trajectories are not new observed procurement units','No IID real-versus-simulation hypothesis tests or predetermined scientific decision','Observational intervals hold fitted model and simulation fixed','Nominal amounts and sparse institutional cells limit generalization','M1 high SD halfwidth 0.543690 days exceeds 0.500000; preserved without reseeding','No global model pooling; no causal or actual-duration interpretation']})


def verify_outputs(folder,core):
    manifest=json.loads((folder/'08_run_manifest.json').read_text(encoding='utf-8'))
    expected={'08_A_internal_diagnostics.json','08_A_internal_differences.csv','08_A_ecdf_at_observed_knots.csv','08_B_oof_marginal_evaluation.json','08_B_oof_metrics.csv','08_C_methodological_limits.json'}
    if {v['path'] for v in manifest['outputs']}!=expected:raise ValueError('Incomplete validation publication')
    for entry in manifest['outputs']:
        path=folder/entry['path']
        if Path(entry['path']).name!=entry['path'] or core.sha(path)!=entry['sha256']:raise ValueError('Validation output hash mismatch')
    a=json.loads((folder/'08_A_internal_diagnostics.json').read_text());b=json.loads((folder/'08_B_oof_marginal_evaluation.json').read_text())
    if len(a['configurations'])!=9 or not b['joint_phase_sum_oof_validation'].startswith('NOT_AVAILABLE'):raise ValueError('Evidence separation failure')


def run(calibration,bundle_dir,simulation,output_root,reps=2000,seed=2026110308):
    output=Path(output_root).resolve()/'02_results/04_model_validation'
    if output.exists() or output.is_symlink():raise FileExistsError('Existing validation results; use fresh output root')
    core,history,oof,summary,hashes=load_inputs(calibration,bundle_dir,simulation);start=time.perf_counter();script_hash=core.sha(__file__)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.08_',dir=output.parent) as tmp:
        stage=Path(tmp);build_outputs(history,oof,summary,simulation,stage,reps,seed)
        if any(core.sha(path)!=value for path,value in hashes.items()) or core.sha(__file__)!=script_hash:raise ValueError('Protected input/code changed')
        write_json(stage/'08_run_manifest.json',{'schema_version':VERSION,'script_sha256':script_hash,'input_hashes':hashes,'bootstrap_reps':reps,'seed':seed,
            'elapsed_seconds':time.perf_counter()-start,'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__},
            'outputs':[{'path':p.name,'bytes':p.stat().st_size,'sha256':core.sha(p)} for p in sorted(stage.iterdir())]})
        verify_outputs(stage,core)
        if output.exists() or output.is_symlink():raise FileExistsError('Validation output appeared')
        stage.rename(output)
    return output



def self_test():
    import unittest
    import copy
    from unittest import mock
    core=core06()
    def fixtures():
        n=120;scenario=np.tile(SCENARIOS,40);q=np.tile([1,10,40],40);ids=[str(100+i) for i in range(n)]
        a=np.arange(n)%8+2.;b=np.zeros(n);b[0]=2;c=np.arange(n)%13+5.
        h=pd.DataFrame({'procedure_code':ids,'source00_entity_code':['E'+str(i//3) for i in range(n)],'cv_project_group':['P'+str(i//3) for i in range(n)],GROUP:['D'+str(i//3) for i in range(n)],GOV:['GOBIERNO LOCAL']*n,
            'asymmetry_scenario':scenario,'queries_observations_count':q,'source00_reference_amount':np.arange(n)+100.,TARGET:a+b+c,PHASES[0]:a,PHASES[1]:b,PHASES[2]:c,'cv_fold':np.repeat(np.arange(40)%3+1,3),'date_nature':'published_schedule_not_verified_actual_events','source00_notice_date':['2020-01-01']*n})
        # Q boundaries are P25=1 and P75=40 for repeated values, so use the
        # exported primary mapping independently below for linkage tests.
        h['queries_observations_count']=np.arange(n);cuts=h.queries_observations_count.quantile([.25,.75]).to_numpy();h['asymmetry_scenario']=np.where(h.queries_observations_count<cuts[0],'low',np.where(h.queries_observations_count>cuts[1],'high','medium'))
        rows=[];folds=[]
        for f in [1,2,3]:
            held=h[h.cv_fold.eq(f)];train=h[h.cv_fold.ne(f)];bundles={}
            for model in ['M0','M1','M2','M3','M4','NESTED_SELECTED','M2_noQ','M3_noQ','M4_noQ']:
                if model!='NESTED_SELECTED':bundles[model]={'training_procedure_codes':train.procedure_code.tolist()}
                for outcome in ([TARGET] if model.endswith('_noQ') else [TARGET]+PHASES):
                    for row in held.to_dict('records'):
                        y=row[outcome];rows.append({'procedure_code':row['procedure_code'],'model':model,'architecture':'M2' if model=='NESTED_SELECTED' else model,'outcome':outcome,'observed':y,'mean':y+1,'median':y,'p10':max(0,y-2),'p90':y+2,'log_score':-1.,'fold':f,GROUP:row[GROUP],GOV:row[GOV],'notice_year':2020})
            folds.append({'fold':f,'selected_architecture':'M2','training_procedure_codes':train.procedure_code.tolist(),'validation_procedure_codes':held.procedure_code.tolist(),'bundles':bundles})
        return h,h.copy(),pd.DataFrame(rows),folds
    class Tests(unittest.TestCase):
        def test_known_distances_ecdf_and_exceedances(self):
            v=compare(np.array([0.,1.,2.]),np.array([1.,2.,3.]));self.assertEqual(v['observed_minus_simulated']['mean'],-1.)
            self.assertAlmostEqual(v['wasserstein_days'],1.);self.assertAlmostEqual(v['ecdf_sup_distance'],1/3)
            self.assertEqual(descriptive([30.,30.,60.])['exceed_30'],1/3)
        def test_distribution_invariant_to_simulation_replication(self):
            a=np.array([0.,1.,3.]);b=np.array([0.,2.,5.])
            self.assertAlmostEqual(ecdf_distance(a,b),ecdf_distance(a,np.tile(b,20)))
            self.assertAlmostEqual(stats.wasserstein_distance(a,b),stats.wasserstein_distance(a,np.tile(b,20)))
            # Global mixture weights must come from historical support, not N.
            def weighted_rate(parts,weights):return sum(w*np.mean(x>1) for x,w in zip(parts,weights))
            self.assertEqual(weighted_rate([a,b],[.25,.75]),weighted_rate([np.tile(a,30),np.tile(b,2)],[.25,.75]))
        def test_oof_known_metrics(self):
            h,p,o,f=fixtures();v=oof_metrics(o);self.assertTrue(all(x['MAE_median']==0 and x['bias_predicted_minus_observed_days']==1 and x['coverage80']==1 for x in v))
            self.assertTrue(all(x['below_p10']==0 and x['above_p90']==0 for x in v))
            o.loc[0,'log_score']=-np.inf;self.assertTrue(any(x['mean_log_score'] is None for x in oof_metrics(o)))
        def test_links_and_corruptions(self):
            h,p,o,f=fixtures();validate_links(h,p,o,f)
            for mutation in ['duplicate','missing','scenario','observed','fold','profile','nested']:
                a,b,c,d=h.copy(),p.copy(),o.copy(),copy.deepcopy(f)
                if mutation=='duplicate':c=pd.concat([c,c.iloc[[0]]],ignore_index=True)
                elif mutation=='missing':c=c.iloc[1:]
                elif mutation=='scenario':a.loc[0,'asymmetry_scenario']='wrong'
                elif mutation=='observed':c.loc[0,'observed']+=1
                elif mutation=='fold':c.loc[0,'fold']=99
                elif mutation=='profile':b.loc[0,'source00_reference_amount']+=1
                else:d[0]['selected_architecture']='M4'
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_links(a,b,c,d)
        def test_component_members_never_split(self):
            h,_,_,_=fixtures();index=component_draw(h,np.random.default_rng(8));counts=pd.Series(index).value_counts()
            for _,part in h.groupby(GROUP):self.assertEqual(len({int(counts.get(i,0)) for i in part.index}),1)
        def test_bootstrap_support_and_degeneracy(self):
            h,_,_,_=fixtures();a=observational_bootstrap(h,100,10);b=observational_bootstrap(h,100,10);self.assertEqual(a,b)
            h[TARGET]=10.;result=observational_bootstrap(h,100,10)
            self.assertTrue(all(not x['intervals'] for x in result.values()))
            self.assertTrue(all(x['degenerate_metrics_without_interval'] for x in result.values()))
        def test_loader_rejects_real_manifest_and_schema_routes(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);cal=root/'cal';sim=root/'sim';cal.mkdir();sim.mkdir()
                for folder,name in [(cal,'05_run_manifest.json'),(sim,'07_run_manifest.json')]:
                    write_json(folder/name,{'status':'COMPLETE','schema_version':'incompatible','outputs':[]})
                with self.assertRaisesRegex(ValueError,'Script 07 schema'):load_inputs(cal,root/'bundle',sim)
                write_json(sim/'07_run_manifest.json',{'schema_version':'2.0-conditional-orchestrator','outputs':[]})
                write_json(cal/'05_3_model_parameters.json',{'schema_version':'wrong','cross_validation':{'kind':'wrong'}})
                for name in ['05_1_classified_dataset.csv','05_5_out_of_fold_predictions.csv','05_6_nested_assignments.json']:(cal/name).write_text('synthetic')
                (sim/'07_2_simulation_summary.json').write_text('synthetic')
                write_json(cal/'05_run_manifest.json',{'outputs':[{'path':x.name,'sha256':core.sha(x)} for x in cal.iterdir() if x.name!='05_run_manifest.json']})
                write_json(sim/'07_run_manifest.json',{'schema_version':'2.0-conditional-orchestrator','outputs':[{'path':'07_2_simulation_summary.json','sha256':core.sha(sim/'07_2_simulation_summary.json')}]})
                with self.assertRaisesRegex(ValueError,'nested calibration'):load_inputs(cal,root/'bundle',sim)
                write_json(cal/'05_run_manifest.json',{'outputs':[{'path':'05_3_model_parameters.json','sha256':'0'*64}]})
                with self.assertRaisesRegex(ValueError,'hash'):load_inputs(cal,root/'bundle',sim)
        def test_manifest_hash_and_paths(self):
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);(folder/'a').write_text('ok');write_json(folder/'manifest.json',{'outputs':[{'path':'a','sha256':core.sha(folder/'a')}]});verify_manifest(folder,'manifest.json',core)
                (folder/'a').write_text('bad')
                with self.assertRaises(ValueError):verify_manifest(folder,'manifest.json',core)
        def test_no_old_inference_decisions(self):
            text=Path(__file__).read_text(encoding='utf-8').split('def self_test():')[0]
            self.assertNotIn('ttest_ind',text);self.assertNotIn('ks_2samp',text);self.assertNotIn('stats.levene',text);self.assertNotIn('H1 ACCEPTED',text)
        def test_publication_evidence_precision_and_failure(self):
            h,p,o,f=fixtures()
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);sim=root/'simulation';sim.mkdir();configs={}
                stagecols=['stage1_absolution_days','stage2_integration_days','stage3_post_integration_days']
                for model in MODELS:
                    for scenario in SCENARIOS:
                        part=h[h.asymmetry_scenario.eq(scenario)];file=sim/(model+'_'+scenario+'.csv.gz')
                        frame=part[PHASES+[TARGET]].rename(columns=dict(zip(PHASES,stagecols))|{TARGET:'total_duration_days'});frame.to_csv(file,index=False,compression='gzip')
                        warn=[{'metric':'std','halfwidth':.543690,'tolerance':.5,'pass':False}] if model=='M1' and scenario=='high' else []
                        configs[model+':scenario:'+scenario]={'model':model,'scenario':scenario,'N':len(frame),'trajectory_file':file.name,'precision_diagnostics':warn}
                protected=sim/'protected';protected.write_text('intact');fingerprint=core.sha(protected)
                with mock.patch.dict(globals(),{'load_inputs':lambda *a:(core,h,o,{'configurations':configs},{str(protected):fingerprint})}):
                    out=run(root,root,sim,root/'success',100);verify_outputs(out,core)
                    a=json.loads((out/'08_A_internal_diagnostics.json').read_text());b=json.loads((out/'08_B_oof_marginal_evaluation.json').read_text())
                    self.assertEqual(a['configurations']['M1:scenario:high']['simulation_precision_warnings'][0]['halfwidth'],.543690)
                    self.assertTrue(b['joint_phase_sum_oof_validation'].startswith('NOT_AVAILABLE'))
                    with self.assertRaises(FileExistsError):run(root,root,sim,root/'success',100)
                    with mock.patch.dict(globals(),{'verify_outputs':mock.Mock(side_effect=ValueError('deliberate publication failure'))}):
                        with self.assertRaisesRegex(ValueError,'deliberate'):run(root,root,sim,root/'failure',100)
                    self.assertFalse((root/'failure/02_results/04_model_validation').exists());self.assertFalse(list((root/'failure/02_results').glob('.08_*')))
                    self.assertEqual(fingerprint,core.sha(protected))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise RuntimeError('Synthetic validation tests failed')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['calibration-dir','bundle-dir','simulation-dir','output-root']:parser.add_argument('--'+name,type=Path)
    parser.add_argument('--bootstrap-reps',type=int,default=2000);parser.add_argument('--seed',type=int,default=2026110308);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:return self_test()
    if any(getattr(args,k) is None for k in ['calibration_dir','bundle_dir','simulation_dir','output_root']):parser.error('All four directories required')
    print(run(args.calibration_dir,args.bundle_dir,args.simulation_dir,args.output_root,args.bootstrap_reps,args.seed))

if __name__=='__main__':main()
