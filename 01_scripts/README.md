# Computational Pipeline Scripts

This directory contains the complete executable Python workflow developed for the road procurement stochastic simulation research.

The pipeline comprises **10 sequentially numbered scripts (00–09)** organized into four methodological modules directly aligned with the study's specific objectives:

```text
01_scripts/
│
├── 01_sample_and_data/          # Objective 1: Sample screening, SEACE acquisition, and data curation
│   ├── 00_select_sample.py
│   ├── 01_download_pdfs.py
│   ├── 02_count_queries.py
│   └── 03_integrate_results.py
│
├── 02_statistical_analysis/     # Objective 2: Exploratory data analysis, calibration, and scenario definition
│   ├── 04_exploratory_analysis.py
│   └── 05_scenarios_and_calibration.py
│
├── 03_stochastic_simulation/    # Objective 3: Monte Carlo convergence and Discrete Event Simulation (DES)
│   ├── 06_convergence_analysis.py
│   └── 07_discrete_event_simulation.py
│
└── 04_model_validation/         # Objective 4: Goodness-of-fit, hypothesis testing, and sensitivity analysis
    ├── 08_model_validation.py
    └── 09_sensitivity_analysis.py
```

---

## Execution Sequence

All scripts are self-contained, reproducible, and designed to be executed from the **repository root**:

```bash
# Phase 1: Data Preparation & Curation (Specific Objective 1)
python 01_scripts/01_sample_and_data/00_select_sample.py
python 01_scripts/01_sample_and_data/01_download_pdfs.py --all
python 01_scripts/01_sample_and_data/02_count_queries.py
python 01_scripts/01_sample_and_data/03_integrate_results.py

# Phase 2: Statistical Modeling & Calibration (Specific Objective 2)
python 01_scripts/02_statistical_analysis/04_exploratory_analysis.py
python 01_scripts/02_statistical_analysis/05_scenarios_and_calibration.py

# Phase 3: Stochastic Simulation (Specific Objective 3)
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py
python 01_scripts/03_stochastic_simulation/07_discrete_event_simulation.py

# Phase 4: Model Validation & Robustness (Specific Objective 4)
python 01_scripts/04_model_validation/08_model_validation.py
python 01_scripts/04_model_validation/09_sensitivity_analysis.py
```

---

## Script Architecture Overview

| Script | Module | Description | Primary Output |
|---|---|---|---|
| `00_select_sample.py` | 01 | Multi-year record linkage (2020–2025) and road-scope screening | `00_1_sample_selection.xlsx` |
| `01_download_pdfs.py` | 01 | Automated SEACE scraper and schedule extraction | `01_1_acquisition_status.xlsx`, `05_pdfs/` |
| `02_count_queries.py` | 01 | Structural parsing of consultation/observation count (Q) | `02_1_query_counts.xlsx` |
| `03_integrate_results.py` | 01 | Quality control, identity checks, and master eligible dataset | `03_2_model_ready_dataset.xlsx` (N = 2,004) |
| `04_exploratory_analysis.py` | 02 | Non-parametric correlations and dispersion diagnostics | `04_1_descriptive_statistics.xlsx` |
| `05_scenarios_and_calibration.py` | 02 | Conditional Lognormal fitting, Hurdle model, and copula | `05_3_model_parameters.json` |
| `06_convergence_analysis.py` | 03 | Monte Carlo stability assessment validating N = 100,000 | `06_2_convergence_decision.json` |
| `07_discrete_event_simulation.py` | 03 | Two-stage DES engine generating 300,000 synthetic runs | `07_2_simulation_summary.xlsx` |
| `08_model_validation.py` | 04 | K-S, Welch t-test, Levene test (p = 1.48 × 10⁻²⁴), and Bootstrap CI | `08_2_hypothesis_decision.json` |
| `09_sensitivity_analysis.py` | 04 | Robustness across tertiles, copula vs. independence, and years | `09_1_sensitivity_metrics.xlsx` |
