# Computational Pipeline

This directory contains the Python scripts used to construct, analyze, model, validate, and synthesize the road-infrastructure procurement dataset used in this study.

The workflow is designed as a **sequential and auditable computational pipeline**. Each analytical stage produces structured outputs that are subsequently consumed or audited by later stages.

The pipeline covers:

- analytical sample construction;
- SEACE procedure-level data acquisition and processing;
- integration and quality control;
- statistical characterization;
- information-asymmetry scenario definition;
- stochastic model specification;
- Monte Carlo simulation;
- discrete-event simulation;
- temporal model validation;
- robustness and sensitivity analysis; and
- final scientific synthesis.

> **Reproducibility principle:** scripts should be executed in numerical order because later stages depend on analytical decisions and outputs established by earlier stages.

---

## Pipeline Architecture

```text
OFFICIAL OECE-SEACE DATA
        │
        ▼
Sample construction
        │
        ▼
Procedure-level SEACE evidence
        │
        ▼
Data processing and integration
        │
        ▼
Statistical analysis
        │
        ▼
Stochastic model specification
        │
        ├───────────────┐
        ▼               ▼
 Monte Carlo       Discrete-event
 simulation         simulation
        │               │
        └───────┬───────┘
                ▼
         Model validation
                │
                ▼
     Robustness / sensitivity
                │
                ▼
        Final synthesis
```

---

## Directory Structure

The scripts are organized by analytical stage.

```text
01_scripts/
│
├── 00_select_sample.py
│
├── ...
│
├── statistical_analysis/
│   ├── ...
│   ├── 07_...
│   ├── 08_...
│   ├── 09_...
│   ├── 10_...
│   └── 11_methodological_assessment.py
│
├── stochastic_modeling/
│   ├── 12_model_specification.py
│   ├── 13_monte_carlo_convergence.py
│   ├── 14_monte_carlo_simulation.py
│   ├── 15_discrete_event_assessment.py
│   └── 16_discrete_event_simulation.py
│
├── model_validation/
│   └── 17_model_validation.py
│
├── robustness_analysis/
│   └── 18_robustness_analysis.py
│
└── final_synthesis/
    └── 19_final_synthesis.py
```

The exact filenames of the early data-acquisition and processing scripts are retained in the repository itself. Their numerical prefixes define their execution order.

---

# Analytical Stages

## 00 — Sample Selection

### `00_select_sample.py`

Constructs the analytical population from the official OECE-SEACE procurement datasets for **2020–2025**.

The selection process links procurement notices and contract-award information using procedure/item identifiers and applies the study eligibility criteria.

The methodological funnel is:

| Stage | Unique procedures |
|---|---:|
| Analytical population | 336,106 |
| Contractual object = Works | 63,781 |
| Road infrastructure | 9,755 |
| Reference amount > PEN 25 million | 231 |
| Public Tender | 148 |
| After exclusions | 137 |
| Final analytical sample | **137** |

The resulting **137 unique procurement procedures** constitute the master analytical population used throughout the downstream pipeline.

Technical source and linkage audits are retained separately from the methodological funnel.

---

## 01–06 — Data Acquisition, Processing, Integration, and Quality Control

These scripts reconstruct the procedure-level analytical variables required by the study.

This stage combines the selected procurement sample with information retrieved from SEACE procedure records and constructs the temporal and information-asymmetry variables used downstream.

Among the core analytical variables are:

```text
queries_observations_count
total_award_time_days
query_stage_duration_days
evaluation_stage_duration_days
```

`queries_observations_count` is the primary empirical proxy for pre-award information asymmetry / informational friction.

`total_award_time_days` is the primary stochastic outcome.

The stage-level duration variables support the subsequent process-decomposition analysis.

The integrated analytical dataset preserves the master population of **137 procedures**. Missing temporal information is explicitly recorded rather than automatically imputed.

The resulting integrated dataset is the computational bridge between source reconstruction and formal statistical analysis.

---

## 07 — Scenario Definition

Defines **Low, Medium, and High** information-asymmetry scenarios from the observed consultation and observation counts.

Three alternative classification strategies are evaluated:

- terciles;
- P25/P75 thresholds; and
- a one-dimensional data-driven partition.

The pipeline establishes:

```text
Terciles        -> PRIMARY
P25/P75         -> ROBUSTNESS
Data-driven 1D  -> SENSITIVITY ONLY
```

The tercile classification is retained as the primary scenario structure because it provides balanced analytical groups and a reproducible ordered pattern in award-time behavior.

