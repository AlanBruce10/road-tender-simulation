"""Conditional Monte Carlo orchestration of three correlated schedule intervals.

Physical legacy filename retained. No independent DES engine or recalibration.
Only empirical primary Q mixtures inherit the verified Script 06 decisions.
"""
import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd

VERSION='2.0-conditional-orchestrator'
MODELS=['M1','M2','M4']
SCENARIOS=['low','medium','high']
STAGES=['stage1_absolution_days','stage2_integration_days','stage3_post_integration_days']


def load_core(path=None):
    path=Path(path) if path else Path(__file__).with_name('06_convergence_analysis.py')
    # Source execution avoids pycache writes and never invokes __main__.
    spec=importlib.util.spec_from_loader('thesis06_core',loader=None,origin=str(path))
    module=importlib.util.module_from_spec(spec);module.__file__=str(path)
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),module.__dict__)
    return module


def write_json(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def load_decisions(core,bundle_folder,initial,supplement):
    bundle,data,inputs=core.load_contract(bundle_folder)
    if len(data)!=2004:raise ValueError('Approved cohort must contain 2,004 profiles')
    resolved={};provenance=[]
    for protocol,folder in [('initial',Path(initial)),('supplement',Path(supplement))]:
        result=core.verify_publication(folder)
        if result.get('schema_version')!=core.VERSION:raise ValueError('Convergence schema mismatch')
        recorded_protocol=result.get('protocol','initial')
        recorded_plan=result.get('plan',core.protocol_plan('initial'))
        if recorded_protocol!=protocol or recorded_plan!=core.protocol_plan(protocol):raise ValueError('Convergence protocol/plan mismatch')
        expected_seed=20251025 if protocol=='initial' else 2026110306
        if result['seed']!=expected_seed or result.get('stream_namespace','')!=('' if protocol=='initial' else 'supplement_v1:'):raise ValueError('Convergence stream provenance mismatch')
        if result['inputs']!=inputs:raise ValueError('Convergence uses a different calibration bundle')
        if protocol=='supplement' and result.get('chunk_size')!=100000:raise ValueError('Supplement block contract mismatch')
        if protocol=='initial' and result.get('chunk_size') is not None:raise ValueError('Initial block contract mismatch')
        fingerprint=core.sha(folder/'06_run_manifest.json')
        provenance.append({'protocol':protocol,'directory':str(folder.resolve()),'manifest_sha256':fingerprint})
        for key,decision in result['decisions'].items():
            model,tag,scenario=key.split(':')
            if model not in MODELS or tag!='scenario' or scenario not in SCENARIOS:raise ValueError('Unknown convergence configuration')
            if decision['status']=='PRECISION_REACHED':
                if decision['recommended_N'] is None or not decision['larger_size_confirmation']:raise ValueError('Unconfirmed convergence recommendation')
                if key in resolved:raise ValueError('Ambiguous convergence recommendation')
                resolved[key]={'N':decision['recommended_N'],'protocol':protocol,'directory':str(folder.resolve()),'manifest_sha256':fingerprint}
    # Acceptance contract checks approved values; actual N always comes from
    # hash-verified decisions, never this independent guard or a fallback.
    accepted={'M1':[50000,150000,500000],'M2':[50000,500000,2000000],'M4':[50000,250000,2000000]}
    if set(resolved)!={m+':scenario:'+s for m in MODELS for s in SCENARIOS}:raise ValueError('Missing certified configuration')
    for model,values in accepted.items():
        for scenario,expected in zip(SCENARIOS,values):
            if resolved[model+':scenario:'+scenario]['N']!=expected:raise ValueError('Decision differs from approved convergence outcome')
    return bundle,data,inputs,resolved,provenance


def summary(total,core):
    rows=core.precision_metrics(total)
    for row in rows:
        if not np.isfinite(row['halfwidth']):
            row['halfwidth']=None;row['precision_status']='UNBOUNDED_ORDER_STATISTIC_INTERVAL';row['pass']=False
    return {'N':len(total),'mean':float(np.mean(total)),'median':float(np.quantile(total,.5)),
            'std_dev':float(np.std(total,ddof=1)),'P90':float(np.quantile(total,.9)),'P95':float(np.quantile(total,.95)),
            'exceedances':{str(t):float(np.mean(total>t)) for t in core.THRESHOLDS},
            'precision_diagnostics':rows,'precision_scope':'Single production-run diagnostics; accepted N does not guarantee every future replicate meets all targets.'}


def configuration_stream(core,seed,model,scenario,n):
    if model not in MODELS or scenario not in SCENARIOS:raise ValueError('Invalid model/scenario')
    return core.stream(seed,'script07_v1:'+model+':scenario:'+scenario,n,0)


def simulate_configuration(core,bundle,data,model,scenario,n,seed,chunk_size,trajectory_path):
    if model not in MODELS or scenario not in SCENARIOS:raise ValueError('Invalid model/scenario')
    if not isinstance(n,int) or n<2 or not isinstance(chunk_size,int) or chunk_size<=0:raise ValueError('Invalid N/block size')
    part=core.select_profiles(data,scenario);weights=part.empirical_row_weight.to_numpy(float);weights/=weights.sum()
    rng=configuration_stream(core,seed,model,scenario,n)
    # All profile selections precede normal draws, matching the core sampling
    # sequence. The same indices are reused across chunks, never Q alone.
    indices=rng.choice(len(part),n,p=weights);total=np.empty(n)
    ids=['procedure_code','source00_entity_code','cv_project_group','cv_dependency_group',core.Q,core.GOV,core.AMOUNT]
    import gzip
    with gzip.open(trajectory_path,'wt',encoding='utf-8',newline='') as stream:
        for start in range(0,n,chunk_size):
            stop=min(start+chunk_size,n);profiles=part.iloc[indices[start:stop]]
            simulated=core.simulate_profiles(profiles,bundle['models'][model],rng)
            durations=simulated[:,:3];milestones=np.cumsum(durations,axis=1)
            if not np.array_equal(simulated[:,3],durations.sum(axis=1)) or not np.allclose(milestones[:,2],simulated[:,3],rtol=1e-14,atol=1e-12):raise ValueError('Temporal identity failed')
            frame=profiles[ids].reset_index(drop=True).copy();frame['simulation_id']=np.arange(start,stop)
            frame['model']=model;frame['scenario_primary']=scenario
            for i,name in enumerate(STAGES):frame[name]=durations[:,i]
            for i,name in enumerate(['event1_absolution_milestone','event2_integration_milestone','event3_award_milestone']):frame[name]=milestones[:,i]
            frame['total_duration_days']=simulated[:,3];frame.to_csv(stream,index=False,header=start==0)
            total[start:stop]=simulated[:,3]
    result=summary(total,core)
    result.update(model=model,scenario=scenario,seed=seed,stream_configuration='script07_v1:'+model+':scenario:'+scenario,stream_replicate=0,
        empirical_profiles=len(part),empirical_entities=int(part.source00_entity_code.nunique()),chunk_size=chunk_size,
        trajectory_file=trajectory_path.name,trajectory_sha256=core.sha(trajectory_path))
    return result


def verify_outputs(folder,core):
    manifest=json.loads((folder/'07_run_manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['outputs']:
        p=(folder/entry['path']).resolve()
        if p.parent!=folder.resolve() or core.sha(p)!=entry['sha256']:raise ValueError('Output hash/path mismatch')
    results=json.loads((folder/'07_2_simulation_summary.json').read_text(encoding='utf-8'))
    if set(results['configurations'])!=set(manifest['configurations']):raise ValueError('Summary configuration mismatch')
    for key,value in results['configurations'].items():
        count=0
        for part in pd.read_csv(folder/value['trajectory_file'],compression='gzip',chunksize=100000):
            if not part.model.eq(value['model']).all() or not part.scenario_primary.eq(value['scenario']).all():raise ValueError('Trajectory label mismatch')
            if not np.array_equal(part.simulation_id.to_numpy(),np.arange(count,count+len(part))):raise ValueError('Trajectory index mismatch')
            a=part[STAGES].to_numpy();t=part.total_duration_days.to_numpy()
            if not np.isfinite(a).all() or (a<0).any() or not np.allclose(a.sum(axis=1),t,rtol=1e-12,atol=1e-10):raise ValueError('Invalid output durations')
            milestones=part[['event1_absolution_milestone','event2_integration_milestone','event3_award_milestone']].to_numpy()
            if not np.allclose(np.cumsum(a,axis=1),milestones,rtol=1e-12,atol=1e-10):raise ValueError('Invalid milestones')
            count+=len(part)
        if count!=value['N']:raise ValueError('Trajectory row count mismatch')
    return results


def run(bundle_folder,initial,supplement,output_root,models=('M2',),scenarios=('low','medium','high'),seed=2026110307,chunk_size=100000):
    if not models or len(set(models))!=len(models) or not set(models)<=set(MODELS):raise ValueError('Invalid models')
    if not scenarios or len(set(scenarios))!=len(scenarios) or not set(scenarios)<=set(SCENARIOS):raise ValueError('Invalid scenarios')
    output=Path(output_root).resolve()/'02_results/03_stochastic_simulation'
    if output.exists() or output.is_symlink():raise FileExistsError('Existing output; use a fresh root')
    core=load_core();bundle,data,inputs,decisions,provenance=load_decisions(core,bundle_folder,initial,supplement)
    before={Path(bundle_folder)/name:value for name,value in inputs.items()}
    for folder in [Path(initial),Path(supplement)]:
        for name in ['06_1_convergence_metrics.csv','06_2_convergence_decision.json','06_run_manifest.json']:before[folder/name]=core.sha(folder/name)
    core_hash=core.sha(core.__file__);script_hash=core.sha(__file__);start=time.perf_counter()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.07_',dir=output.parent) as tmp:
        stage=Path(tmp);results={}
        for model in models:
            for scenario in scenarios:
                key=model+':scenario:'+scenario;decision=decisions[key]
                value=simulate_configuration(core,bundle,data,model,scenario,decision['N'],seed,chunk_size,stage/f'07_1_{model}_{scenario}_trajectories.csv.gz')
                value['convergence_provenance']=decision;results[key]=value
        document={'schema_version':VERSION,'reference_model':'M2','configurations':results,'duration_unit':'continuous_calendar_days','date_nature':bundle['scope']['date_nature'],
            'interpretation':'Conditional Monte Carlo of published schedules; no causal effect or initial-notice prediction.',
            'limitations':['Certified N only for evaluated empirical mixtures; not fixed profiles, tertiles or amount bands','National/FONAFE support limitations remain','No parameter/model-selection uncertainty propagation','Phase sum differs from independently calibrated TOTAL; empirical validation pending Script 08'],
            'output_contract_changes':['Separate trajectory file per model/scenario; no legacy pooled CSV','total_duration_days is continuous, never rounded or floored','Rows retain source profile IDs and joint covariates','Model-specific summaries and convergence provenance; no global pooled population','No tertile/KDE/sensitivity outputs'],
            'elapsed_seconds':time.perf_counter()-start}
        write_json(stage/'07_2_simulation_summary.json',document)
        if any(core.sha(p)!=h for p,h in before.items()) or core.sha(core.__file__)!=core_hash or core.sha(__file__)!=script_hash:raise ValueError('Protected source changed')
        manifest={'schema_version':VERSION,'script_sha256':script_hash,'core06_sha256':core_hash,'seed':seed,'inputs':inputs,'convergence_sources':provenance,
            'configurations':list(results),'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__},
            'outputs':[{'path':p.name,'bytes':p.stat().st_size,'sha256':core.sha(p)} for p in sorted(stage.iterdir())]}
        write_json(stage/'07_run_manifest.json',manifest);verify_outputs(stage,core)
        if output.exists() or output.is_symlink():raise FileExistsError('Output appeared')
        stage.rename(output)
    return output


def self_test():
    import unittest
    from unittest import mock
    import copy
    core=load_core()
    def fixture():
        n=30;q=np.tile([1,10,40],10)
        data=pd.DataFrame({'procedure_code':[str(i+100) for i in range(n)],'source00_entity_code':['E'+str(i) for i in range(n)],'cv_project_group':['P'+str(i) for i in range(n)],'cv_dependency_group':['D'+str(i) for i in range(n)],core.Q:q,core.GOV:['GOBIERNO LOCAL']*29+['FONAFE'],core.AMOUNT:100.+q,'empirical_row_weight':[1/n]*n,'asymmetry_scenario':np.tile(SCENARIOS,10)})
        t={'Q_log1p_mean':1.,'Q_log1p_std':1.,'amount_log_mean':5.,'amount_log_std':1.,'government_weights':dict(zip(core.LEVELS[:3],[.7,.2,.1]))}
        marginal={'kind':'covariate_lognormal_v3','location_names':['intercept','Q_standardized_log1p'],'location_coefficients':[2.,.1],'log_sigma_names':['log_sigma_intercept'],'log_sigma_coefficients':[-1.]}
        model={'transform':t,'dependence':{'phase_order':core.PHASES,'latent_correlation':[[1,0,.4],[0,1,0],[.4,0,1]]},'models':{core.PHASES[0]:marginal,core.PHASES[1]:{'kind':'constant','value':0},core.PHASES[2]:marginal}}
        return {'models':{m:copy.deepcopy(model) for m in MODELS},'scope':{'date_nature':'published_schedule_not_verified_actual_events'}},data
    class Tests(unittest.TestCase):
        def test_import_without_execution(self):
            with mock.patch('tempfile.TemporaryDirectory',side_effect=AssertionError('Import side effect')):module=load_core()
            self.assertTrue(callable(module.simulate_profiles));self.assertEqual(module.__name__,'thesis06_core')
        def test_exact_core_and_joint_profiles(self):
            bundle,data=fixture();part=core.select_profiles(data,'high');n=503;rng=configuration_stream(core,7,'M2','high',n);w=part.empirical_row_weight.to_numpy();w/=w.sum();indices=rng.choice(len(part),n,p=w);expected=core.simulate_profiles(part.iloc[indices],bundle['models']['M2'],rng)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'x.csv.gz';result=simulate_configuration(core,bundle,data,'M2','high',n,7,100,path);v=pd.read_csv(path)
                np.testing.assert_allclose(v.total_duration_days,expected[:,3],rtol=1e-13,atol=1e-12)
                source=data.set_index('procedure_code');source.index=source.index.astype(str)
                for row in v.to_dict('records'):
                    original=source.loc[str(row['procedure_code'])];self.assertEqual(row[core.Q],original[core.Q]);self.assertEqual(row[core.AMOUNT],original[core.AMOUNT]);self.assertEqual(row[core.GOV],original[core.GOV])
                self.assertTrue(v.stage2_integration_days.eq(0).all());self.assertIn('FONAFE',v[core.GOV].unique());self.assertEqual(result['N'],n)
        def test_unbounded_precision_is_explicit(self):
            value=summary(np.arange(10,dtype=float),core)
            self.assertTrue(any(r['halfwidth'] is None for r in value['precision_diagnostics']))
            json.dumps(value,allow_nan=False)
        def test_nine_decisions_and_provenance_rejection(self):
            b,d=fixture();d=pd.concat([d]*67,ignore_index=True).iloc[:2004]
            accepted={'M1':[50000,150000,500000],'M2':[50000,500000,2000000],'M4':[50000,250000,2000000]}
            inputs={'05_7_simulation_bundle.json':'synthetic'}
            def decision(folder):
                protocol=folder.name;plan=core.protocol_plan(protocol);entries={}
                for key in plan:
                    model,_,scenario=key.split(':');n=accepted[model][SCENARIOS.index(scenario)]
                    ok=(scenario=='low') if protocol=='initial' else True
                    entries[key]={'status':'PRECISION_REACHED' if ok else 'PRECISION_NOT_REACHED','recommended_N':n if ok else None,'larger_size_confirmation':ok}
                value={'schema_version':core.VERSION,'inputs':inputs,'seed':20251025 if protocol=='initial' else 2026110306,'decisions':entries}
                if protocol=='supplement':value.update(protocol=protocol,plan=plan,stream_namespace='supplement_v1:',chunk_size=100000)
                return value
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for protocol in ['initial','supplement']:
                    (root/protocol).mkdir();(root/protocol/'06_run_manifest.json').write_text('synthetic')
                with mock.patch.object(core,'load_contract',return_value=(b,d,inputs)),mock.patch.object(core,'verify_publication',side_effect=decision):
                    _,_,_,values,_=load_decisions(core,root,root/'initial',root/'supplement')
                    self.assertEqual(len(values),9)
                    for model,counts in accepted.items():
                        for scenario,count in zip(SCENARIOS,counts):self.assertEqual(values[model+':scenario:'+scenario]['N'],count)
                for bad in ['seed','inputs','missing','N']:
                    def invalid(folder):
                        value=decision(folder)
                        if folder.name=='supplement':
                            if bad=='seed':value['seed']=0
                            elif bad=='inputs':value['inputs']={}
                            elif bad=='missing':value['decisions'].pop('M2:scenario:high')
                            else:value['decisions']['M2:scenario:high']['recommended_N']=1
                        return value
                    with self.subTest(case=bad),mock.patch.object(core,'load_contract',return_value=(b,d,inputs)),mock.patch.object(core,'verify_publication',side_effect=invalid):
                        with self.assertRaises(ValueError):load_decisions(core,root,root/'initial',root/'supplement')
                with mock.patch.object(core,'load_contract',side_effect=ValueError('Bundle hash mismatch')):
                    with self.assertRaisesRegex(ValueError,'hash'):load_decisions(core,root,root/'initial',root/'supplement')
        def test_statistics_and_strict_exceedance(self):
            x=np.array([1.,2.,30.,30.,60.,120.]);v=summary(x,core);self.assertEqual(v['exceedances']['30'],2/6);self.assertEqual(v['median'],30);self.assertEqual(v['std_dev'],x.std(ddof=1))
        def test_order_independent(self):
            a=configuration_stream(core,8,'M2','low',100).random(20);configuration_stream(core,8,'M4','high',100).random(20)
            np.testing.assert_array_equal(a,configuration_stream(core,8,'M2','low',100).random(20))
        def test_invalid_selection_and_empty_cell(self):
            with self.assertRaises(ValueError):configuration_stream(core,1,'M3','low',100)
            b,d=fixture()
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(ValueError):simulate_configuration(core,b,d[d.asymmetry_scenario.ne('low')],'M2','low',10,1,10,Path(tmp)/'x.gz')
        def test_actual_hash_rejection_routes(self):
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                for name in ['05_7_simulation_bundle.json','05_8_joint_profiles.csv']:(folder/name).write_text('altered')
                write_json(folder/'05_export_manifest.json',{'status':'COMPLETE','outputs':[{'path':name,'sha256':'0'*64} for name in ['05_7_simulation_bundle.json','05_8_joint_profiles.csv']]})
                with self.assertRaisesRegex(ValueError,'hash'):load_decisions(core,folder,folder,folder)
                b,d=fixture();d=pd.concat([d]*67,ignore_index=True).iloc[:2004]
                for name in ['06_1_convergence_metrics.csv','06_2_convergence_decision.json']:(folder/name).write_text('altered')
                write_json(folder/'06_run_manifest.json',{'outputs':[{'path':name,'sha256':'0'*64} for name in ['06_1_convergence_metrics.csv','06_2_convergence_decision.json']]})
                with mock.patch.object(core,'load_contract',return_value=(b,d,{})):
                    with self.assertRaisesRegex(ValueError,'hash'):load_decisions(core,folder,folder,folder)
        def test_bundle_rejection_uses_loader(self):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(FileNotFoundError):load_decisions(core,tmp,tmp,tmp)
        def test_publication_and_failure(self):
            b,d=fixture()
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);inputs={'input.json':core.sha(__file__)};(root/'input.json').write_bytes(Path(__file__).read_bytes())
                for folder in [root/'initial',root/'supplement']:
                    folder.mkdir()
                    for name in ['06_1_convergence_metrics.csv','06_2_convergence_decision.json','06_run_manifest.json']:(folder/name).write_text('synthetic')
                mapping={m+':scenario:'+s:{'N':50,'protocol':'synthetic'} for m in MODELS for s in SCENARIOS}
                with mock.patch.dict(globals(),{'load_decisions':lambda *a:(b,d,inputs,mapping,[])}):
                    out=run(root,root/'initial',root/'supplement',root/'success',models=['M2'],scenarios=['low'],chunk_size=17);verify_outputs(out,core)
                    with self.assertRaises(FileExistsError):run(root,root/'initial',root/'supplement',root/'success')
                    with mock.patch.dict(globals(),{'verify_outputs':mock.Mock(side_effect=ValueError('deliberate publication failure'))}):
                        with self.assertRaisesRegex(ValueError,'deliberate'):run(root,root/'initial',root/'supplement',root/'failure',models=['M1'],scenarios=['low'])
                    self.assertFalse((root/'failure/02_results/03_stochastic_simulation').exists());self.assertFalse(list((root/'failure/02_results').glob('.07_*')))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise RuntimeError('Synthetic tests failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ['bundle-dir','initial-dir','supplement-dir','output-root']:parser.add_argument('--'+option,type=Path)
    parser.add_argument('--models',nargs='+',choices=MODELS,default=['M2']);parser.add_argument('--scenarios',nargs='+',choices=SCENARIOS,default=SCENARIOS)
    parser.add_argument('--seed',type=int,default=2026110307);parser.add_argument('--chunk-size',type=int,default=100000);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:return self_test()
    if any(getattr(args,k) is None for k in ['bundle_dir','initial_dir','supplement_dir','output_root']):parser.error('All four artifact/output directories are required')
    print(run(args.bundle_dir,args.initial_dir,args.supplement_dir,args.output_root,args.models,args.scenarios,args.seed,args.chunk_size))

if __name__=='__main__':main()
