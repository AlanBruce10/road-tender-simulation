# Computational Pipeline Scripts

This directory contains the complete executable Python workflow developed for the road procurement stochastic simulation research.

The pipeline comprises **10 sequentially numbered scripts (00–09)** organized into four methodological modules aligned with the study's specific objectives:

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
