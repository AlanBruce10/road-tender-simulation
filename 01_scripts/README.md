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
│   └── 07_conditional_monte_carlo_simulation.py
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
python 01_scripts/03_stochastic_simulation/07_conditional_monte_carlo_simulation.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --initial-dir 02_results/reproducibility/script06_real_20261103T030931307613Z/02_results/03_stochastic_simulation --supplement-dir 02_results/reproducibility/script06_supplement_real_20261103T032752392276Z/02_results/03_stochastic_simulation --output-root 02_results/reproducibility/script07_new --models M1 M2 M4 --scenarios low medium high --seed 2026110307 --chunk-size 50000

# Phase 4: Model Validation & Robustness (Specific Objective 4)
python 01_scripts/04_model_validation/08_model_validation.py --calibration-dir 02_results/reproducibility/script05_nested_20261102T054434700539Z_1eec8469/02_results/02_statistical_analysis --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --simulation-dir 02_results/reproducibility/script07_real_20261103T035847496236Z/02_results/03_stochastic_simulation --output-root 02_results/reproducibility/script08_new --bootstrap-reps 2000 --seed 2026110308
# Set the directory variables as described in the Script 09 contract.
python 01_scripts/04_model_validation/09_sensitivity_analysis.py --calibration-dir "$CALIBRATION_DIR" --bundle-dir "$BUNDLE_DIR" --simulation-dir "$SIMULATION_DIR" --validation-dir "$VALIDATION_DIR" --output-root "$STAGE1_ROOT" --bootstrap-reps 2000 --seed 2026110309
python 01_scripts/04_model_validation/09_sensitivity_analysis.py stage2 --bundle-dir "$BUNDLE_DIR" --output-root "$STAGE2_ROOT"
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
| `07_conditional_monte_carlo_simulation.py` | 03 | Conditional Monte Carlo orchestrator reusing Script 06 | `07_2_simulation_summary.json` |
| `08_model_validation.py` | 04 | Internal phase-sum diagnostics, saved marginal OOF evaluation and methodological limits; no joint OOF phase-sum validation | `08_A_internal_diagnostics.json`, `08_B_oof_marginal_evaluation.json`, `08_C_methodological_limits.json` |
| `09_sensitivity_analysis.py` | 04 | Descriptive and structural sensitivity plus a paired residual dependence pilot | Stage 1 JSON/CSV and manifest; Stage 2 replicate, precision and manifest JSON |
