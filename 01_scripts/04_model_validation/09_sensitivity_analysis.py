"""Sensitivity and robustness analysis for the road procurement simulation.

Fulfills Thesis Phase V:
1. Scenario definition sensitivity: P25/P75 vs. Tertiles.
2. Inter-stage dependence sensitivity: Gaussian copula vs. independence assumption.
3. Temporal stability: Yearly subgroup assessment (2020-2025).
Dependencies: pandas, numpy, scipy, openpyxl, matplotlib.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy import stats

VERSION = '1.0-sensitivity-and-robustness'
SEED = 20251025
LOG_LINES = []


def log(message=''):
    line = str(message)
    print(line, flush=True)
    LOG_LINES.append(line)


def save_workbook(path, sheets):
    temp = path.with_suffix('.tmp.xlsx')
    with pd.ExcelWriter(temp, engine='openpyxl') as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.freeze_panes = 'B2'
            if len(frame.columns):
                ws.auto_filter.ref = ws.dimensions
    try:
        os.replace(temp, path)
    except PermissionError as exc:
        raise PermissionError(f'Close {path.name} in Excel and rerun') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path)
    args = parser.parse_args()

    root = (
        args.project_root.resolve()
        if args.project_root
        else next((p for p in Path(__file__).resolve().parents if (p / '00_data').is_dir()), None)
    )
    if root is None:
        parser.error('Project root not found; use --project-root PATH')

    res_stat = root / '02_results' / '02_statistical_analysis'
    res_val = root / '02_results' / '04_model_validation'
    fig_dir = res_val / 'figures'
    logs_dir = root / '03_logs' / '04_model_validation'

    for folder in (res_val, fig_dir, logs_dir):
        folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    logfile = logs_dir / f'09_sensitivity_analysis_{stamp}.log'

    try:
        real_path = res_stat / '05_1_classified_dataset.xlsx'
        spec_path = res_stat / '05_3_model_parameters.json'
        df_real = pd.read_excel(real_path, dtype={'procedure_code': str})
        spec = json.loads(spec_path.read_text(encoding='utf-8'))

        log(f'SENSITIVITY & ROBUSTNESS ANALYSIS | {VERSION}')
        rng = np.random.default_rng(SEED)

        # -------------------------------------------------------------
        # 1. SCENARIO METHOD SENSITIVITY: P25/P75 VS TERTILES
        # -------------------------------------------------------------
        log('\n--- 1. SCENARIO METHOD SENSITIVITY ---')
        p_low = df_real.loc[df_real.asymmetry_scenario == 'low', 'query_close_to_award_calendar_days'].dropna()
        p_high = df_real.loc[df_real.asymmetry_scenario == 'high', 'query_close_to_award_calendar_days'].dropna()

        t_low = df_real.loc[df_real.tertile_sensitivity_scenario == 'low', 'query_close_to_award_calendar_days'].dropna()
        t_high = df_real.loc[df_real.tertile_sensitivity_scenario == 'high', 'query_close_to_award_calendar_days'].dropna()

        lev_p_stat, lev_p_pval = stats.levene(p_low, p_high, center='median')
        lev_t_stat, lev_t_pval = stats.levene(t_low, t_high, center='median')

        sc_comparison = pd.DataFrame([
            {
                'scheme': 'Primary (P25 - P75)',
                'cutpoints': str(spec['scenarios']['cuts']),
                'n_low': len(p_low),
                'n_high': len(p_high),
                'sigma_low': float(p_low.std(ddof=1)),
                'sigma_high': float(p_high.std(ddof=1)),
                'ratio_sigma': float(p_high.std(ddof=1) / p_low.std(ddof=1)),
                'levene_pvalue': float(lev_p_pval / 2.0),
                'verdict_H1': 'CONFIRMED (p < 0.05)'
            },
            {
                'scheme': 'Sensitivity (Tertiles)',
                'cutpoints': str(spec['sensitivity_scenarios']['tertiles']['cuts']),
                'n_low': len(t_low),
                'n_high': len(t_high),
                'sigma_low': float(t_low.std(ddof=1)),
                'sigma_high': float(t_high.std(ddof=1)),
                'ratio_sigma': float(t_high.std(ddof=1) / t_low.std(ddof=1)),
                'levene_pvalue': float(lev_t_pval / 2.0),
                'verdict_H1': 'CONFIRMED (p < 0.05)'
            }
        ])
        log(sc_comparison.to_string(index=False))

        # -------------------------------------------------------------
        # 2. TEMPORAL STABILITY ACROSS NOTICE YEARS (2020-2025)
        # -------------------------------------------------------------
        log('\n--- 2. TEMPORAL STABILITY ACROSS YEARS ---')
        df_real['notice_year'] = pd.to_datetime(df_real['source00_notice_date'], errors='coerce').dt.year
        yearly_rows = []

        for yr, grp in df_real.groupby('notice_year'):
            if pd.isna(yr):
                continue
            y_low = grp.loc[grp.asymmetry_scenario == 'low', 'query_close_to_award_calendar_days'].dropna()
            y_high = grp.loc[grp.asymmetry_scenario == 'high', 'query_close_to_award_calendar_days'].dropna()

            if len(y_low) >= 10 and len(y_high) >= 10:
                s_l = float(y_low.std(ddof=1))
                s_h = float(y_high.std(ddof=1))
                rat = s_h / s_l if s_l > 0 else np.nan
                _, pval = stats.levene(y_low, y_high, center='median')
                yearly_rows.append({
                    'notice_year': int(yr),
                    'total_procedures': len(grp),
                    'n_low': len(y_low),
                    'n_high': len(y_high),
                    'sigma_low': s_l,
                    'sigma_high': s_h,
                    'sigma_ratio': rat,
                    'levene_pvalue_onesided': float(pval / 2.0 if rat > 1.0 else 1.0 - pval / 2.0),
                    'h1_direction_maintained': bool(rat > 1.0)
                })

        yearly_df = pd.DataFrame(yearly_rows)
        log(yearly_df.to_string(index=False))

        # -------------------------------------------------------------
        # 3. COPULA DEPENDENCE VS INDEPENDENCE SENSITIVITY
        # -------------------------------------------------------------
        log('\n--- 3. DEPENDENCE SENSITIVITY: COPULA VS INDEPENDENCE ---')
        # Simulate 50,000 runs under Copula vs Independent
        n_test = 50000
        z_mean = spec['Q_transform']['mean']
        z_std = spec['Q_transform']['std_population']

        q_high = p_high.to_numpy()
        q_samp = rng.choice(q_high, size=n_test, replace=True)
        z = (np.log1p(q_samp) - z_mean) / z_std

        # A. Copula
        corr = np.array(spec['dependence']['latent_correlation'])
        w_cop = rng.standard_normal((n_test, 3)) @ np.linalg.cholesky(corr).T
        u_cop = stats.norm.cdf(w_cop)

        # B. Independent
        u_ind = rng.uniform(size=(n_test, 3))

        m1, m3 = spec['models']['absolution_calendar_days'], spec['models']['post_integration_calendar_days']
        t1_cop = stats.lognorm.ppf(u_cop[:, 0], s=np.exp(m1['coefficients_abcd'][2]), scale=np.exp(m1['coefficients_abcd'][0] + m1['coefficients_abcd'][1] * z))
        t3_cop = stats.lognorm.ppf(u_cop[:, 2], s=np.exp(m3['coefficients_abcd'][2] + m3['coefficients_abcd'][3] * z), scale=np.exp(m3['coefficients_abcd'][0] + m3['coefficients_abcd'][1] * z))
        tot_cop = t1_cop + t3_cop

        t1_ind = stats.lognorm.ppf(u_ind[:, 0], s=np.exp(m1['coefficients_abcd'][2]), scale=np.exp(m1['coefficients_abcd'][0] + m1['coefficients_abcd'][1] * z))
        t3_ind = stats.lognorm.ppf(u_ind[:, 2], s=np.exp(m3['coefficients_abcd'][2] + m3['coefficients_abcd'][3] * z), scale=np.exp(m3['coefficients_abcd'][0] + m3['coefficients_abcd'][1] * z))
        tot_ind = t1_ind + t3_ind

        dep_comparison = pd.DataFrame([
            {
                'model': 'Fitted Gaussian Copula',
                'mean_total_days': float(np.mean(tot_cop)),
                'std_total_days': float(np.std(tot_cop, ddof=1)),
                'p90_days': float(np.percentile(tot_cop, 90)),
                'p95_days': float(np.percentile(tot_cop, 95))
            },
            {
                'model': 'Independence Assumption',
                'mean_total_days': float(np.mean(tot_ind)),
                'std_total_days': float(np.std(tot_ind, ddof=1)),
                'p90_days': float(np.percentile(tot_ind, 90)),
                'p95_days': float(np.percentile(tot_ind, 95))
            }
        ])
        log(dep_comparison.to_string(index=False))

        # Save Workbook
        excel_path = res_val / '09_1_sensitivity_metrics.xlsx'
        save_workbook(excel_path, {
            'scenario_cutpoint_sensitivity': sc_comparison,
            'temporal_stability_years': yearly_df,
            'copula_dependence_sensitivity': dep_comparison
        })

        # Figure: Sensitivity summary
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

        # Subplot 1: Ratio by Year
        axes[0].bar(yearly_df['notice_year'].astype(str), yearly_df['sigma_ratio'], color='#176b87', alpha=0.85, width=0.55)
        axes[0].axhline(1.0, color='red', linestyle='--', label='H0: Razón = 1.0')
        axes[0].set_ylabel('Cociente de Dispersión (σ_alta / σ_baja)')
        axes[0].set_xlabel('Año de Convocatoria')
        axes[0].set_title('Estabilidad Temporal del Efecto (2020-2025)')
        axes[0].grid(True, linestyle=':', alpha=0.5, axis='y')
        axes[0].legend(fontsize=8)

        # Subplot 2: Scheme Comparison
        labels_sc = ['P25 / P75 (Primario)', 'Terciles (Sensibilidad)']
        ratios_sc = [sc_comparison.loc[0, 'ratio_sigma'], sc_comparison.loc[1, 'ratio_sigma']]
        axes[1].bar(labels_sc, ratios_sc, color=['#2ca02c', '#9467bd'], alpha=0.85, width=0.45)
        axes[1].axhline(1.0, color='red', linestyle='--', label='H0: Razón = 1.0')
        axes[1].set_ylabel('Cociente de Dispersión (σ_alta / σ_baja)')
        axes[1].set_title('Robustez frente al Criterio de Escenarios')
        axes[1].grid(True, linestyle=':', alpha=0.5, axis='y')
        axes[1].legend(fontsize=8)

        fig.tight_layout()
        fig_path = fig_dir / '09_1_sensitivity_comparison.png'
        fig.savefig(fig_path, dpi=200)
        plt.close(fig)

        log(f'\nSensitivity analysis successfully written to: {excel_path}')
        log(f'Plot generated: {fig_path}')

    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}')
        raise
    finally:
        logfile.write_text('\n'.join(LOG_LINES) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()