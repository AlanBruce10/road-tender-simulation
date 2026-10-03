# Stochastic Simulation of Information Asymmetry and Award-Time Uncertainty in Peruvian Road Infrastructure Tenders

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Reproducible Research](https://img.shields.io/badge/Reproducible-Research-brightgreen.svg)](#reproducibility)

## Overview

This repository contains the complete reproducible computational pipeline developed for the research project:

> **Stochastic Simulation of the Effect of Information Asymmetry on Award-Time Uncertainty in Peruvian Road Infrastructure Tenders**

The study examines public road-infrastructure procurement procedures registered in the **Peruvian OECE-SEACE public procurement system** during **2020–2025**.

The computational workflow reconstructs the study population from official open procurement data, retrieves procedure-level documentation, quantifies consultations and observations as an empirical proxy for pre-award information asymmetry / informational friction, constructs award-time variables, evaluates their statistical relationship, defines information-asymmetry scenarios, fits stochastic representations, performs Monte Carlo and discrete-event simulations, conducts temporal validation and robustness analyses, and consolidates the resulting scientific evidence.

The final selection yielded a **master analytical sample of 137 eligible public road-infrastructure tender procedures**.

---

## Research Objective

The general objective of the study is to develop a stochastic simulation model to evaluate the relationship between information asymmetry and the variability of award times in Peruvian public road-infrastructure procurement.

The study addresses four specific objectives:

1. **Identify** road-infrastructure tender procedures satisfying the predefined eligibility criteria during 2020–2025.
2. **Classify** procurement procedures into Low, Medium, and High information-asymmetry scenarios according to the volume of consultations and observations.
3. **Model stochastically** the award-time behavior of each scenario using Monte Carlo simulation and discrete-event simulation.
4. **Validate and assess the robustness** of the stochastic architecture using empirical, temporal, distributional, and sensitivity-based evidence.

The analysis is **observational**. Statistical associations and stochastic differences are therefore not interpreted as causal effects.

---

## Data Source

The study uses public procurement information from the **OECE-SEACE Open Data Portal (Peru)** for the period **2020–2025**.

Two complementary source families are used during sample reconstruction:

- procurement notices; and
- contract awards.

The source datasets are linked using procedure-item identifiers before applying the study eligibility criteria.

The raw annual source files are **not distributed in this repository**. They must be independently downloaded from the official public source.

Detailed source-data acquisition and reconstruction instructions are available in:

```text
00_data/README.md
```

---

## Study Population and Sample Selection

The reproducible selection protocol begins with the linked analytical procurement population and sequentially applies the predefined eligibility criteria.

| Selection stage | Unique procedures |
|---|---:|
| Analytical procurement population | 336,106 |
| Contractual object = Works | 63,781 |
| Road infrastructure | 9,755 |
| Reference amount > PEN 25 million | 231 |
| Public Tender | 148 |
| After exclusions | 137 |
| **Final analytical population** | **137** |

The resulting **137 unique procurement procedures** constitute the master analytical sample preserved throughout the downstream pipeline.

Technical source and linkage audits are retained separately from the methodological selection funnel.

---

## Core Analytical Variables

The computational pipeline reconstructs four variables central to the analysis:

```text
queries_observations_count
total_award_time_days
query_stage_duration_days
evaluation_stage_duration_days
```

### Information-asymmetry proxy

`queries_observations_count` represents the number of consultations and observations registered during the tender process.

It is used as the primary empirical proxy for **pre-award information asymmetry / informational friction**.

This variable should therefore be interpreted as an observable procurement-process proxy rather than as a direct measurement of latent information asymmetry.

### Primary stochastic outcome

`total_award_time_days` represents the elapsed award time reconstructed from the procurement timeline and constitutes the primary stochastic outcome.

Award-time information is available for **136 of the 137 procedures**.

### Stage-level temporal variables

The process-decomposition analysis additionally uses:

- `query_stage_duration_days`
- `evaluation_stage_duration_days`

Complete two-stage temporal decompositions are available for **109 of the 137 procedures (79.56%)**.

Missing temporal information is retained explicitly and is not automatically imputed.

---

## Repository Structure

```text
road-tender-simulation/
│
├── 00_data/
│   └── README.md
│
├── 01_scripts/
│   ├── statistical_analysis/
│   ├── stochastic_modeling/
│   ├── model_validation/
│   ├── robustness_analysis/
│   ├── final_synthesis/
│   ├── 00_select_sample.py
│   ├── 01_download_pdfs.py
│   ├── 02_count_queries.py
│   ├── 03_integrate_results.py
│   └── README.md
│
├── 02_results/
│   ├── statistical_analysis/
│   ├── stochastic_modeling/
│   ├── model_validation/
│   ├── robustness_analysis/
│   ├── final_synthesis/
│   ├── 00_1_sample_selection.xlsx
│   ├── 00_2_sample_selection_flow.xlsx
│   ├── 01_1_download_status.xlsx
│   ├── 02_1_query_counts.xlsx
│   ├── 02_2_processing_summary.xlsx
│   ├── 03_1_integrated_dataset.xlsx
│   └── README.md
│
├── 03_logs/
│
├── 04_screenshots/
│
├── 05_pdfs/
│   ├── .gitkeep
│   └── README.md
│
├── .gitignore
├── LICENSE
└── README.md
```

The repository separates source reconstruction, executable code, analytical outputs, execution logs, visual evidence, and locally reconstructed procedure documents.

Detailed script-level documentation is available in:

```text
01_scripts/README.md
```

Detailed analytical-output documentation is available in:

```text
02_results/README.md
```

---

## Computational Pipeline

The final workflow consists of **20 sequentially numbered scripts (00–19)**.

### Stage 1 — Sample Selection and Data Reconstruction

| Script | Purpose |
|---|---|
| `00_select_sample.py` | Reconstruct the eligible road-infrastructure procurement population |
| `01_download_pdfs.py` | Retrieve procedure-level SEACE documents |
| `02_count_queries.py` | Extract and count consultations and observations |
| `03_integrate_results.py` | Integrate procurement, temporal, and information-asymmetry variables |

These scripts produce the master analytical dataset containing the **137 eligible procedures**.

---

### Stage 2 — Statistical Analysis

| Script | Purpose |
|---|---|
| `04_exploratory_analysis.py` | Descriptive statistics, data-quality diagnostics, and initial association analysis |
| `05_missing_data_analysis.py` | Evaluate missing temporal information and potential systematic missingness |
| `06_relationship_diagnostics.py` | Assess continuous relationships between consultation/observation volume and award time |
| `07_scenario_definition.py` | Define the primary Low/Medium/High information-asymmetry scenarios |
| `08_scenario_robustness.py` | Evaluate alternative scenario definitions |
| `09_distribution_fitting.py` | Fit candidate probability distributions |
| `10_distribution_diagnostics.py` | Diagnose distributional adequacy and tail behavior |
| `11_methodological_assessment.py` | Consolidate methodological decisions before stochastic simulation |

This stage establishes the empirical and distributional architecture subsequently used by the stochastic models.

---

### Stage 3 — Stochastic Modeling

| Script | Purpose |
|---|---|
| `12_model_specification.py` | Specify the stochastic model architecture |
| `13_monte_carlo_convergence.py` | Evaluate Monte Carlo numerical convergence and simulation-size adequacy |
| `14_monte_carlo_simulation.py` | Run the final direct award-time Monte Carlo simulation |
| `15_discrete_event_assessment.py` | Assess whether stage-level discrete-event simulation is scientifically justified |
| `16_discrete_event_simulation.py` | Implement the two-stage discrete-event process model |

The final operational Monte Carlo simulation uses **50,000 iterations per scenario**, selected after numerical convergence assessment.

The same operational simulation budget is used for the two-stage discrete-event model for computational comparability, while its numerical behavior is audited separately.

---

### Stage 4 — Model Validation

| Script | Purpose |
|---|---|
| `17_model_validation.py` | Evaluate internal fidelity and temporal out-of-sample behavior |

Temporal validation separates:

```text
Training period:    2020–2023
Validation period:  2024–2025
```

Scenario thresholds used in the temporal validation experiment are estimated using the training period only, preventing validation-period outcomes from determining the classification thresholds.

The full-sample scenario structure remains the primary analytical specification.

---

### Stage 5 — Robustness and Sensitivity Analysis

| Script | Purpose |
|---|---|
| `18_robustness_analysis.py` | Stress-test the principal scientific conclusions across prespecified analytical alternatives |

Robustness is evaluated across multiple dimensions, including:

- continuous association across time periods;
- alternative scenario definitions;
- Low-scenario probability representation;
- Monte Carlo versus discrete-event architecture;
- stage-dependence specification; and
- temporal transportability.

Sensitivity analyses are not used to retrospectively optimize the primary model.

---

### Stage 6 — Final Scientific Synthesis

| Script | Purpose |
|---|---|
| `19_final_synthesis.py` | Integrate the final evidence architecture for scientific reporting |

Script 19 does not fit a new model or alter previous methodological decisions.

It consolidates:

- empirical relationships;
- scenario evidence;
- Monte Carlo results;
- discrete-event results;
- temporal validation;
- robustness and sensitivity;
- methodological limitations;
- objective-level evidence; and
- the final scientific interpretation boundaries.

The computational pipeline is therefore complete through final scientific synthesis.

---

## Primary Scenario Definition

The primary scenario specification uses the **tercile-based classification established in the statistical-analysis stage**.

Among the **136 procedures with available total award time**, the final primary analytical groups are:

| Scenario | N | Observed query/observation range | Observed award-time median | Observed P95 |
|---|---:|---:|---:|---:|
| Low | 46 | 0–30 | 43.50 days | 124.50 days |
| Medium | 46 | 33–106 | 83.50 days | 277.00 days |
| High | 44 | 109–403 | 126.00 days | 285.45 days |

The observed median ordering is:

```text
Low < Medium < High
```

Alternative definitions, including **P25/P75** and a **data-driven one-dimensional partition**, are retained as robustness or sensitivity specifications rather than replacements for the primary tercile classification.

---

## Continuous Empirical Relationship

Across the procedures with available total award time (`n = 136`), the relationship between consultation/observation volume and award time is positive:

| Statistic | Estimate | p-value |
|---|---:|---:|
| Pearson r | 0.3457 | 3.75 × 10⁻⁵ |
| Spearman ρ | 0.5453 | 6.67 × 10⁻¹² |
| Kendall τ | 0.3717 | 1.86 × 10⁻¹⁰ |

Because the variables exhibit non-normality and substantial distributional heterogeneity, the rank-based evidence is especially relevant to the final interpretation.

The observed association is statistically supported but is **not interpreted as causal**.

---

## Probability Representations

Distribution diagnostics resulted in scenario-specific stochastic representations.

The final primary representations are:

| Scenario | Primary representation |
|---|---|
| Low | Empirical / nonparametric |
| Medium | Lognormal |
| High | Lognormal |

The Low scenario retains an empirical representation because the parametric alternative does not reproduce all relevant distributional features adequately, particularly upper-tail behavior.

A Lognormal representation for Low is retained only as a sensitivity analysis.

---

## Monte Carlo Simulation

The **direct total-duration Monte Carlo model** is the primary stochastic simulation framework.

After numerical convergence assessment, the final operational simulation uses:

```text
50,000 iterations per scenario
```

Primary results are:

| Scenario | Representation | Simulated median | Simulated P95 |
|---|---|---:|---:|
| Low | Empirical | 43.00 days | 125.00 days |
| Medium | Lognormal | 90.09 days | 286.33 days |
| High | Lognormal | 126.51 days | 297.34 days |

Simulation iterations represent stochastic draws from the fitted or empirical representations. They **do not increase the number of independent procurement procedures in the empirical sample**.

---

## Discrete-Event Simulation

A secondary **two-stage discrete-event simulation (DES)** represents each tender as an entity progressing through the observed procurement stages:

```text
NOTICE
   │
   ▼
Query / integration stage
   │
   ▼
INTEGRATED TERMS
   │
   ▼
Evaluation / award stage
   │
   ▼
AWARD
```

The DES is based on the **109 procedures with complete stage-level temporal decomposition**.

No unobserved queues, artificial service disciplines, resource constraints, or administrative waiting mechanisms are introduced.

### Dependence preservation

The two observed temporal stages exhibit empirical dependence.

Accordingly, the primary DES preserves the observed dependence structure through **joint empirical resampling of stage-duration pairs within each scenario**.

Independent stage sampling is retained only as a counterfactual sensitivity analysis.

### DES results

| Scenario | Query-stage median | Evaluation-stage median | Total median | P95 |
|---|---:|---:|---:|---:|
| Low | 22.00 | 20.00 | 42.00 | 123.00 |
| Medium | 30.00 | 27.00 | 70.00 | 277.00 |
| High | 55.00 | 55.00 | 132.00 | 391.00 |

The DES is interpreted as a **secondary process-decomposition model**, whereas the direct total-duration Monte Carlo model remains the primary stochastic reference.

The two models are complementary representations rather than interchangeable estimators.

---

## Temporal Validation

The stochastic architecture was evaluated using a prespecified temporal split:

```text
Training period:          2020–2023 (n = 69)
Temporal holdout period:  2024–2025 (n = 68)
```

The continuous relationship remained positive in both periods:

| Period | N | Spearman ρ |
|---|---:|---:|
| 2020–2023 | 69 | 0.6530 |
| 2024–2025 | 67 | 0.4706 |

The positive association therefore persists in the temporal holdout period.

Scenario-specific predictive performance, however, is heterogeneous. The validation results are retained as evidence about model transportability rather than used to retrospectively modify the previously selected probability families or scenario definitions.

---

## Robustness and Sensitivity

The final robustness analysis distinguishes conclusions that are stable across analytical alternatives from those that depend materially on modeling choices.

The principal continuous relationship is directionally robust across:

- the complete 2020–2025 analytical period;
- the 2020–2023 training period; and
- the 2024–2025 temporal validation period.

The ordered Low–Medium–High award-time pattern also persists under multiple prespecified scenario-classification approaches.

At the same time, the analysis identifies meaningful sensitivity in:

- the stochastic representation of the Low scenario;
- direct Monte Carlo versus two-stage DES architecture; and
- the dependence specification used in stage-level simulation.

These sensitivities are reported explicitly rather than optimized away.

---

## Final Evidence Architecture

The completed pipeline establishes the following methodological hierarchy:

```text
1. Continuous empirical relationship
            │
            ▼
2. Low / Medium / High scenario structure
            │
            ▼
3. Scenario-specific probability representation
            │
            ▼
4. Direct Monte Carlo simulation
            │
            ▼
5. Two-stage discrete-event simulation
            │
            ▼
6. Temporal validation
            │
            ▼
7. Robustness and sensitivity analysis
            │
            ▼
8. Final scientific synthesis
```

The final model hierarchy retains:

- **Direct total-duration Monte Carlo** as the primary stochastic model;
- **Empirical/nonparametric representation** for Low;
- **Lognormal representation** for Medium;
- **Lognormal representation** for High; and
- **two-stage DES with joint pair resampling** as the secondary process-decomposition model.

---

## Main Scientific Findings

The completed computational pipeline supports the following principal findings:

1. The final analytical population comprises **137 eligible road-infrastructure public tender procedures** from the 2020–2025 selection protocol.

2. Consultation/observation volume exhibits a positive relationship with total award time, with **Spearman ρ = 0.5453** in the full analytical sample with available award-time information.

3. Observed award-time medians increase across the primary information-asymmetry scenarios from **43.50 days (Low)** to **83.50 days (Medium)** and **126.00 days (High)**.

4. The final direct Monte Carlo model uses **50,000 operational iterations per scenario** after numerical convergence assessment.

5. The primary probability representations are **empirical/nonparametric for Low** and **Lognormal for Medium and High**.

6. Primary Monte Carlo simulated medians are **43.00, 90.09, and 126.51 days** for Low, Medium, and High, respectively.

7. The secondary two-stage DES preserves empirical dependence between query/integration and evaluation/award durations through joint pair resampling.

8. The positive continuous relationship persists in the **2024–2025 temporal validation period**, although scenario-specific predictive performance is heterogeneous.

9. Robustness analysis supports the principal directional relationship while identifying meaningful sensitivity to the Low-scenario representation, stochastic-model architecture, and DES dependence assumptions.

These findings support an **associational interpretation** of the research hypothesis. They do not establish that consultation/observation volume causally determines procurement duration.

---

## Reproducibility

The repository is designed to preserve the computational provenance of the study from source-data reconstruction to final scientific synthesis.

The principal reproducibility layers are:

```text
00_data/          Source-data reconstruction instructions
01_scripts/       Executable computational pipeline
02_results/       Structured analytical outputs
03_logs/          Execution records
04_screenshots/   Visual workflow evidence
05_pdfs/          Local procedure-document reconstruction workspace
```

Raw OECE-SEACE datasets and downloaded procedure PDFs are intentionally not distributed in the repository.

Instead, the repository documents how these materials can be independently reconstructed from their original public sources.

Derived analytical workbooks, execution logs, methodological audits, and reproducibility metadata are retained to make the transformation from source information to final evidence traceable.

Random seeds and simulation metadata are recorded by the corresponding stochastic-modeling scripts where applicable.

---

## Requirements

The pipeline was developed in **Python**.

A Python 3.11+ environment is recommended.

Core packages used across the workflow include:

```text
pandas
numpy
scipy
openpyxl
matplotlib
statsmodels
scikit-learn
playwright
PyMuPDF
google-genai
```

Package requirements vary by pipeline stage.

For the browser-automation component, Playwright also requires a compatible browser installation:

```bash
playwright install chromium
```

Users reproducing the complete workflow should inspect the corresponding script and stage documentation before execution.

---

## Running the Pipeline

The scripts are designed to be executed from the repository root.

For example:

```bash
python 01_scripts/00_select_sample.py
python 01_scripts/01_download_pdfs.py
python 01_scripts/02_count_queries.py
python 01_scripts/03_integrate_results.py
```

Subsequent analytical stages are executed in numerical order from their corresponding subdirectories under `01_scripts/`.

The complete execution sequence and the purpose of every script are documented in:

```text
01_scripts/README.md
```

Because later scripts depend on outputs generated by earlier stages, the numerical execution order should be preserved when reproducing the complete analysis from source data.

---

## Procedure-Level PDF Reconstruction

Procedure documents retrieved from SEACE are used to reconstruct consultation and observation counts.

These PDFs are stored locally under:

```text
05_pdfs/
```

but are intentionally excluded from version control.

The repository instead provides a documented and reproducible workflow for obtaining the procedure-level evidence from the original public procurement platform.

See:

```text
05_pdfs/README.md
```

for the reconstruction protocol.

---

## Results and Audit Outputs

The `02_results/` directory contains the structured outputs generated throughout the computational pipeline, including:

- sample-selection audits;
- download-status records;
- consultation/observation counts;
- the integrated analytical dataset;
- descriptive and diagnostic statistics;
- missing-data analyses;
- scenario definitions and robustness analyses;
- distribution-fitting and diagnostic outputs;
- Monte Carlo convergence evidence;
- Monte Carlo simulation outputs;
- discrete-event assessment and simulation outputs;
- temporal model-validation evidence;
- robustness and sensitivity results; and
- the final scientific synthesis.

The final synthesis is stored in:

```text
02_results/final_synthesis/19_1_final_synthesis.xlsx
```

Detailed output documentation is available in:

```text
02_results/README.md
```

Execution records are stored separately under:

```text
03_logs/
```

This separation prevents analytical results from being conflated with runtime evidence.

---

## Scientific Scope and Interpretation

Several interpretation boundaries are intentionally preserved throughout the repository:

- the empirical study population remains **137 procedures**;
- simulation iterations do not create additional independent empirical observations;
- missing temporal values are not automatically imputed;
- the primary scenario thresholds are not redefined after observing simulation or validation results;
- probability families are not re-selected to improve validation performance;
- temporal validation outcomes are not used to retrospectively optimize the primary models;
- the DES does not introduce unobserved administrative mechanisms;
- robustness and sensitivity results are reported separately from primary results; and
- statistical association is not interpreted as causal identification.

These constraints are part of the analytical design and are retained throughout the final scientific synthesis.

---

## Research Status

The computational research pipeline is complete through:

```text
Sample selection
        ↓
Data reconstruction
        ↓
Statistical analysis
        ↓
Scenario definition
        ↓
Distribution diagnostics
        ↓
Stochastic-model specification
        ↓
Monte Carlo convergence
        ↓
Monte Carlo simulation
        ↓
Discrete-event assessment
        ↓
Discrete-event simulation
        ↓
Temporal model validation
        ↓
Robustness and sensitivity analysis
        ↓
Final scientific synthesis
```

The repository is therefore ready to support the **Results, Discussion, and scientific reporting phases** of the research.

---

## Citation

If this repository, its computational workflow, or its derived results are used in academic work, please cite the associated research:

> Hurtado Zavaleta, A. B. (2026). *Stochastic simulation of the effect of information asymmetry on award-time uncertainty in Peruvian road infrastructure tenders*. Universidad Nacional Toribio Rodríguez de Mendoza de Amazonas.

Citation metadata may be updated following publication of the corresponding scientific article.

---

## Author

**Alan Bruce Hurtado Zavaleta**  
Universidad Nacional Toribio Rodríguez de Mendoza de Amazonas (UNTRM)  
Peru

GitHub: `@AlanBruce10`

---

## License

This repository is distributed under the **MIT License**.

See:

```text
LICENSE
```

for the complete license terms.

---

## Repository Documentation

For detailed information about individual components of the project, see:

| Documentation | Purpose |
|---|---|
| `README.md` | Overall scientific and computational architecture |
| `00_data/README.md` | Reconstruction of OECE-SEACE source datasets |
| `01_scripts/README.md` | Complete executable pipeline and script sequence |
| `02_results/README.md` | Analytical outputs and result provenance |
| `05_pdfs/README.md` | Reconstruction of procedure-level SEACE documents |

Together, these five documentation layers describe the complete path from official public procurement records to the final reproducible scientific evidence.