The primary scenario sample sizes with available award times are approximately balanced:

```text
Low       n = 46
Medium    n = 46
High      n = 44
```

---

## 08 — Scenario Robustness

Evaluates whether the Low–Medium–High structure is supported statistically and whether its interpretation depends strongly on the selected scenario thresholds.

The analysis includes:

- descriptive comparisons;
- Kruskal–Wallis tests;
- ordered-trend assessment;
- pairwise comparisons;
- effect-size estimation;
- bootstrap uncertainty;
- sample-size diagnostics; and
- alternative scenario definitions.

This stage provides the robustness evidence required before scenario-specific stochastic modeling.

---

## 09 — Distribution Fitting

Evaluates candidate probability distributions for scenario-specific award times.

Distributional assessment combines several complementary diagnostics rather than relying on a single goodness-of-fit statistic.

These include:

- log-likelihood;
- AIC;
- AICc;
- BIC;
- Kolmogorov–Smirnov diagnostics;
- Cramér–von Mises diagnostics;
- quantile errors;
- bootstrap goodness-of-fit assessment; and
- model-selection stability.

The resulting evidence supports Lognormal candidate representations for the Medium and High scenarios.

For the Low scenario, the parametric Lognormal representation is not accepted as the sole primary model.

---

## 10 — Distribution Diagnostics

Investigates distributional shape, concentration, upper-tail behavior, influential durations, and the specific limitations detected during probability-model fitting.

This stage prevents an apparently favorable information criterion from being interpreted as sufficient evidence of model adequacy.

The Low scenario receives particular attention because its empirical behavior is not adequately represented by the selected parametric model across all relevant diagnostics.

---

## 11 — Methodological Assessment

Closes the statistical-analysis phase and determines whether the evidence is sufficient to proceed to stochastic modeling.

The assessment confirms:

- master analytical population: **137 procedures**;
- available total award times: **136/137**;
- complete temporal decompositions: **109/137**;
- a positive association between consultation/observation volume and award time;
- stable scenario ordering under subsampling; and
- non-degenerate within-scenario stochastic variability.

For the primary continuous relationship:

```text
Pearson r      = 0.3457
Spearman rho   = 0.5453
Kendall tau    = 0.3717
```

This script distinguishes statistical evidence supporting stochastic representation from the separate question of which stochastic architecture should be implemented.

---

# Stochastic Modeling

## 12 — Model Specification

### `stochastic_modeling/12_model_specification.py`

Translates the statistical evidence into an explicit stochastic-model protocol **before final simulation**.

The model architecture specifies:

```text
Primary exposure:
queries_observations_count

Primary outcome:
total_award_time_days

Primary scenario definition:
Terciles
```

The scenario-specific probability protocol is:

```text
Low       -> empirical/nonparametric primary representation
Medium    -> Lognormal parametric candidate
High      -> Lognormal parametric candidate
```

A Low-scenario Lognormal model is retained only as a parametric sensitivity analysis.

This stage also prespecifies the quantities to be estimated and the numerical convergence experiment required before final Monte Carlo simulation.

---

## 13 — Monte Carlo Convergence Assessment

### `stochastic_modeling/13_monte_carlo_convergence.py`

Determines the simulation budget empirically rather than assuming that a predetermined number of iterations is sufficient.

The prespecified convergence grid is:

```text
100
500
1,000
2,500
5,000
10,000
25,000
50,000
100,000
```

A prospective extension rule is also available if the original grid fails because of genuine numerical non-convergence.

Convergence is evaluated across multiple deterministic seeds and multiple stochastic quantities, including:

- mean;
- median;
- standard deviation;
- P90;
- P95; and
- exceedance probability.

The analysis finds:

```text
Low Lognormal       25,000
Medium Lognormal    50,000
High Lognormal      50,000
```

The Low empirical representation exhibits finite-support behavior and is therefore evaluated using exact empirical functionals rather than forcing continuous-distribution convergence criteria onto a discrete empirical support.

The resulting common operational simulation budget is:

```text
50,000 iterations
```

This value is inherited by the final Monte Carlo simulation.

---

## 14 — Monte Carlo Simulation

### `stochastic_modeling/14_monte_carlo_simulation.py`

Performs the final scenario-based stochastic simulation using the model architecture and iteration budget authorized by the preceding scripts.

Primary representations:

```text
Low       Empirical
Medium    Lognormal
High      Lognormal
```

The Low Lognormal model is retained only for sensitivity analysis.

Primary simulated results include:

