"""Discrete Event Simulation (DES) and Monte Carlo simulation of road tender durations.

Implements the stochastic timeline model across information asymmetry scenarios.
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

VERSION = '1.0-des-monte-carlo-simulation'
SEED = 20251025
EXCEEDANCE_THRESHOLDS = [30, 45, 60, 75, 90, 120, 150, 180]
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


def simulate_des_core(q_values, spec, rng):
    """Vectorized DES simulation engine applying Gaussian copula and marginals."""
    n = len(q_values)
    z_mean = spec['Q_transform']['mean']
    z_std = spec['Q_transform']['std_population']
    z = (np.log1p(q_values) - z_mean) / z_std

    # Gaussian copula
    corr = np.array(spec['dependence']['latent_correlation'])
    chol = np.linalg.cholesky(corr)
    w = rng.standard_normal((n, 3)) @ chol.T
    u = stats.norm.cdf(w)

    # Stage 1: Absolution of queries
    m1 = spec['models']['absolution_calendar_days']
    a1, b1, c1, d1 = m1['coefficients_abcd']
    scale1 = np.exp(a1 + b1 * z)
    shape1 = np.exp(c1 + d1 * z)
    delta_t1 = stats.lognorm.ppf(u[:, 0], s=shape1, scale=scale1)

    # Stage 2: Integration of bases (Hurdle)
    m2 = spec['models']['integration_calendar_days']
    p_zero = m2['p_zero']
    pos_support = np.array(m2['positive_values'])
    delta_t2 = np.zeros(n)
    pos_mask = u[:, 1] >= p_zero
    if np.any(pos_mask):
        u_star = (u[pos_mask, 1] - p_zero) / (1.0 - p_zero)
        indices = np.clip((u_star * len(pos_support)).astype(int), 0, len(pos_support) - 1)
        delta_t2[pos_mask] = pos_support[indices]

    # Stage 3: Post-Integration to Award
    m3 = spec['models']['post_integration_calendar_days']
    a3, b3, c3, d3 = m3['coefficients_abcd']
    scale3 = np.exp(a3 + b3 * z)
    shape3 = np.exp(c3 + d3 * z)
    delta_t3 = stats.lognorm.ppf(u[:, 2], s=shape3, scale=scale3)

    # Discrete Event Timeline: Cumulative Milestones
    event_0 = np.zeros(n)                   # Query Close (t=0)
    event_1 = event_0 + delta_t1            # Absolution End
    event_2 = event_1 + delta_t2            # Integration End
    event_3 = event_2 + delta_t3            # Award (Buena Pro)
    total_duration = event_3 - event_0

    # Rounded integer calendar days (analytical practice in civil procurement)
    return pd.DataFrame({
        'q_input': q_values,
        'stage1_absolution_days': delta_t1,
        'stage2_integration_days': delta_t2,
        'stage3_post_integration_days': delta_t3,
        'event1_absolution_milestone': event_1,
        'event2_integration_milestone': event_2,
        'event3_award_milestone': event_3,
        'total_duration_continuous': total_duration,
        'total_duration_days': np.maximum(1, np.round(total_duration)).astype(int)
    })


def compute_distribution_summary(df_group, label_name, label_val):
    """Calculate descriptive statistics, dispersion metrics, and quantiles."""
    rows = []
    variables = [
        ('total_duration_days', 'Plazo Total Adjudicación (días)'),
        ('stage1_absolution_days', 'Etapa 1: Absolución (días)'),
        ('stage2_integration_days', 'Etapa 2: Integración (días)'),
        ('stage3_post_integration_days', 'Etapa 3: Post-Integración a Buena Pro (días)')
    ]

    for col, desc in variables:
        series = df_group[col]
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        rows.append({
            'scheme': label_name,
            'scenario': label_val,
            'variable': col,
            'description': desc,
            'iterations_n': len(series),
            'mean': float(series.mean()),
            'std_dev': float(series.std(ddof=1)),
            'variance': float(series.var(ddof=1)),
            'cv_percent': float(series.std(ddof=1) / series.mean() * 100) if series.mean() > 0 else np.nan,
            'min': float(series.min()),
            'p10': float(series.quantile(0.10)),
            'p25': float(q1),
            'median_p50': float(series.quantile(0.50)),
            'p75': float(q3),
            'p90': float(series.quantile(0.90)),
            'p95': float(series.quantile(0.95)),
            'p99': float(series.quantile(0.99)),
            'max': float(series.max()),
            'iqr': float(q3 - q1)
        })
    return rows


def compute_exceedance_table(df_group, label_name, label_val, thresholds):
    """Compute empirical survival probabilities P(T > threshold)."""
    rows = []
    tot = df_group['total_duration_days'].to_numpy()
    n = len(tot)

    for thr in thresholds:
        prob = float(np.mean(tot > thr) * 100)
        rows.append({
            'scheme': label_name,
            'scenario': label_val,
            'threshold_calendar_days': thr,
            'exceedance_probability_percent': prob,
            'interpretation': f'P(T > {thr} días) = {prob:.2f}%'
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--iterations', type=int, help='Override iteration count (default from Script 06 decision)')
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
    fig_dir = res_sim / 'figures'
    logs_dir = root / '03_logs' / '03_stochastic_simulation'

    for folder in (res_sim, fig_dir, logs_dir):
        folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    logfile = logs_dir / f'07_discrete_event_simulation_{stamp}.log'

    try:
        spec_path = res_stat / '05_3_model_parameters.json'
        data_path = res_stat / '05_1_classified_dataset.xlsx'
        dec_path = res_sim / '06_2_convergence_decision.json'

        if not spec_path.exists() or not data_path.exists():
            raise FileNotFoundError('Required Script 05 artifacts missing.')

        spec = json.loads(spec_path.read_text(encoding='utf-8'))
        df_real = pd.read_excel(data_path, dtype={'procedure_code': str})

        # Determine N iterations
        if args.iterations and args.iterations > 0:
            n_sim = args.iterations
            n_source = 'cli_override'
        elif dec_path.exists():
            dec = json.loads(dec_path.read_text(encoding='utf-8'))
            n_sim = int(dec.get('recommended_operational_N', 50000))
            n_source = 'script06_convergence_decision'
        else:
            n_sim = 50000
            n_source = 'fallback_default'

        log(f'DISCRETE EVENT SIMULATION (DES) & MONTE CARLO | {VERSION}')
        log(f'Iterations per scenario: N={n_sim:,} (Source: {n_source}) | Seed: {SEED}')

        rng = np.random.default_rng(SEED)

        # 1. Primary Scenarios (P25 - P75)
        primary_cuts = spec['scenarios']['cuts']  # [7.0, 35.0]
        log(f'Primary scenario boundaries: Low Q < {primary_cuts[0]}, High Q > {primary_cuts[1]}')

        # 2. Sensitivity Scenarios (Tertiles)
        tertile_cuts = spec['sensitivity_scenarios']['tertiles']['cuts']  # [10, 27]
        log(f'Sensitivity tertile boundaries: Low Q <= {tertile_cuts[0]}, High Q > {tertile_cuts[1]}')

        sim_frames = []
        summary_rows = []
        exceedance_rows = []

        # Simulate Primary Scenarios
        for sc in ['low', 'medium', 'high']:
            sub_q = df_real.loc[df_real.asymmetry_scenario == sc, 'queries_observations_count'].to_numpy(float)
            q_boot = rng.choice(sub_q, size=n_sim, replace=True)
            res = simulate_des_core(q_boot, spec, rng)
            res['scenario_primary'] = sc
            res['scenario_tertile'] = np.nan
            sim_frames.append(res)

            summary_rows.extend(compute_distribution_summary(res, 'primary_P25_P75', sc))
            exceedance_rows.extend(compute_exceedance_table(res, 'primary_P25_P75', sc, EXCEEDANCE_THRESHOLDS))
            log(f'  [Primary] {sc.upper()}: Mean={res["total_duration_days"].mean():.2f} d, Std={res["total_duration_days"].std():.2f} d, P90={res["total_duration_days"].quantile(0.9):.1f} d')

        # Simulate Sensitivity Scenarios (Tertiles)
        for sc in ['low', 'medium', 'high']:
            sub_q = df_real.loc[df_real.tertile_sensitivity_scenario == sc, 'queries_observations_count'].to_numpy(float)
            q_boot = rng.choice(sub_q, size=n_sim, replace=True)
            res = simulate_des_core(q_boot, spec, rng)
            res['scenario_primary'] = np.nan
            res['scenario_tertile'] = sc

            summary_rows.extend(compute_distribution_summary(res, 'sensitivity_tertiles', sc))
            exceedance_rows.extend(compute_exceedance_table(res, 'sensitivity_tertiles', sc, EXCEEDANCE_THRESHOLDS))
            log(f'  [Tertiles] {sc.upper()}: Mean={res["total_duration_days"].mean():.2f} d, Std={res["total_duration_days"].std():.2f} d, P90={res["total_duration_days"].quantile(0.9):.1f} d')

        # Consolidated Simulation Output (Compressed)
        all_sim = pd.concat(sim_frames, ignore_index=True)
        traj_path = res_sim / '07_1_simulated_trajectories.csv.gz'
        all_sim.to_csv(traj_path, index=False, compression='gzip', encoding='utf-8')
        log(f'Simulation trajectories saved: {traj_path} ({len(all_sim):,} records)')

        # Metadata table
        meta = pd.DataFrame([
            {'parameter': 'version', 'value': VERSION},
            {'parameter': 'date_nature', 'value': 'published_schedule_not_verified_actual_events'},
            {'parameter': 'iterations_per_scenario', 'value': n_sim},
            {'parameter': 'iteration_selection_source', 'value': n_source},
            {'parameter': 'random_seed', 'value': SEED},
            {'parameter': 'empirical_cohort_n', 'value': len(df_real)},
            {'parameter': 'primary_cuts_P25_P75', 'value': str(primary_cuts)},
            {'parameter': 'sensitivity_cuts_tertiles', 'value': str(tertile_cuts)},
            {'parameter': 'stages_modeled', 'value': 'absolution, integration, post_integration_to_award'},
            {'parameter': 'dependence_copula', 'value': 'Gaussian copula fitted from training residuals'},
            {'parameter': 'run_utc', 'value': datetime.now(timezone.utc).isoformat()}
        ])

        summary_df = pd.DataFrame(summary_rows)
        exceed_df = pd.DataFrame(exceedance_rows)

        # Excel Audit Export
        summary_path = res_sim / '07_2_simulation_summary.xlsx'
        save_workbook(summary_path, {
            'primary_scenarios': summary_df.loc[summary_df.scheme == 'primary_P25_P75'],
            'sensitivity_tertiles': summary_df.loc[summary_df.scheme == 'sensitivity_tertiles'],
            'exceedance_risk': exceed_df,
            'metadata': meta
        })
        log(f'Simulation summary workbook saved: {summary_path}')

        # -------------------------------------------------------------
        # FIGURES FOR THESIS REPORT
        # -------------------------------------------------------------

        # Figure 1: Density Curves by Scenario (Primary)
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = {'low': '#1f77b4', 'medium': '#ff7f0e', 'high': '#d62728'}
        labels = {'low': f'Baja Asimetría (Q < {primary_cuts[0]:.0f})',
                  'medium': f'Media Asimetría ({primary_cuts[0]:.0f} ≤ Q ≤ {primary_cuts[1]:.0f})',
                  'high': f'Alta Asimetría (Q > {primary_cuts[1]:.0f})'}

        for sc in ['low', 'medium', 'high']:
            data_sub = all_sim.loc[all_sim.scenario_primary == sc, 'total_duration_days']
            kde = stats.gaussian_kde(data_sub)
            x_grid = np.linspace(0, np.percentile(data_sub, 99.5), 500)
            ax.plot(x_grid, kde(x_grid), color=colors[sc], linewidth=2, label=labels[sc])
            ax.fill_between(x_grid, kde(x_grid), color=colors[sc], alpha=0.15)

        ax.set_xlabel('Plazo Total de Adjudicación desde Cierre de Consultas (Días Calendario)')
        ax.set_ylabel('Densidad de Probabilidad')
        ax.set_title(f'Distribución de Plazos de Adjudicación según Escenario de Asimetría (N = {n_sim:,})')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(fontsize=9, loc='upper right')
        fig.tight_layout()
        fig1_path = fig_dir / '07_1_duration_distributions_by_scenario.png'
        fig.savefig(fig1_path, dpi=200)
        plt.close(fig)

        # Figure 2: Exceedance Risk Curves P(T > t)
        fig, ax = plt.subplots(figsize=(10, 5))
        for sc in ['low', 'medium', 'high']:
            data_sub = np.sort(all_sim.loc[all_sim.scenario_primary == sc, 'total_duration_days'].to_numpy())
            surv_y = 1.0 - np.arange(1, len(data_sub) + 1) / len(data_sub)
            ax.plot(data_sub, surv_y * 100, color=colors[sc], linewidth=2, label=labels[sc])

        ax.set_xlim(0, 150)
        ax.set_ylim(0, 105)
        ax.set_xlabel('Umbral de Días Calendario (t)')
        ax.set_ylabel('Probabilidad de Excedencia P(T > t) [%]')
        ax.set_title('Curvas de Riesgo Temporal: Probabilidad de Exceder Plazos de Adjudicación')
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(fontsize=9, loc='upper right')
        fig.tight_layout()
        fig2_path = fig_dir / '07_2_exceedance_risk_curves.png'
        fig.savefig(fig2_path, dpi=200)
        plt.close(fig)

        # Figure 3: Decomposition by Stages across Scenarios
        fig, ax = plt.subplots(figsize=(10, 5))
        stage_names = ['stage1_absolution_days', 'stage2_integration_days', 'stage3_post_integration_days']
        stage_labels = ['Absolución', 'Integración', 'Evaluación / Buena Pro']
        sc_labels = ['Baja Asimetría', 'Media Asimetría', 'Alta Asimetría']

        means = []
        for sc in ['low', 'medium', 'high']:
            sub = all_sim.loc[all_sim.scenario_primary == sc]
            means.append([sub[col].mean() for col in stage_names])
        means = np.array(means)  # shape (3, 3)

        bottom = np.zeros(3)
        palette = ['#2ca02c', '#9467bd', '#bcbd22']
        for i, (col, st_lbl) in enumerate(zip(stage_names, stage_labels)):
            ax.bar(sc_labels, means[:, i], bottom=bottom, label=st_lbl, color=palette[i], width=0.55, edgecolor='black', alpha=0.85)
            bottom += means[:, i]

        for idx, total_val in enumerate(bottom):
            ax.text(idx, total_val + 1.5, f'{total_val:.1f} d', ha='center', fontweight='bold', fontsize=9)

        ax.set_ylabel('Duración Media Acumulada (Días Calendario)')
        ax.set_title('Descomposición del Cronograma de Adjudicación por Etapas según Escenario')
        ax.grid(True, linestyle=':', alpha=0.5, axis='y')
        ax.legend(fontsize=9, loc='upper left')
        fig.tight_layout()
        fig3_path = fig_dir / '07_3_stage_decomposition.png'
        fig.savefig(fig3_path, dpi=200)
        plt.close(fig)

        log(f'Generated figure 1: {fig1_path}')
        log(f'Generated figure 2: {fig2_path}')
        log(f'Generated figure 3: {fig3_path}')
        log('DISCRETE EVENT SIMULATION COMPLETED SUCCESSFULLY.')

    except Exception as exc:
        log(f'PIPELINE FAILED: {type(exc).__name__}: {exc}')
        raise
    finally:
        logfile.write_text('\n'.join(LOG_LINES) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()