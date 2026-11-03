"""Conditional Monte Carlo precision study; published schedules, fixed calibration.

No independent DES mechanism, parameter refitting or predictive validation.
"""
import argparse
import hashlib
import json
import math
import platform
import tempfile
import time
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
from scipy import stats

VERSION='2.0-conditional-monte-carlo'
SIZES=[1000,5000,10000,50000,100000]
THRESHOLDS=[30,45,60,75,90,120,150,180]
PHASES=['absolution_calendar_days','integration_calendar_days','post_integration_calendar_days']
Q='queries_observations_count'
GOV='calibration_government'
AMOUNT='source00_reference_amount'
LEVELS=['GOBIERNO LOCAL','GOBIERNO REGIONAL','GOBIERNO NACIONAL','FONAFE']

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()

def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def load_contract(folder):
    folder=Path(folder).resolve()
    manifest=json.loads((folder/'05_export_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('status')!='COMPLETE':raise ValueError('Incomplete export')
    files={}
    if {e['path'] for e in manifest['outputs']}!={'05_7_simulation_bundle.json','05_8_joint_profiles.csv'} or len(manifest['outputs'])!=2:raise ValueError('Manifest membership mismatch')
    for entry in manifest['outputs']:
        path=(folder/entry['path']).resolve()
        if path.parent!=folder or sha(path)!=entry['sha256']:raise ValueError('Artifact hash/path mismatch')
        files[path.name]=path
    bundle=json.loads(files['05_7_simulation_bundle.json'].read_text(encoding='utf-8'))
    if bundle['schema_version']!='sixa-calibration-bundle/1.0' or manifest['schema_version']!=bundle['schema_version'] or bundle['reference_model']!='M2':raise ValueError('Unsupported schema/reference')
    profiles=bundle['joint_profiles'];path=(folder/profiles['path']).resolve()
    if path.parent!=folder or path.name not in files or sha(path)!=profiles['sha256']:raise ValueError('Profile hash mismatch')
    data=pd.read_csv(path,dtype={'procedure_code':str,'source00_entity_code':str})
    if len(data)!=profiles['n'] or data.procedure_code.duplicated().any():raise ValueError('Profile IDs/count mismatch')
    validate_profiles(data)
    if list(data.columns)!=profiles['columns']:raise ValueError('Profile column mismatch')
    for col in ['procedure_code','source00_entity_code','cv_project_group','cv_dependency_group']:
        if data[col].isna().any() or data[col].astype(str).str.strip().eq('').any():raise ValueError('Missing profile identifier')
    if not np.isclose(data.empirical_row_weight.sum(),1.,rtol=0,atol=1e-10):raise ValueError('Unnormalized profile weights')
    cuts=bundle['scenarios']['primary']['cuts']
    if len(cuts)!=2 or not np.isfinite(cuts).all() or cuts[0]>=cuts[1]:raise ValueError('Invalid scenario cuts')
    labels=np.where(data[Q]<cuts[0],'low',np.where(data[Q]>cuts[1],'high','medium'))
    if not np.array_equal(labels,data.asymmetry_scenario):raise ValueError('Scenario mismatch')
    for name in ['M1','M2','M4']:
        model=bundle['models'][name]
        if model.get('architecture')!=name:raise ValueError('Architecture mismatch')
        if canonical({k:v for k,v in model.items() if k!='model_sha256'})!=model['model_sha256']:raise ValueError('Model hash mismatch')
        validate_model(model)
        for phase in [PHASES[0],PHASES[2]]:
            m=model['models'][phase];expected=['intercept','Q_standardized_log1p']
            if name in ['M2','M4']:expected+=['government_regional_centered','government_national_centered']
            if name=='M4':expected+=['procedure_amount_standardized_ln_nominal_PEN']
            shape=['log_sigma_intercept']+(['log_sigma_Q'] if phase==PHASES[2] else [])
            if m.get('location_names')!=expected or m.get('log_sigma_names')!=shape:raise ValueError('Architecture design mismatch')
    return bundle,data,{p.name:sha(p) for p in list(files.values())+[folder/'05_export_manifest.json']}

def validate_profiles(data):
    if not data[GOV].isin(LEVELS).all():raise ValueError('Unknown government')
    for col in [Q,AMOUNT,'empirical_row_weight']:
        if not np.isfinite(data[col]).all():raise ValueError('Nonfinite profile input')
    if (data[Q]<0).any() or data[Q].mod(1).ne(0).any() or (data[AMOUNT]<=0).any() or (data.empirical_row_weight<=0).any():raise ValueError('Invalid profile input/weight')

def validate_model(model):
    dep=model['dependence']
    if dep['phase_order']!=PHASES:raise ValueError('Phase order mismatch')
    corr=np.array(dep['latent_correlation'],float)
    if corr.shape!=(3,3) or not np.isfinite(corr).all() or not np.allclose(corr,corr.T) or not np.allclose(np.diag(corr),1):raise ValueError('Invalid correlation')
    np.linalg.cholesky(corr)
    t=model['transform']
    if not np.isfinite([t[k] for k in ['Q_log1p_mean','Q_log1p_std','amount_log_mean','amount_log_std']]).all():raise ValueError('Nonfinite transform')
    weights=t['government_weights']
    if any(not np.isfinite(v) or v<0 or v>1 for v in weights.values()) or not np.isclose(sum(weights.values()),1.):raise ValueError('Invalid government weights')
    if t['Q_log1p_std']<=0 or t['amount_log_std']<=0:raise ValueError('Invalid transform')
    for phase in PHASES:
        m=model['models'][phase]
        if m['kind']=='covariate_lognormal_v3':
            for key in ['location','log_sigma']:
                if len(m[key+'_names'])!=len(m[key+'_coefficients']) or not np.isfinite(m[key+'_coefficients']).all():raise ValueError('Coefficient mismatch')
        elif m['kind']=='empirical_zero_positive_mixture':
            p=m['p_zero'];s=np.asarray(m['positive_values'],float)
            if not 0<=p<=1 or (p<1 and not len(s)) or not np.isfinite(s).all() or (s<=0).any():raise ValueError('Invalid integration mixture')
        elif m['kind']=='constant':
            if not np.isfinite(m['value']) or m['value']<0:raise ValueError('Invalid constant')
        else:raise ValueError('Unsupported marginal')

def design(data,t):
    z=(np.log1p(data[Q].to_numpy(float))-t['Q_log1p_mean'])/t['Q_log1p_std']
    regular=data[GOV].ne('FONAFE').to_numpy()
    return {'intercept':np.ones(len(data)),'Q_standardized_log1p':z,'log_sigma_intercept':np.ones(len(data)),'log_sigma_Q':z,
        'government_regional_centered':np.where(regular,data[GOV].eq('GOBIERNO REGIONAL').to_numpy(float)-t['government_weights']['GOBIERNO REGIONAL'],0),
        'government_national_centered':np.where(regular,data[GOV].eq('GOBIERNO NACIONAL').to_numpy(float)-t['government_weights']['GOBIERNO NACIONAL'],0),
        'procedure_amount_standardized_ln_nominal_PEN':(np.log(data[AMOUNT].to_numpy(float))-t['amount_log_mean'])/t['amount_log_std']}

def inverse_marginal(model,u,basis):
    kind=model['kind']
    if kind=='constant':return np.full(len(u),model['value'],float)
    if kind=='empirical_zero_positive_mixture':
        p=model['p_zero'];out=np.zeros(len(u));positive=u>p
        if positive.any():out[positive]=np.quantile(np.array(model['positive_values']),np.clip((u[positive]-p)/(1-p),0,1),method='inverted_cdf')
        return out
    mu=sum(basis[k]*v for k,v in zip(model['location_names'],model['location_coefficients']))
    sigma=np.exp(sum(basis[k]*v for k,v in zip(model['log_sigma_names'],model['log_sigma_coefficients'])))
    return np.exp(mu+sigma*stats.norm.ppf(np.clip(u,1e-12,1-1e-12)))

def simulate_profiles(data,model,rng):
    """One row per realization; no resampling here and no TOTAL-marginal draw."""
    validate_profiles(data);validate_model(model)
    basis=design(data,model['transform']);corr=np.array(model['dependence']['latent_correlation'])
    u=stats.norm.cdf(rng.standard_normal((len(data),3))@np.linalg.cholesky(corr).T)
    phases=np.column_stack([inverse_marginal(model['models'][p],u[:,i],basis) for i,p in enumerate(PHASES)])
    if not np.isfinite(phases).all() or (phases<0).any():raise ValueError('Invalid simulated interval')
    return np.column_stack([phases,phases.sum(axis=1)])

def select_profiles(data,scenario=None,government=None,amount_band=None):
    part=data.copy()
    if scenario is not None:part=part[part.asymmetry_scenario.eq(scenario)]
    if government is not None:
        if government not in LEVELS:raise ValueError('Unknown government')
        part=part[part[GOV].eq(government)]
    if amount_band is not None:part=part[part[AMOUNT].between(*amount_band)]
    if part.empty:raise ValueError('UNSUPPORTED_PROFILE: empty conditional cell')
    return part

def stream(seed,configuration,n,replicate):
    digest=hashlib.sha256(configuration.encode('utf-8')).digest()
    key=tuple(int.from_bytes(digest[i:i+4],'little') for i in range(0,16,4))+(int(n),int(replicate))
    return np.random.default_rng(np.random.SeedSequence(int(seed),spawn_key=key))

def precision_metrics(values):
    """Pointwise 95% MC intervals; simultaneous acceptance is operational only."""
    x=np.asarray(values,float);n=len(x)
    if n<2 or not np.isfinite(x).all():raise ValueError('Invalid precision sample')
    mean=float(x.mean());s=float(x.std(ddof=1));m4=float(np.mean((x-mean)**4))
    sdse=math.sqrt(max(m4-s**4,0)/(4*n*s*s)) if s else 0.
    rows=[{'metric':'mean','estimate':mean,'halfwidth':1.96*s/math.sqrt(n),'tolerance':max(.25,.005*abs(mean))},
          {'metric':'std','estimate':s,'halfwidth':1.96*sdse,'tolerance':max(.5,.01*s)}]
    ordered=np.sort(x)
    for p,label,absolute,relative in [(.9,'P90',.5,.01),(.95,'P95',1.,.02)]:
        estimate=float(np.quantile(x,p,method='linear'))
        lower=int(stats.binom.ppf(.025,n,p));upper=int(stats.binom.ppf(.975,n,p))+1
        lo=float(ordered[lower-1]) if lower>=1 else -np.inf
        hi=float(ordered[upper-1]) if upper<=n else np.inf
        rows.append({'metric':label,'estimate':estimate,'halfwidth':max(estimate-lo,hi-estimate),'tolerance':max(absolute,relative*abs(estimate))})
    for threshold in THRESHOLDS:
        k=int((x>threshold).sum());p=k/n;z=stats.norm.ppf(.975);den=1+z*z/n
        center=(p+z*z/(2*n))/den;radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
        rows.append({'metric':'exceed_'+str(threshold),'estimate':p,'halfwidth':max(p-(center-radius),(center+radius)-p),'tolerance':.005})
    for row in rows:row['pass']=bool(np.isfinite(row['halfwidth']) and row['halfwidth']<=row['tolerance'])
    return rows

def decide(table,sizes=SIZES,repetitions=30):
    required={'mean','std','P90','P95'}|{'exceed_'+str(v) for v in THRESHOLDS}
    if set(table.metric)!=required or table.duplicated(['N','replicate','metric']).any() or set(table.N)!=set(sizes):raise ValueError('Incomplete/duplicate precision metrics')
    if not np.isfinite(table[['estimate','tolerance']].to_numpy()).all() or table.tolerance.le(0).any() or table.halfwidth.isna().any() or table.halfwidth.lt(0).any():raise ValueError('Invalid precision diagnostics')
    table=table.copy();table['pass']=np.isfinite(table.halfwidth)&table.halfwidth.le(table.tolerance)
    summary=[]
    for n in sizes:
        part=table[table.N.eq(n)];counts=part.groupby('replicate')['pass'].all()
        if set(part.replicate)!=set(range(repetitions)) or len(part)!=repetitions*len(required) or len(counts)!=repetitions:raise ValueError('Incomplete replicate table')
        summary.append({'N':n,'replicates_passing_all':int(counts.sum()),'precision_pass':bool(counts.sum()>=math.ceil(.9*repetitions))})
    for entry in summary:
        n=entry['N'];stable=True
        for larger in [v for v in sizes if v>n]:
            for metric in table.metric.unique():
                a=table[table.N.eq(n)&table.metric.eq(metric)];b=table[table.N.eq(larger)&table.metric.eq(metric)]
                # Replicate means assess numerical agreement of estimators, not
                # the precision of a single future run (checked separately).
                va=a.estimate.var(ddof=1)/repetitions;vb=b.estimate.var(ddof=1)/repetitions
                df=(va+vb)**2/((va*va+vb*vb)/(repetitions-1)) if va+vb else 2*repetitions-2
                error=stats.t.ppf(.975,df)*math.sqrt(va+vb)
                stable &= abs(a.estimate.mean()-b.estimate.mean())+error<=min(a.tolerance.mean(),b.tolerance.mean())
        entry['stable_against_larger']=bool(stable)
    candidates=[r['N'] for i,r in enumerate(summary) if r['stable_against_larger'] and all(v['precision_pass'] for v in summary[i:])]
    recommendation=min(candidates) if candidates else None
    return {'status':'PRECISION_REACHED' if recommendation else 'PRECISION_NOT_REACHED','recommended_N':recommendation,
        'larger_size_confirmation':bool(recommendation and recommendation<max(sizes)),'sizes':summary}

def simulate_totals(part,indices,model,rng,chunk_size=None):
    """Keep draw order; retain every total for unchanged exact precision metrics."""
    if chunk_size is None:return simulate_profiles(part.iloc[indices],model,rng)[:,3]
    if not isinstance(chunk_size,int) or chunk_size<=0:raise ValueError('chunk_size must be a positive integer')
    total=np.empty(len(indices),dtype=float)
    for start in range(0,len(indices),chunk_size):
        stop=min(start+chunk_size,len(indices))
        total[start:stop]=simulate_profiles(part.iloc[indices[start:stop]],model,rng)[:,3]
    return total

def protocol_plan(protocol):
    if protocol=='initial':return {m+':scenario:'+s:list(SIZES) for m in ['M2','M1','M4'] for s in ['low','medium','high']}
    if protocol!='supplement':raise ValueError('Unknown protocol')
    return {'M1:scenario:medium':[150000,250000,500000],
        'M2:scenario:medium':[250000,500000,750000],
        'M4:scenario:medium':[250000,500000,750000],
        'M1:scenario:high':[500000,750000,1000000],
        'M2:scenario:high':[1000000,2000000,3000000],
        'M4:scenario:high':[1000000,2000000,3000000]}

def run_study(bundle_folder,output_root,seed=20251025,protocol='initial',chunk_size=None):
    output=Path(output_root).resolve()/'02_results/03_stochastic_simulation'
    if output.exists() or output.is_symlink():raise FileExistsError('Existing results must not be replaced')
    bundle,data,inputs=load_contract(bundle_folder);started=time.perf_counter();rows=[];decisions={}
    plan=protocol_plan(protocol)
    if protocol=='supplement' and chunk_size is None:chunk_size=100000
    for key,sizes in plan.items():
        model,_,scenario=key.split(':');part=select_profiles(data,scenario);weights=part.empirical_row_weight.to_numpy(float);weights/=weights.sum()
        for n in sizes:
            for rep in range(30):
                stream_key=key if protocol=='initial' else 'supplement_v1:'+key
                rng=stream(seed,stream_key,n,rep);indices=rng.choice(len(part),size=n,p=weights)
                total=simulate_totals(part,indices,bundle['models'][model],rng,chunk_size)
                rows.extend({'configuration':key,'N':n,'replicate':rep,**m} for m in precision_metrics(total))
        decisions[key]=decide(pd.DataFrame([r for r in rows if r['configuration']==key]),sizes=sizes)
    table=pd.DataFrame(rows)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.06_',dir=output.parent) as temporary:
        stage=Path(temporary);table.to_csv(stage/'06_1_convergence_metrics.csv',index=False)
        result={'schema_version':VERSION,'seed':seed,'protocol':protocol,'plan':plan,'stream_namespace':'' if protocol=='initial' else 'supplement_v1:',
            'chunk_size':chunk_size,'chunk_numerics':'Same draw order and exact quantile definitions; BLAS blocking can differ at floating-point roundoff. Initial default remains unchunked.','expected_realizations':30*sum(sum(v) for v in plan.values()),'decisions':decisions,'inputs':inputs,'elapsed_seconds':time.perf_counter()-started,
            'acceptance':'At least 27/30 replicates simultaneously pass all 12 pointwise-95% precision criteria; operational rule, no familywise coverage guarantee. Larger-size agreement uses replicate estimates, not single-run precision.',
            'configuration_scope':'Selected empirical model/scenario mixtures only; no precision guarantee for arbitrary future SIXA fixed profiles or amount bands.',
            'scope':'Fixed calibrated parameters and empirical profiles; excludes parameter/model-selection uncertainty and predictive validity. No academic amendment presumed.',
            'versions':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__}}
        (stage/'06_2_convergence_decision.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
        for name,h in inputs.items():
            if sha(Path(bundle_folder)/name)!=h:raise ValueError('Input changed')
        manifest={'schema_version':VERSION,'script_sha256':sha(__file__),'inputs':inputs,'outputs':[{'path':p.name,'sha256':sha(p)} for p in stage.iterdir()]}
        (stage/'06_run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        verify_publication(stage)
        if output.exists() or output.is_symlink():raise FileExistsError('Output appeared')
        # Rename the complete staging directory; TemporaryDirectory then has
        # nothing to remove at its original path.
        stage.rename(output)
    return output

def verify_publication(folder):
    manifest=json.loads((folder/'06_run_manifest.json').read_text(encoding='utf-8'))
    if {v['path'] for v in manifest['outputs']}!={'06_1_convergence_metrics.csv','06_2_convergence_decision.json'}:raise ValueError('Publication membership mismatch')
    for entry in manifest['outputs']:
        if Path(entry['path']).name!=entry['path'] or sha(folder/entry['path'])!=entry['sha256']:raise ValueError('Publication hash mismatch')
    table=pd.read_csv(folder/'06_1_convergence_metrics.csv')
    result=json.loads((folder/'06_2_convergence_decision.json').read_text(encoding='utf-8'))
    if set(table.configuration)!=set(result['decisions']):raise ValueError('Publication configuration mismatch')
    plan=result.get('plan',protocol_plan('initial'))
    if len(table)!=sum(len(v) for v in plan.values())*30*12:raise ValueError('Publication row count mismatch')
    for key,sizes in plan.items():
        part=table[table.configuration.eq(key)].copy()
        if decide(part,sizes=sizes)!=result['decisions'][key]:raise ValueError('Published decisions do not match metrics')
    return result

def self_test():
    import unittest
    class Tests(unittest.TestCase):
        def test_core_sum_and_copula(self):
            d=pd.DataFrame({Q:[2]*20000,AMOUNT:[100]*20000,GOV:['FONAFE']*20000,'empirical_row_weight':[1/20000]*20000})
            t={'Q_log1p_mean':0.,'Q_log1p_std':1.,'amount_log_mean':0.,'amount_log_std':1.,'government_weights':{'GOBIERNO LOCAL':.7,'GOBIERNO REGIONAL':.2,'GOBIERNO NACIONAL':.1}}
            m={'kind':'covariate_lognormal_v3','location_names':['intercept'],'location_coefficients':[0.],'log_sigma_names':['log_sigma_intercept'],'log_sigma_coefficients':[0.]}
            b={'transform':t,'dependence':{'phase_order':PHASES,'latent_correlation':[[1,0,.6],[0,1,0],[.6,0,1]]},'models':{PHASES[0]:m,PHASES[1]:{'kind':'constant','value':0.},PHASES[2]:m}}
            v=simulate_profiles(d,b,np.random.default_rng(18));np.testing.assert_array_equal(v[:,3],v[:,:3].sum(axis=1))
            self.assertAlmostEqual(np.corrcoef(np.log(v[:,0]),np.log(v[:,2]))[0,1],.6,delta=.025)
            self.assertAlmostEqual(v[:,0].mean(),np.exp(.5),delta=.06)
            b['dependence']['latent_correlation']=np.eye(3).tolist();v=simulate_profiles(d,b,np.random.default_rng(18))
            self.assertAlmostEqual(np.corrcoef(np.log(v[:,0]),np.log(v[:,2]))[0,1],0,delta=.025)
            b['dependence']['phase_order']=list(reversed(PHASES))
            with self.assertRaises(ValueError):validate_model(b)
        def test_design_inactive_amount_and_FONAFE(self):
            d=pd.DataFrame({Q:[0],AMOUNT:[100],GOV:['FONAFE'],'empirical_row_weight':[1.]})
            t={'Q_log1p_mean':1.,'Q_log1p_std':2.,'amount_log_mean':0.,'amount_log_std':1.,'government_weights':{'GOBIERNO LOCAL':.7,'GOBIERNO REGIONAL':.2,'GOBIERNO NACIONAL':.1}}
            x=design(d,t);self.assertEqual(x['government_national_centered'][0],0)
            m={'kind':'covariate_lognormal_v3','location_names':['intercept','procedure_amount_standardized_ln_nominal_PEN'],'location_coefficients':[0.,.2],'log_sigma_names':['log_sigma_intercept'],'log_sigma_coefficients':[0.]}
            a=inverse_marginal(m,np.array([.5]),x);d[AMOUNT]*=2;b=inverse_marginal(m,np.array([.5]),design(d,t));np.testing.assert_allclose(b/a,2**.2)
            m['location_names']=['intercept'];m['location_coefficients']=[0.];np.testing.assert_array_equal(inverse_marginal(m,np.array([.5]),x),inverse_marginal(m,np.array([.5]),design(d,t)))
        def test_joint_rows_and_invalid_weights(self):
            d=pd.DataFrame({Q:[1,2],AMOUNT:[10,20],GOV:['GOBIERNO LOCAL']*2,'empirical_row_weight':[.5,.5],'asymmetry_scenario':['low','low']})
            selected=select_profiles(d,'low');draw=selected.iloc[np.random.default_rng(1).choice(2,100)]
            self.assertTrue((draw[AMOUNT]==draw[Q]*10).all());d.loc[0,'empirical_row_weight']=0
            with self.assertRaises(ValueError):validate_profiles(d)
        def test_stream_order(self):
            a=stream(10,'M2:low',1000,0).random(30);stream(10,'other',1000,0).random(30)
            np.testing.assert_array_equal(a,stream(10,'M2:low',1000,0).random(30))
            self.assertFalse(np.array_equal(a,stream(10,'M2:low',1000,1).random(30)))
        def test_mixture(self):
            m={'kind':'empirical_zero_positive_mixture','p_zero':.5,'positive_values':[8,2,2,4]}
            np.testing.assert_array_equal(inverse_marginal(m,np.array([0,.5,.51,.75,1]),{}),[0,0,2,2,8])
            np.testing.assert_array_equal(inverse_marginal({'kind':'empirical_zero_positive_mixture','p_zero':1.,'positive_values':[]},np.array([0.,1.]),{}),[0,0])
        def test_constants(self):
            np.testing.assert_array_equal(inverse_marginal({'kind':'constant','value':0},np.ones(10),{}),np.zeros(10))
            rows=precision_metrics(np.full(1000,12.));self.assertEqual(rows[0]['estimate'],12.);self.assertEqual(rows[1]['halfwidth'],0.)
        def test_analytical_lognormal(self):
            m={'kind':'covariate_lognormal_v3','location_names':['intercept'],'location_coefficients':[2.], 'log_sigma_names':['intercept'],'log_sigma_coefficients':[0.]}
            a=inverse_marginal(m,np.array([.5]),{'intercept':np.ones(1)});np.testing.assert_allclose(a,np.exp(2))
        def test_zero_exceedances(self):
            r=[r for r in precision_metrics(np.ones(1000)) if r['metric']=='exceed_180'][0]
            self.assertEqual(r['estimate'],0);self.assertGreater(r['halfwidth'],0)
        def test_reject_invalid_sample(self):
            with self.assertRaises(ValueError):precision_metrics([1,np.nan])
        def test_empty_cell(self):
            d=pd.DataFrame({'asymmetry_scenario':['low'],GOV:['FONAFE'],AMOUNT:[1]})
            with self.assertRaises(ValueError):select_profiles(d,'high')
            with self.assertRaises(ValueError):select_profiles(d,government='UNKNOWN')
        def test_not_reached(self):
            rows=[{'N':n,'replicate':r,'metric':metric,'estimate':1.,'halfwidth':10.,'tolerance':.25,'pass':False} for n in SIZES for r in range(30) for metric in ['mean','std','P90','P95']+['exceed_'+str(v) for v in THRESHOLDS]]
            self.assertEqual(decide(pd.DataFrame(rows))['status'],'PRECISION_NOT_REACHED')
        def test_first_acceptable(self):
            rows=[{'N':n,'replicate':r,'metric':metric,'estimate':1.,'halfwidth':0.,'tolerance':.25,'pass':True} for n in SIZES for r in range(30) for metric in ['mean','std','P90','P95']+['exceed_'+str(v) for v in THRESHOLDS]]
            self.assertEqual(decide(pd.DataFrame(rows))['recommended_N'],1000)
        def test_existing_output(self):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'02_results/03_stochastic_simulation';p.mkdir(parents=True)
                with self.assertRaises(FileExistsError):run_study('missing',d)
        def test_hash_corruption(self):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'x';p.write_text('one');before=sha(p);p.write_text('two');self.assertNotEqual(before,sha(p))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    if not result.wasSuccessful():raise RuntimeError('Synthetic tests failed')


def closure_tests():
    import unittest
    import copy
    from unittest import mock
    import contextlib
    import io
    def fixture(folder):
        folder.mkdir()
        d=pd.DataFrame({'procedure_code':[str(100+i) for i in range(6)],'source00_entity_code':['E'+str(i) for i in range(6)],
            'cv_project_group':['P'+str(i) for i in range(6)],'cv_dependency_group':['D'+str(i) for i in range(6)],
            GOV:['GOBIERNO LOCAL']*5+['FONAFE'],Q:[1,10,40,2,20,50],AMOUNT:[100.,200.,300.,400.,500.,600.],
            'asymmetry_scenario':['low','medium','high','low','medium','high'],'empirical_row_weight':[1/6]*6})
        t={'Q_log1p_mean':1.,'Q_log1p_std':1.,'amount_log_mean':5.,'amount_log_std':1.,'government_weights':dict(zip(LEVELS[:3],[.7,.2,.1]))}
        models={}
        for name in ['M1','M2','M4']:
            names=['intercept','Q_standardized_log1p']
            if name in ['M2','M4']:names+=['government_regional_centered','government_national_centered']
            if name=='M4':names+=['procedure_amount_standardized_ln_nominal_PEN']
            marginals={}
            for phase in [PHASES[0],PHASES[2]]:
                sn=['log_sigma_intercept']+(['log_sigma_Q'] if phase==PHASES[2] else [])
                marginals[phase]={'kind':'covariate_lognormal_v3','location_names':names,'location_coefficients':[2.]+[.1]*(len(names)-1),'log_sigma_names':sn,'log_sigma_coefficients':[-1.]+[0.]*(len(sn)-1)}
            marginals[PHASES[1]]={'kind':'empirical_zero_positive_mixture','p_zero':.9,'positive_values':[1,2,2,4]}
            models[name]={'architecture':name,'transform':copy.deepcopy(t),'models':marginals,'dependence':{'phase_order':PHASES,'latent_correlation':np.eye(3).tolist()}}
        b={'schema_version':'sixa-calibration-bundle/1.0','reference_model':'M2','models':models,'scenarios':{'primary':{'cuts':[7,35]}},'joint_profiles':{'path':'05_8_joint_profiles.csv','n':6,'columns':list(d.columns)}}
        write(folder,b,d);return b,d
    def write(folder,b,d):
        d.to_csv(folder/'05_8_joint_profiles.csv',index=False)
        b['joint_profiles']['sha256']=sha(folder/'05_8_joint_profiles.csv')
        for model in b['models'].values():model['model_sha256']=canonical({k:v for k,v in model.items() if k!='model_sha256'})
        (folder/'05_7_simulation_bundle.json').write_text(json.dumps(b),encoding='utf-8')
        m={'schema_version':b['schema_version'],'status':'COMPLETE','outputs':[{'path':name,'sha256':sha(folder/name)} for name in ['05_7_simulation_bundle.json','05_8_joint_profiles.csv']]}
        (folder/'05_export_manifest.json').write_text(json.dumps(m),encoding='utf-8')
    def table():
        return pd.DataFrame([{'N':n,'replicate':r,'metric':m,'estimate':1.,'halfwidth':0.,'tolerance':.25,'pass':True} for n in SIZES for r in range(30) for m in ['mean','std','P90','P95']+['exceed_'+str(v) for v in THRESHOLDS]])
    class Closure(unittest.TestCase):
        def test_loader_valid_and_semantic_corruptions(self):
            mutations=[('version',lambda b,d:b.update(schema_version='incompatible')),('missing_model',lambda b,d:b['models'].pop('M4')),
                ('order',lambda b,d:b['models']['M2']['dependence'].update(phase_order=list(reversed(PHASES)))),
                ('nan_transform',lambda b,d:b['models']['M2']['transform'].update(Q_log1p_mean=float('nan'))),
                ('zero_scale',lambda b,d:b['models']['M2']['transform'].update(amount_log_std=0)),
                ('bad_coefficients',lambda b,d:b['models']['M2']['models'][PHASES[0]].update(location_coefficients=[1.])),
                ('wrong_design',lambda b,d:b['models']['M2']['models'][PHASES[0]]['location_names'].__setitem__(1,'wrong')),
                ('missing_phase',lambda b,d:b['models']['M4']['models'].pop(PHASES[2])),
                ('invalid_probability',lambda b,d:b['models']['M2']['models'][PHASES[1]].update(p_zero=2)),
                ('unknown_government',lambda b,d:d.__setitem__(GOV,['UNKNOWN']*6)),
                ('duplicate_ids',lambda b,d:d.__setitem__('procedure_code',['1']*6)),
                ('missing_ids',lambda b,d:d.__setitem__('cv_dependency_group',[None]*6)),
                ('negative_weight',lambda b,d:d.__setitem__('empirical_row_weight',[-1.]*6)),
                ('wrong_scenario',lambda b,d:d.__setitem__('asymmetry_scenario',['high']*6)),
                ('invalid_amount',lambda b,d:d.__setitem__(AMOUNT,[0.]*6))]
            for name,mutate in mutations:
                with self.subTest(case=name),tempfile.TemporaryDirectory() as tmp:
                    f=Path(tmp)/'source';b,d=fixture(f);load_contract(f);mutate(b,d)
                    if name=='nan_transform':
                        # canonical JSON rejects NaN; recompute using finite hash
                        # representation not needed: corruption must fail either check.
                        (f/'05_7_simulation_bundle.json').write_text(json.dumps(b),encoding='utf-8')
                    else:write(f,b,d)
                    with self.assertRaises((ValueError,KeyError,TypeError,np.linalg.LinAlgError)):load_contract(f)
        def test_loader_hash_manifest_and_csv_routes(self):
            for case in ['csv','json','hash','manifest_schema','duplicate','missing','traversal','model_hash']:
                with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                    f=Path(tmp)/'source';b,d=fixture(f);mp=f/'05_export_manifest.json';m=json.loads(mp.read_text())
                    if case in ['csv','json']:(f/('05_8_joint_profiles.csv' if case=='csv' else '05_7_simulation_bundle.json')).write_text('altered')
                    elif case=='hash':m['outputs'][0]['sha256']='0'*64
                    elif case=='manifest_schema':m['schema_version']='other'
                    elif case=='duplicate':m['outputs'].append(m['outputs'][0])
                    elif case=='missing':m['outputs'].pop()
                    elif case=='traversal':m['outputs'][0]['path']='../outside.json'
                    elif case=='model_hash':
                        b['models']['M4']['model_sha256']='0'*64;(f/'05_7_simulation_bundle.json').write_text(json.dumps(b));m['outputs'][0]['sha256']=sha(f/'05_7_simulation_bundle.json')
                    mp.write_text(json.dumps(m))
                    with self.assertRaises((ValueError,KeyError)):load_contract(f)
        def test_rule_27_of_30_and_simultaneous_metrics(self):
            t=table();t.loc[t.replicate.ge(27)&t.metric.eq('P95'),'halfwidth']=1.
            self.assertEqual(decide(t)['recommended_N'],1000)
            t.loc[t.replicate.eq(26)&t.metric.eq('exceed_180'),'halfwidth']=1.
            self.assertEqual(decide(t)['status'],'PRECISION_NOT_REACHED')
        def test_missing_duplicate_or_forged_pass(self):
            t=table()
            for bad in [t.iloc[1:],pd.concat([t,t.iloc[[0]]]),t[t.metric.ne('P90')]]:
                with self.assertRaises(ValueError):decide(bad)
            t['halfwidth']=10.;t['pass']=True;self.assertIsNone(decide(t)['recommended_N'])
        def test_larger_sizes_and_last_size(self):
            t=table();t.loc[t.N.eq(1000),'estimate']=10.
            self.assertNotEqual(decide(t)['recommended_N'],1000)
            t=table();t.loc[t.N.ne(100000),'halfwidth']=10.
            result=decide(t);self.assertEqual(result['recommended_N'],100000);self.assertFalse(result['larger_size_confirmation'])
        def test_metrics_tolerances_per_run(self):
            x=np.exp(np.random.default_rng(9).normal(2,1,1000));a=precision_metrics(x)
            self.assertEqual(len(a),12);self.assertEqual(a[0]['tolerance'],max(.25,.005*x.mean()))
            self.assertEqual(a[1]['tolerance'],max(.5,.01*x.std(ddof=1)))
            self.assertEqual(a[2]['tolerance'],max(.5,.01*np.quantile(x,.9)))
            self.assertEqual(a[3]['tolerance'],max(1.,.02*np.quantile(x,.95)))
            self.assertTrue(all(m['tolerance']==.005 for m in a[4:]));self.assertGreater(a[1]['halfwidth'],0)
        def test_chunked_draws_and_metrics_exact(self):
            with tempfile.TemporaryDirectory() as tmp:
                source=Path(tmp)/'source';fixture(source);b,d,_=load_contract(source)
                for name in ['M1','M2','M4']:
                    b['models'][name]['dependence']['latent_correlation']=[[1,0,.6],[0,1,0],[.6,0,1]]
                    rng=stream(2,'equivalence',1003,0);indices=rng.choice(len(d),1003)
                    expected=simulate_totals(d,indices,b['models'][name],rng)
                    for chunk in [1,7,1000,4096]:
                        rng=stream(2,'equivalence',1003,0);same=rng.choice(len(d),1003)
                        actual=simulate_totals(d,same,b['models'][name],rng,chunk)
                        np.testing.assert_allclose(actual,expected,rtol=1e-13,atol=1e-12)
                        for left,right in zip(precision_metrics(actual),precision_metrics(expected)):
                            self.assertEqual(left['metric'],right['metric']);self.assertEqual(left['pass'],right['pass'])
                            for field in ['estimate','halfwidth','tolerance']:np.testing.assert_allclose(left[field],right[field],rtol=1e-13,atol=1e-12)
                with self.assertRaises(ValueError):simulate_totals(d,indices,b['models']['M2'],rng,0)
        def test_supplement_plan_and_total(self):
            plan=protocol_plan('supplement');self.assertEqual(len(plan),6)
            self.assertEqual(30*sum(sum(v) for v in plan.values()),544500000)
            self.assertFalse(any('low' in k for k in plan));self.assertEqual(max(max(v) for v in plan.values()),3000000)
            with self.assertRaises(ValueError):protocol_plan('other')
        def test_supplement_streams_and_selection(self):
            for key,sizes in protocol_plan('supplement').items():
                a=stream(2026110306,'supplement_v1:'+key,sizes[0],0).random(20)
                self.assertFalse(np.array_equal(a,stream(20251025,key,sizes[0],0).random(20)))
                rows=[{'N':n,'replicate':r,'metric':m,'estimate':1.,'halfwidth':0. if n==sizes[-1] else 10.,'tolerance':.25} for n in sizes for r in range(30) for m in ['mean','std','P90','P95']+['exceed_'+str(v) for v in THRESHOLDS]]
                result=decide(pd.DataFrame(rows),sizes=sizes);self.assertEqual(result['recommended_N'],sizes[-1]);self.assertFalse(result['larger_size_confirmation'])
        def test_supplement_publication(self):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);source=root/'source';fixture(source);before={p.name:sha(p) for p in source.iterdir()}
                original_plan=protocol_plan
                def small_plan(protocol):return {k:[20,40,60] for k in original_plan(protocol)}
                with mock.patch.dict(globals(),{'protocol_plan':small_plan,'simulate_profiles':lambda data,model,rng:np.zeros((len(data),4))}):
                    out=run_study(source,root/'output',2026110306,protocol='supplement');result=verify_publication(out)
                    self.assertEqual(result['protocol'],'supplement');self.assertEqual(result['seed'],2026110306)
                    self.assertEqual(result['stream_namespace'],'supplement_v1:');self.assertEqual(len(result['decisions']),6)
                    self.assertEqual(len(pd.read_csv(out/'06_1_convergence_metrics.csv')),6*3*30*12)
                self.assertEqual(before,{p.name:sha(p) for p in source.iterdir()})
        def test_fixed_profile_is_not_resampled(self):
            with tempfile.TemporaryDirectory() as tmp:
                f=Path(tmp)/'source';_,_=fixture(f);b,d,_=load_contract(f)
                fixed=pd.concat([d.iloc[[0]]]*200,ignore_index=True)
                before=fixed.copy(deep=True);v=simulate_profiles(fixed,b['models']['M4'],stream(3,'fixed',200,0))
                pd.testing.assert_frame_equal(before,fixed);self.assertEqual(v.shape,(200,4));self.assertGreater(v[:,3].std(),0)
        def test_publication_success_failure_and_integrity(self):
            for failure in [False,True]:
                with self.subTest(failure=failure),tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);source=root/'source';fixture(source);before={p.name:sha(p) for p in source.iterdir()}
                    protected=root/'protected.bin';protected.write_bytes(b'unchanged');ph=sha(protected)
                    original_decide=decide
                    with mock.patch.dict(globals(),{'SIZES':[20,40],'decide':lambda t,sizes=None:original_decide(t,sizes=sizes or [20,40]),
                        'simulate_profiles':lambda data,model,rng:np.zeros((len(data),4))}):
                        if failure:
                            with mock.patch.dict(globals(),{'verify_publication':mock.Mock(side_effect=ValueError('deliberate failure before rename'))}):
                                with self.assertRaisesRegex(ValueError,'deliberate'):run_study(source,root/'output')
                            self.assertFalse((root/'output/02_results/03_stochastic_simulation').exists())
                            self.assertFalse(list((root/'output/02_results').glob('.06_*')))
                        else:
                            out=run_study(source,root/'output');verify_publication(out)
                            with self.assertRaises(FileExistsError):run_study(source,root/'output')
                            (out/'06_1_convergence_metrics.csv').write_text('altered')
                            with self.assertRaisesRegex(ValueError,'hash'):verify_publication(out)
                    self.assertEqual(ph,sha(protected));self.assertEqual(before,{p.name:sha(p) for p in source.iterdir()})
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Closure))
    if not result.wasSuccessful():raise RuntimeError('Closure tests failed')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle-dir',type=Path);parser.add_argument('--output-root',type=Path);parser.add_argument('--protocol',choices=['initial','supplement'],default='initial');parser.add_argument('--seed',type=int);parser.add_argument('--chunk-size',type=int);parser.add_argument('--self-test',action='store_true');args=parser.parse_args()
    if args.self_test:
        self_test()
        return closure_tests()
    if args.bundle_dir is None or args.output_root is None:parser.error('--bundle-dir and fresh --output-root required')
    seed=args.seed if args.seed is not None else (2026110306 if args.protocol=='supplement' else 20251025)
    print(run_study(args.bundle_dir,args.output_root,seed,protocol=args.protocol,chunk_size=args.chunk_size))

if __name__=='__main__':main()
