# Model Validation and Hypothesis Testing

This directory contains the scripts dedicated to the statistical validation of the simulation model and the formal empirical testing of the research hypothesis.

These scripts fulfill **Specific Objective 4** of the thesis:
> *Validate the model by contrasting simulated procurement times against real historical records using the Kolmogorov-Smirnov (K-S) and Student's t tests at a significance level of α = 0.05, and test the dispersion hypothesis H1: σ_high > σ_low.*

---

## Workflow Overview

| Script | Title | Methodological Role |
|---|---|---|
| `08_model_validation.py` | Goodness-of-Fit & Hypothesis Testing | Contrasts simulated vs. real distributions (K-S, Welch t-test, Wasserstein distance) and tests H1 via Levene's test and Bootstrap 95% CI |
| `09_sensitivity_analysis.py` | Multi-Dimensional Robustness | Evaluates sensitivity to scenario cutpoints (P25/P75 vs. Tertiles), inter-stage copula dependence vs. independence, and yearly stability (2020–2025) |

---

## 1. Script 08 — Statistical Validation & Formal Hypothesis Testing

### Purpose
`08_model_validation.py` contrasts the 300,000 synthetic DES trajectories against the 2,004 historical empirical procedures and conducts the formal test of the central thesis hypothesis.

### Core Validation Batteries
1. **Calibration in Mean (Welch's t-test):** Tests whether the simulated timeline introduces systematic bias against real procurement records (Overall: Real Mean = 48.7 d, Sim Mean = 46.0 d; Welch p = 0.0073).
2. **Distributional Fidelity (Kolmogorov-Smirnov & Wasserstein Distance):**
   - Applies standard two-sample K-S and resampled Bootstrap K-S (subsampling n_real = 2,004 over 1,000 rounds) to control for sample-size hyper-sensitivity.
   - Measures the physical distance between empirical and simulated curves via the Earth Mover's Distance (Wasserstein Distance: 7.00 calendar days).
3. **Formal Hypothesis Contrast (H1: σ_high > σ_low):**
   - **Observed Empirical Standard Deviations:** σ_low = 33.66 days vs. σ_high = 58.15 days (Observed Ratio: 1.73).
   - **Levene Test (Brown-Forsythe with median center):** Statistic = 109.062, p-value = 1.48 × 10⁻²⁴.
   - **Bootstrap 95% Confidence Interval for Ratio (B = 5,000):** [1.27, 2.58], strictly greater than 1.0.
   - **Verdict:** Reject H0 in favor of H1 with overwhelming statistical significance (p < 0.001).

### Execution
From the repository root:
```bash
python 01_scripts/04_model_validation/08_model_validation.py
```

### Main Outputs (`02_results/04_model_validation/`)
- `08_1_statistical_validation_tests.xlsx`: Detailed test sheets for goodness-of-fit, hypothesis contrast, and quantile comparisons.
- `08_2_hypothesis_decision.json`: Machine-readable resolution confirming the formal acceptance of H1.
- `figures/08_1_qq_plots_real_vs_simulated.png`: Quantile-Quantile (Q-Q) alignment plots by scenario.
- `figures/08_2_hypothesis_dispersion_contrast.png`: Comparative boxplots illustrating the widening of dispersion between Low and High asymmetry.
- `figures/08_3_bootstrap_ratio_distribution.png`: Empirical density of the bootstrap variance ratio with 95% confidence intervals.

---

## 2. Script 09 — Sensitivity and Robustness Analysis

### Purpose
`09_sensitivity_analysis.py` stress-tests the scientific conclusions across three alternative analytical dimensions to guarantee that findings are not artifacts of specific modeling choices.

### Sensitivity Dimensions
1. **Scenario Cutpoint Invariance:**
   - Primary scheme (P25 - P75: Q < 7 vs. Q > 35): Ratio = 1.73, Levene p = 1.48 × 10⁻²⁴.
   - Tertiles scheme (Low Q ≤ 10 vs. High Q > 27): Ratio = 1.75, Levene p = 6.65 × 10⁻²⁷.
   - Confirms that the dispersion effect is completely invariant to the partitioning convention.
2. **Temporal Subgroup Stability (2020 to 2025):**
   - Evaluates the variance ratio separately for each of the six study years.
   - In all six individual years, σ_high exceeds σ_low (H1 direction maintained = True; ratios ranging from 1.32 to 3.38).
3. **Copula vs. Independence Benchmark:**
   - Contrasts the full multi-stage Gaussian copula model against an independent stage assumption (Mean: 61.49 d vs. 61.46 d; P90: 113.6 d vs. 113.8 d), validating that copula dependence captures residual correlation without distorting total durations.

### Execution
From the repository root:
```bash
python 01_scripts/04_model_validation/09_sensitivity_analysis.py
```

### Main Outputs (`02_results/04_model_validation/`)
- `09_1_sensitivity_metrics.xlsx`: Excel workbook documenting scenario comparisons, yearly stability tables, and copula sensitivity.
- `figures/09_1_sensitivity_comparison.png`: Dual publication plots displaying yearly dispersion ratios and scheme comparisons.