| Scenario | Representation | Mean | Median | SD | P90 | P95 |
|---|---|---:|---:|---:|---:|---:|
| Low | Empirical | 60.56 | 43.00 | 36.88 | 112.00 | 125.00 |
| Medium | Lognormal | 115.13 | 90.09 | 91.29 | 222.20 | 286.33 |
| High | Lognormal | 144.64 | 126.51 | 81.42 | 245.81 | 297.34 |

The simulation also estimates stochastic cross-scenario ordering probabilities.

These probabilities describe stochastic comparisons between modeled durations and are **not interpreted as causal probabilities**.

---

## 15 — Discrete-Event Simulation Assessment

### `stochastic_modeling/15_discrete_event_assessment.py`

Evaluates whether a stage-level process representation is scientifically defensible before implementing discrete-event simulation.

Complete temporal decompositions are available for:

```text
109 / 137 procedures
79.56%
```

For these observations:

```text
query-stage duration
+
evaluation-stage duration
=
total award time
```

with exact reconstruction for all complete cases.

The analysis also identifies statistically detectable dependence between the two temporal stages.

Consequently, independent stage sampling is not adopted as the primary process representation.

The final methodological decision is:

```text
DES_AUTHORIZED_WITH_CAUTION
```

---

## 16 — Two-Stage Discrete-Event Simulation

### `stochastic_modeling/16_discrete_event_simulation.py`

Implements the authorized two-stage stochastic process:

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

Observed stage-duration pairs are resampled jointly within each scenario to preserve their empirical dependence structure.

No unobserved queues, resource constraints, service disciplines, or administrative mechanisms are artificially introduced.

The simulation uses **50,000 entities per scenario** as a common operational simulation budget for comparability with the direct Monte Carlo analysis.

The resulting model is treated as a:

```text
SECONDARY PROCESS-DECOMPOSITION MODEL
```

while direct total-duration Monte Carlo remains the:

```text
PRIMARY STOCHASTIC REFERENCE
```

Independent stage sampling is retained only as a counterfactual sensitivity analysis.

---

# Model Validation

## 17 — Temporal Model Validation

### `model_validation/17_model_validation.py`

Evaluates whether the stochastic architecture can reproduce data outside the period used for calibration.

The temporal experiment is defined as:

```text
Training:
2020–2023

Holdout validation:
2024–2025
```

Training-only scenario thresholds are estimated without using validation-period outcomes.

The validation stage distinguishes:

```text
internal fidelity
≠
out-of-sample validation
```

and evaluates both the direct stochastic model and the two-stage DES.

Diagnostics include:

- empirical vs predicted medians;
- Kolmogorov–Smirnov statistics;
- Wasserstein distance;
- predictive interval coverage;
- temporal scenario ordering;
- continuous relationship transportability; and
- DES temporal behavior.

The positive continuous relationship remains observable in the holdout period:

```text
2024–2025 Spearman rho = 0.4706
```

Validation limitations are retained rather than being used to retrospectively modify previously selected models.

---

# Robustness and Sensitivity

## 18 — Robustness Analysis

### `robustness_analysis/18_robustness_analysis.py`

Stress-tests the principal scientific conclusions across reasonable analytical alternatives already established in the pipeline.

The analysis evaluates sensitivity to:

- time period;
- scenario-definition method;
- Low-scenario probability representation;
- direct Monte Carlo vs DES architecture;
- DES dependence assumptions; and
- temporal validation behavior.

The positive continuous relationship is observed in the full sample and in both temporal partitions:

| Period | n | Spearman rho |
|---|---:|---:|
| 2020–2025 | 136 | 0.5453 |
| 2020–2023 | 69 | 0.6530 |
| 2024–2025 | 67 | 0.4706 |

Scenario ordering is also reproduced under the primary and alternative scenario definitions.

At the same time, the pipeline explicitly identifies model-sensitive quantities, particularly:

- Low-scenario tail behavior;
- differences between direct Monte Carlo and stage-decomposed DES outputs; and
- DES sensitivity to the stage-dependence specification.

Robustness is therefore assessed **conclusion by conclusion**, rather than being reduced to a single omnibus score.

---

# Final Scientific Synthesis

## 19 — Final Synthesis

### `final_synthesis/19_final_synthesis.py`

Integrates the evidence generated throughout the computational pipeline.

This final stage does not re-fit models, change thresholds, select new distributions, or optimize previous analytical decisions.

Instead, it consolidates:

