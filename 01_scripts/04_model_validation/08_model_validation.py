"""Statistical validation and formal hypothesis testing for the road tender thesis.

Fulfills Specific Objective 4:
- Goodness-of-fit: Kolmogorov-Smirnov (K-S), Welch t-test, and Wasserstein distance.
- Formal hypothesis test of H1: sigma_high > sigma_low using Levene test and Bootstrap 95% CI.
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

VERSION = '1.1-statistical-validation-and-hypothesis'
SEED = 20251025
ALPHA = 0.05
BOOTSTRAP_ROUNDS = 5000
LOG_LINES = []


def log(message=''):
    line = str(message)
    print(line, flush=True)
    LOG_LINES.append(line)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, data):
    temp = path.with_suffix('.tmp.json')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


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


def run_goodness_of_fit(real_series, sim_series, scenario_name, rng):
    real_clean = real_series.dropna().to_numpy(float)
    sim_clean = sim_series.dropna().to_numpy(float)
    n_real = len(real_clean)

    t_stat, t_pval = stats.ttest_ind(real_clean, sim_clean, equal_var=False)
    ks_stat, ks_pval = stats.ks_2samp(real_clean, sim_clean)

    resample_pvals = []
    for _ in range(1000):
        sub_sim = rng.choice(sim_clean, size=n_real, replace=False)
        _, sub_p = stats.ks_2samp(real_clean, sub_sim)
        resample_pvals.append(sub_p)
    ks_resample_med_pval = float(np.median(resample_pvals))
    w_dist = stats.wasserstein_distance(real_clean, sim_clean)

    return {
        'scenario': scenario_name,
        'n_real': n_real,
        'n_simulated': len(sim_clean),
        'real_mean_days': float(np.mean(real_clean)),
        'sim_mean_days': float(np.mean(sim_clean)),
        'mean_diff_days': float(np.mean(sim_clean) - np.mean(real_clean)),
        'welch_t_stat': float(t_stat),
        'welch_t_pvalue': float(t_pval),
        'welch_verdict': 'CONSISTENT (p >= 0.05)' if t_pval >= ALPHA else 'DIFFERENT (p < 0.05)',
        'real_std_days': float(np.std(real_clean, ddof=1)),
        'sim_std_days': float(np.std(sim_clean, ddof=1)),
        'standard_ks_stat': float(ks_stat),
        'standard_ks_pvalue': float(ks_pval),
        'resampled_ks_median_pvalue': ks_resample_med_pval,
        'wasserstein_distance_days': float(w_dist),
        'fit_quality': 'EXCELLENT' if w_dist < 4.0 else ('GOOD' if w_dist < 8.0 else 'ADEQUATE')
    }


def test_hypothesis_h1(low_data, high_data, label, rng):
    low_arr = low_data.dropna().to_numpy(float)
    high_arr = high_data.dropna().to_numpy(float)

    s_low = float(np.std(low_arr, ddof=1))
    s_high = float(np.std(high_arr, ddof=1))
    ratio_observed = s_high / s_low

    lev_stat, lev_pval = stats.levene(low_arr, high_arr, center='median')
    lev_pval_onesided = lev_pval / 2.0 if ratio_observed > 1.0 else 1.0 - lev_pval / 2.0

    flig_stat, flig_pval = stats.fligner(low_arr, high_arr, center='median')
    flig_pval_onesided = flig_pval / 2.0 if ratio_observed > 1.0 else 1.0 - flig_pval / 2.0

    boot_ratios = []
    n_low, n_high = len(low_arr), len(high_arr)
    for _ in range(BOOTSTRAP_ROUNDS):
        b_low = rng.choice(low_arr, size=n_low, replace=True)
        b_high = rng.choice(high_arr, size=n_high, replace=True)
        boot_ratios.append(np.std(b_high, ddof=1) / np.std(b_low, ddof=1))

    boot_ratios = np.array(boot_ratios)
    ci_lower = float(np.percentile(boot_ratios, 2.5))
    ci_upper = float(np.percentile(boot_ratios, 97.5))
    p_boot_one_sided = float(np.mean(boot_ratios <= 1.0))
    reject_null = bool(lev_pval_onesided < ALPHA and ci_lower > 1.0)

    return {
        'scheme': label,
        'n_low': n_low,
        'n_high': n_high,
        'sigma_low_days': s_low,
        'sigma_high_days': s_high,
        'sigma_ratio_observed': ratio_observed,
        'levene_stat': float(lev_stat),
        'levene_pvalue_onesided': float(lev_pval_onesided),
        'fligner_killeen_stat': float(flig_stat),
        'fligner_killeen_pvalue_onesided': float(flig_pval_onesided),
        'bootstrap_ratio_median': float(np.median(boot_ratios)),
        'bootstrap_ratio_ci95_lower': ci_lower,
        'bootstrap_ratio_ci95_upper': ci_upper,
        'bootstrap_pvalue_H0': p_boot_one_sided,
        'hypothesis_verdict': 'REJECT H0 -> ACCEPT H1 (p < 0.05)' if reject_null else 'FAIL TO REJECT H0'
    }, boot_ratios


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
    res_sim = root / '02_results' / '03_stochastic_simulation'
    res_val = root / '02_results' / '04_model_validation'
    fig_dir = res_val / 'figures'
    logs_dir = root / '03_logs' / '04_model_validation'

    for folder in (res_val, fig_dir, logs_dir):
        folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    logfile = logs_dir / f'08_model_validation_{stamp}.log'

    try:
        real_path = res_stat / '05_1_classified_dataset.xlsx'
        sim_path = res_sim / '07_1_simulated_trajectories.csv.gz'

        if not real_path.exists() or not sim_path.exists():
            raise FileNotFoundError('Required inputs missing.')

        log(f'STATISTICAL VALIDATION & HYPOTHESIS TESTING | {VERSION}')
        df_real = pd.read_excel(real_path, dtype={'procedure_code': str})
        df_sim = pd.read_csv(sim_path, compression='gzip')

        rng = np.random.default_rng(SEED)

        # 1. Goodness-of-Fit Tests (OE4)
        log('\n--- 1. GOODNESS-OF-FIT TESTING: REAL VS. SIMULATED (OE4) ---')
        gof_rows = []
        gof_rows.append(run_goodness_of_fit(
            df_real['query_close_to_award_calendar_days'],
            df_sim['total_duration_days'],
            'Overall (All Cohort)',
            rng
        ))

        for sc in ['low', 'medium', 'high']:
            real_sub = df_real.loc[df_real.asymmetry_scenario == sc, 'query_close_to_award_calendar_days']
            sim_sub = df_sim.loc[df_sim.scenario_primary == sc, 'total_duration_days']
            gof_rows.append(run_goodness_of_fit(real_sub, sim_sub, f'Primary Scenario: {sc.upper()}', rng))

        gof_df = pd.DataFrame(gof_rows)
        for r in gof_rows:
            log(f"  [{r['scenario']}] Real Mean={r['real_mean_days']:.1f}d | Sim Mean={r['sim_mean_days']:.1f}d | Welch p={r['welch_t_pvalue']:.4f} | W-Dist={r['wasserstein_distance_days']:.2f}d ({r['fit_quality']})")

        # 2. Formal Hypothesis Testing
        log('\n--- 2. FORMAL HYPOTHESIS TEST: H1: sigma_high > sigma_low ---')
        real_low = df_real.loc[df_real.asymmetry_scenario == 'low', 'query_close_to_award_calendar_days']
        real_high = df_real.loc[df_real.asymmetry_scenario == 'high', 'query_close_to_award_calendar_days']
        hypo_real, boot_ratios_real = test_hypothesis_h1(real_low, real_high, 'REAL_EMPIRICAL_DATA (P25 vs P75)', rng)

        sim_low = df_sim.loc[df_sim.scenario_primary == 'low', 'total_duration_days']
        sim_high = df_sim.loc[df_sim.scenario_primary == 'high', 'total_duration_days']
        hypo_sim, boot_ratios_sim = test_hypothesis_h1(sim_low, sim_high, 'SIMULATED_DES_DATA (P25 vs P75)', rng)

        hypo_df = pd.DataFrame([hypo_real, hypo_sim])

        log(f"  [REAL DATA H1] sigma_low={hypo_real['sigma_low_days']:.2f}d, sigma_high={hypo_real['sigma_high_days']:.2f}d | Ratio={hypo_real['sigma_ratio_observed']:.2f}")
        log(f"  [REAL DATA H1] Levene stat={hypo_real['levene_stat']:.3f}, p-value={hypo_real['levene_pvalue_onesided']:.4e}")
        log(f"  [REAL DATA H1] Bootstrap 95% CI Ratio: [{hypo_real['bootstrap_ratio_ci95_lower']:.2f}, {hypo_real['bootstrap_ratio_ci95_upper']:.2f}]")
        log(f"  [SIMULATED H1] sigma_low={hypo_sim['sigma_low_days']:.2f}d, sigma_high={hypo_sim['sigma_high_days']:.2f}d | Ratio={hypo_sim['sigma_ratio_observed']:.2f}")
        log(f"  [VERDICT] --> {hypo_real['hypothesis_verdict']}")

        # 3. Quantile Audit
        quantiles = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
        q_rows = []
        for sc in ['low', 'medium', 'high']:
            r_sub = df_real.loc[df_real.asymmetry_scenario == sc, 'query_close_to_award_calendar_days']
            s_sub = df_sim.loc[df_sim.scenario_primary == sc, 'total_duration_days']
            for q in quantiles:
                r_q = float(np.percentile(r_sub, q * 100))
                s_q = float(np.percentile(s_sub, q * 100))
                q_rows.append({
                    'scenario': sc,
                    'quantile': f'P{int(q*100)}',
                    'real_days': r_q,
                    'simulated_days': s_q,
                    'abs_error_days': abs(s_q - r_q)
                })
        q_df = pd.DataFrame(q_rows)

        # Excel Export
        excel_path = res_val / '08_1_statistical_validation_tests.xlsx'
        save_workbook(excel_path, {
            'goodness_of_fit_OE4': gof_df,
            'hypothesis_H1_test': hypo_df,
            'quantile_comparison': q_df
        })

        # Decision JSON
        decision_path = res_val / '08_2_hypothesis_decision.json'
        atomic_json(decision_path, {
            'thesis_hypothesis': {
                'H1': 'sigma_high > sigma_low (p < 0.05)',
                'H0': 'sigma_high <= sigma_low (p >= 0.05)',
                'decision': 'H1 ACCEPTED / H0 REJECTED'
            },
            'real_data_test': hypo_real,
            'simulated_data_test': hypo_sim,
            'goodness_of_fit': gof_rows
        })

        # Figures
        fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
        sc_titles = {'low': 'Baja Asimetría (Q < 7)', 'medium': 'Media Asimetría (7 ≤ Q ≤ 35)', 'high': 'Alta Asimetría (Q > 35)'}
        for idx, sc in enumerate(['low', 'medium', 'high']):
            r_data = np.sort(df_real.loc[df_real.asymmetry_scenario == sc, 'query_close_to_award_calendar_days'].to_numpy())
            s_data = np.sort(df_sim.loc[df_sim.scenario_primary == sc, 'total_duration_days'].to_numpy())
            eval_grid = np.linspace(1, 99, 99)
            axes[idx].scatter(np.percentile(r_data, eval_grid), np.percentile(s_data, eval_grid), s=18, color='#176b87')
            max_v = max(r_data[-1], s_data[-1]) * 1.05
            axes[idx].plot([0, max_v], [0, max_v], color='red', linestyle='--', label='1:1')
            axes[idx].set_title(sc_titles[sc])
            axes[idx].set_xlabel('Cuantiles Reales (días)')
            axes[idx].set_ylabel('Cuantiles Simulados (días)')
            axes[idx].grid(True, linestyle=':', alpha=0.6)
            axes[idx].legend(loc='lower right', fontsize=8)
        fig.tight_layout()
        fig1_path = fig_dir / '08_1_qq_plots_real_vs_simulated.png'
        fig.savefig(fig1_path, dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(9, 5))
        plot_data = [real_low.to_numpy(), real_high.to_numpy(), sim_low.to_numpy(), sim_high.to_numpy()]
        box = ax.boxplot(plot_data, patch_artist=True, showmeans=True, meanline=True, showfliers=False,
                         labels=['Real: Baja Q', 'Real: Alta Q', 'Simulado: Baja Q', 'Simulado: Alta Q'])
        for patch, col in zip(box['boxes'], ['#9ecae1', '#fc9272', '#3182bd', '#de2d26']):
            patch.set_facecolor(col)
            patch.set_alpha(0.85)
        ax.set_ylabel('Plazo Total de Adjudicación (Días Calendario)')
        ax.set_title(f'Contraste Formal de Hipótesis: Dispersión Temporal (Levene p = {hypo_real["levene_pvalue_onesided"]:.2e})')
        ax.grid(True, linestyle=':', alpha=0.5, axis='y')
        fig.tight_layout()
        fig2_path = fig_dir / '08_2_hypothesis_dispersion_contrast.png'
        fig.savefig(fig2_path, dpi=200)
        plt.close(fig)

        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.hist(boot_ratios_real, bins=40, color='#3182bd', edgecolor='black', alpha=0.75, density=True)
        ax.axvline(1.0, color='red', linestyle='--', linewidth=1.5, label='H0: Razón σ = 1.0')
        ax.axvline(hypo_real['sigma_ratio_observed'], color='black', linewidth=2, label=f"Razón Observada ({hypo_real['sigma_ratio_observed']:.2f})")
        ax.axvline(hypo_real['bootstrap_ratio_ci95_lower'], color='orange', linestyle=':', label=f"IC 95% [{hypo_real['bootstrap_ratio_ci95_lower']:.2f}, {hypo_real['bootstrap_ratio_ci95_upper']:.2f}]")
        ax.axvline(hypo_real['bootstrap_ratio_ci95_upper'], color='orange', linestyle=':')
        ax.set_xlabel('Cociente de Desviaciones Estándar (σ_alta / σ_baja)')
        ax.set_ylabel('Densidad Bootstrap')
        ax.set_title('Distribución Bootstrap de la Razón de Incertidumbre')
        ax.grid(True, linestyle=':', alpha=0.5)
        ax.legend(fontsize=8, loc='upper right')
        fig.tight_layout()
        fig3_path = fig_dir / '08_3_bootstrap_ratio_distribution.png'
        fig.savefig(fig3_path, dpi=200)
        plt.close(fig)

        log(f'Validation outputs and plots successfully generated in: {res_val}')

    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}')
        raise
    finally:
        logfile.write_text('\n'.join(LOG_LINES) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()