- sample-construction evidence;
- scenario-definition evidence;
- statistical relationships;
- stochastic-model results;
- Monte Carlo and DES outputs;
- temporal validation;
- robustness findings;
- limitations; and
- interpretation boundaries.

Its purpose is to provide a reproducible bridge between the computational pipeline and the final scientific reporting of the study.

---

# Model Hierarchy

The final analytical architecture should be interpreted hierarchically:

```text
LEVEL 1
Observed continuous relationship
queries/observations ↔ award time

        │
        ▼

LEVEL 2
Low / Medium / High scenario structure

        │
        ▼

LEVEL 3
Scenario-specific stochastic representations

        │
        ▼

LEVEL 4
Direct Monte Carlo simulation
PRIMARY STOCHASTIC MODEL

        │
        ├───────────────┐
        │               ▼
        │       Two-stage DES
        │       SECONDARY MODEL
        │
        └───────────────┘
                │
                ▼

LEVEL 5
Temporal validation

                │
                ▼

LEVEL 6
Robustness and sensitivity analysis

                │
                ▼

LEVEL 7
Final scientific synthesis
```

---

# Reproducibility Rules

The computational workflow follows several rules intended to prevent retrospective optimization of results.

### Analytical population

The master analytical population remains **n = 137**.

Individual analyses may use fewer observations when a required variable is unavailable, but this does not redefine the master sample.

### Missing data

Missing temporal values are documented.

They are not automatically imputed to manufacture complete observations.

### Scenario thresholds

Primary scenario thresholds are established before final stochastic simulation.

Alternative thresholds are used for robustness or sensitivity analysis rather than replacing the primary definition after observing favorable results.

### Probability distributions

Probability families are evaluated before final simulation.

Validation results are not used to retrospectively select a more favorable distribution.

### Simulation size

The operational Monte Carlo iteration count is determined through an explicit numerical convergence assessment.

Simulation iterations represent numerical draws from the fitted stochastic model; they do not increase the number of independent procurement procedures.

### Discrete-event simulation

The DES does not invent unobserved process mechanisms.

Its structure is limited to the temporal stages supported by the empirical dataset.

### Validation

Internal reproduction of the calibration data is not treated as independent validation.

Temporal validation is performed using a later holdout period.

### Causal interpretation

The study is observational.

The pipeline evaluates statistical relationships, stochastic behavior, predictive transportability, and robustness.

It does not identify a causal effect of consultation and observation volume on procurement duration.

---

# Running the Pipeline

Scripts should be executed from the repository root.

For example:

```bash
python 01_scripts/00_select_sample.py
```

Subsequent scripts should then be executed according to their numerical order and directory location.

Examples:

```bash
python 01_scripts/statistical_analysis/11_methodological_assessment.py

python 01_scripts/stochastic_modeling/12_model_specification.py

python 01_scripts/stochastic_modeling/13_monte_carlo_convergence.py

python 01_scripts/stochastic_modeling/14_monte_carlo_simulation.py

python 01_scripts/stochastic_modeling/15_discrete_event_assessment.py

python 01_scripts/stochastic_modeling/16_discrete_event_simulation.py

python 01_scripts/model_validation/17_model_validation.py

python 01_scripts/robustness_analysis/18_robustness_analysis.py

python 01_scripts/final_synthesis/19_final_synthesis.py
```

Earlier data-acquisition and processing scripts should likewise be executed according to their numerical prefixes.

---

# Outputs

Scripts write structured analytical products primarily to:

```text
02_results/
```

Execution logs are stored in:

```text
03_logs/
```

Source-document evidence used locally during procedure-level reconstruction is stored under:

```text
05_pdfs/
```

The PDF archive itself is not distributed through the repository.

For detailed descriptions of these repository components, see the corresponding documentation directories.

---

# Scientific Scope

This repository is intended to provide a transparent and reproducible computational implementation of the study.

The analytical results should be interpreted within the following boundaries:

- the master sample consists of 137 eligible road-infrastructure procurement procedures;
- consultation and observation volume is used as the study's empirical proxy for information asymmetry / informational friction;
- Monte Carlo simulation is the primary stochastic representation of total award duration;
- discrete-event simulation provides a secondary stage-level process decomposition;
- simulation draws do not constitute additional empirical procurement observations;
- validation evidence includes both successful and imperfect predictive behavior;
- robustness does not imply that every numerical quantity is invariant to modeling assumptions; and
- the observational design does not establish causality.

The repository therefore prioritizes **reproducibility, explicit analytical decisions, validation, and transparent reporting of model sensitivity** over retrospective optimization of results.
