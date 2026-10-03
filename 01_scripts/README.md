# Computational Pipeline

This directory contains the Python scripts used to construct, process, analyze, model, validate, stress-test, and synthesize the road-infrastructure procurement dataset used in this study.

The workflow is implemented as a **sequential and auditable computational pipeline**. Each analytical stage produces structured outputs that are subsequently consumed, validated, or audited by later stages.

The pipeline covers:

- analytical sample construction;
- SEACE procedure-level document acquisition;
- reconstruction of consultation and observation counts;
- integration and quality control;
- exploratory and missing-data analysis;
- continuous relationship diagnostics;
- information-asymmetry scenario definition;
- probability-distribution assessment;
- stochastic model specification;
- Monte Carlo convergence assessment and simulation;
- discrete-event model assessment and simulation;
- temporal out-of-sample validation;
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
Data reconstruction and integration
        │
        ▼
Exploratory and statistical analysis
        │
        ▼
Scenario definition and robustness
        │
        ▼
Distributional assessment
        │
        ▼
Stochastic model specification
        │
        ├────────────────────┐
        ▼                    ▼
   Monte Carlo         Discrete-event
   simulation            simulation
        │                    │
        └──────────┬─────────┘
                   ▼
           Temporal validation
                   │
                   ▼
        Robustness / sensitivity
                   │
                   ▼
           Final synthesis
```

---

# Directory Structure

The scripts are organized according to the sequential analytical workflow of the study. Numerical prefixes define the intended execution order across directories.

```text
01_scripts/
│
├── 00_select_sample.py
├── 01_download_pdfs.py
├── 02_count_queries.py
├── 03_integrate_results.py
│
├── statistical_analysis/
│   ├── 04_exploratory_analysis.py
│   ├── 05_missing_data_analysis.py
│   ├── 06_relationship_diagnostics.py
│   ├── 07_scenario_definition.py
│   ├── 08_scenario_robustness.py
│   ├── 09_distribution_fitting.py
│   ├── 10_distribution_diagnostics.py
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

The complete computational workflow therefore consists of **20 sequential scripts (00–19)**.

The directory structure separates major methodological phases for readability, while the numerical prefixes preserve a single reproducible execution sequence.

---

# Analytical Stages

## 00 — Sample Selection

### `00_select_sample.py`

Constructs the analytical population from the official OECE-SEACE procurement datasets for **2020–2025**.

The selection procedure links procurement notices and contract-award information using the corresponding procedure/item identifiers before applying the study eligibility criteria.

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

Technical source and linkage audits are retained separately from the methodological funnel so that source reconstruction can be audited without conflating record-level linkage with analytical sample selection.

---

# Data Acquisition and Integration

## 01 — Procedure-Document Acquisition

### `01_download_pdfs.py`

Retrieves the relevant procedure-level documents from the SEACE public procurement platform for the procurement procedures selected in Script 00.

These documents provide the source evidence required to reconstruct consultation and observation counts at the procedure level.

The local PDF archive is intentionally not distributed through the repository. Its role, reconstruction logic, and reproducibility procedure are documented separately in:

```text
05_pdfs/README.md
```

This design keeps the repository lightweight while preserving a documented route for reconstructing the underlying public-source evidence.

---

## 02 — Consultation and Observation Reconstruction

### `02_count_queries.py`

Processes the retrieved SEACE procedure documents and reconstructs the number of consultations and observations associated with each procurement procedure.

The workflow distinguishes between:

- procedures with documented consultations and observations;
- documented zero-count cases; and
- cases in which the relevant evidence cannot be reconstructed from the available document.

This distinction prevents a true value of zero from being automatically treated as missing information.

The resulting variable:

```text
queries_observations_count
```

constitutes the study's primary empirical proxy for **pre-award information asymmetry / informational friction**.

---

## 03 — Analytical Dataset Integration

### `03_integrate_results.py`

Integrates the selected procurement sample, reconstructed consultation/observation information, and temporal procurement information required for downstream analysis.

Core analytical variables include:

```text
queries_observations_count
total_award_time_days
query_stage_duration_days
evaluation_stage_duration_days
```

`queries_observations_count` is the primary empirical exposure used to characterize informational friction.

`total_award_time_days` is the primary stochastic outcome.

The stage-level duration variables support the subsequent process-decomposition analysis.

The resulting integrated dataset preserves the master analytical population of **137 procedures**. Missing temporal information is explicitly retained and documented rather than automatically imputed.

This integrated dataset constitutes the computational bridge between source reconstruction and formal statistical analysis.

---

# Statistical Analysis

## 04 — Exploratory Analysis

### `statistical_analysis/04_exploratory_analysis.py`

Performs the initial statistical characterization of the integrated analytical dataset.

This stage examines the empirical distributions, central tendency, dispersion, ranges, and other relevant characteristics of the variables subsequently used in inferential and stochastic analyses.

Its role is descriptive and diagnostic: it establishes the empirical structure of the data before scenario construction or stochastic-model specification.

---

## 05 — Missing-Data Analysis

### `statistical_analysis/05_missing_data_analysis.py`

Audits the availability and structure of the temporal information used throughout the study.

The analysis distinguishes the **master analytical population** from the subsets with complete information required for particular downstream analyses.

The pipeline preserves:

```text
Master analytical population       137
Available total award times        136
Complete stage decompositions      109
```

Missing temporal values are documented rather than automatically imputed.

The stage-level missingness assessment is particularly relevant to the later discrete-event model because complete temporal decomposition is available for **109 of the 137 procedures (79.56%)**.

The availability of stage-level temporal information is therefore explicitly carried forward as a methodological limitation.

---

## 06 — Relationship Diagnostics

### `statistical_analysis/06_relationship_diagnostics.py`

Evaluates the empirical relationship between consultation/observation volume and procurement award time before discretizing the exposure into Low, Medium, and High scenarios.

The continuous relationship is examined using complementary association measures rather than relying on a single correlation coefficient.

The full analytical evidence subsequently consolidated in the pipeline reports:

```text
Pearson r      = 0.3457
Spearman rho   = 0.5453
Kendall tau    = 0.3717
```

The observed relationship is positive.

This stage establishes the continuous empirical relationship underlying the subsequent scenario-based representation while maintaining the observational, non-causal interpretation of the study.

---

## 07 — Scenario Definition

### `statistical_analysis/07_scenario_definition.py`

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

The primary scenario sample sizes with available award times are:

```text
Low       n = 46
Medium    n = 46
High      n = 44
```

The scenario definition is subsequently retained throughout the primary full-sample stochastic analysis rather than being retrospectively changed to optimize later results.

---

## 08 — Scenario Robustness

### `statistical_analysis/08_scenario_robustness.py`

Evaluates whether the Low–Medium–High structure is statistically supported and whether its interpretation depends strongly on the selected scenario thresholds.

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

Alternative classifications are treated as robustness or sensitivity specifications rather than replacements for the primary tercile definition.

---

## 09 — Distribution Fitting

### `statistical_analysis/09_distribution_fitting.py`

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

The resulting evidence supports Lognormal candidate representations for the **Medium** and **High** scenarios.

For the **Low** scenario, the parametric Lognormal representation is not accepted as the sole primary model.

---

## 10 — Distribution Diagnostics

### `statistical_analysis/10_distribution_diagnostics.py`

Investigates distributional shape, concentration, upper-tail behavior, influential durations, and the specific limitations detected during probability-model fitting.

This stage prevents an apparently favorable information criterion from being interpreted as sufficient evidence of model adequacy.

The Low scenario receives particular attention because its empirical behavior is not adequately represented by the selected parametric model across all relevant diagnostics.

These findings motivate the later use of an empirical/nonparametric primary representation for the Low scenario.

---

## 11 — Methodological Assessment

### `statistical_analysis/11_methodological_assessment.py`

Closes the statistical-analysis phase and determines whether the accumulated empirical evidence is sufficient to proceed to stochastic modeling.

The assessment confirms:

- master analytical population: **137 procedures**;
- available total award times: **136/137**;
- complete temporal decompositions: **109/137**;
- a positive association between consultation/observation volume and award time;
- stable scenario behavior under the evaluated diagnostics; and
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

Translates the preceding statistical evidence into an explicit stochastic-model protocol **before final simulation**.

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
Low       -> Empirical/nonparametric primary representation
Medium    -> Lognormal parametric representation
High      -> Lognormal parametric representation
```

A Low-scenario Lognormal model is retained only as a parametric sensitivity analysis.

This stage also prespecifies the stochastic quantities to be estimated and the numerical convergence experiment required before final Monte Carlo simulation.

The purpose of this separation is to prevent final simulation results from retrospectively determining the model architecture.

---

## 13 — Monte Carlo Convergence Assessment

### `stochastic_modeling/13_monte_carlo_convergence.py`

Determines the operational Monte Carlo simulation budget empirically rather than assuming that a predetermined iteration count is numerically sufficient.

The convergence grid is:

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

Convergence is evaluated across multiple deterministic seeds and multiple stochastic quantities, including:

- mean;
- median;
- standard deviation;
- P90;
- P95; and
- exceedance probability.

The assessment identifies the following minimum sufficient iteration counts for the evaluated parametric representations:

```text
Low Lognormal       25,000
Medium Lognormal    50,000
High Lognormal      50,000
```

The Low empirical representation has finite empirical support and is therefore evaluated using its empirical functionals rather than forcing continuous-distribution convergence criteria onto the empirical distribution.

For consistency across the final stochastic experiment, the common operational simulation budget is established as:

```text
50,000 iterations per scenario
```

The final Monte Carlo model therefore uses a simulation budget determined from the numerical convergence analysis.

---

## 14 — Monte Carlo Simulation

### `stochastic_modeling/14_monte_carlo_simulation.py`

Performs the final scenario-based stochastic simulation using the model architecture and simulation budget established by the preceding stages.

Primary representations are:

```text
Low       Empirical
Medium    Lognormal
High      Lognormal
```

The Low Lognormal model is retained only for sensitivity analysis.

The final direct Monte Carlo simulation uses:

```text
50,000 iterations per scenario
```

Primary simulated results are:

| Scenario | Representation | Mean | Median | SD | P90 | P95 |
|---|---|---:|---:|---:|---:|---:|
| Low | Empirical | 60.56 | 43.00 | 36.88 | 112.00 | 125.00 |
| Medium | Lognormal | 115.13 | 90.09 | 91.29 | 222.20 | 286.33 |
| High | Lognormal | 144.64 | 126.51 | 81.42 | 245.81 | 297.34 |

The simulation also estimates stochastic cross-scenario ordering probabilities and other distributional quantities.

These probabilities describe stochastic comparisons between modeled durations and are **not interpreted as causal probabilities**.

The direct total-duration Monte Carlo model constitutes the study's **primary stochastic reference**.

---

## 15 — Discrete-Event Simulation Assessment

### `stochastic_modeling/15_discrete_event_assessment.py`

Evaluates whether a stage-level process representation is scientifically defensible and analytically additive before implementing discrete-event simulation.

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

with exact arithmetic reconstruction for all **109/109 complete cases**.

The stage-duration dependence assessment reports:

```text
Spearman rho = 0.2888
p            = 0.00232374
```

with a bootstrap 95% confidence interval of approximately:

```text
[0.1081, 0.4553]
```

Consequently, automatic independence between the two temporal stages is not supported.

The final methodological decision is:

```text
DES_AUTHORIZED_WITH_CAUTION
```

A two-stage process representation is therefore permitted, provided that empirical stage dependence and the stage-coverage limitation are preserved explicitly.

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

Each simulated tender is represented as an entity progressing through the ordered temporal stages.

Observed stage-duration pairs are resampled jointly within each scenario to preserve their empirical dependence structure.

No unobserved queues, resource constraints, service disciplines, or administrative mechanisms are artificially introduced.

The operational experiment uses:

```text
50,000 simulated entities per scenario
```

for consistency with the common stochastic simulation budget.

Primary DES results are:

| Scenario | Query median | Evaluation median | Total median | Total P95 |
|---|---:|---:|---:|---:|
| Low | 22.00 | 20.00 | 42.00 | 123.00 |
| Medium | 30.00 | 27.00 | 70.00 | 277.00 |
| High | 55.00 | 55.00 | 132.00 | 391.00 |

The empirical stage dependence is closely reproduced by the joint-resampling procedure.

The DES is treated as a:

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

Evaluates the temporal transportability of the stochastic architecture using a genuine later-period holdout rather than treating full-sample reproduction as independent validation.

The temporal experiment is:

```text
Training period:
2020–2023

Holdout validation period:
2024–2025
```

The corresponding sample sizes are:

```text
Training     n = 69
Validation   n = 68
```

Training-only scenario thresholds are estimated without using validation-period outcomes:

```text
Lower tercile threshold = 34.667
Upper tercile threshold = 120.333
```

The validation stage explicitly distinguishes:

```text
internal fidelity
≠
out-of-sample validation
```

and evaluates both the direct stochastic model and the two-stage DES.

Diagnostics include:

- empirical versus predicted medians;
- Kolmogorov–Smirnov statistics;
- Wasserstein distance;
- predictive interval coverage;
- temporal scenario ordering;
- continuous relationship transportability; and
- DES temporal behavior.

The positive continuous relationship remains observable in the holdout period:

```text
2024–2025
Spearman rho = 0.4706
p            = 5.85225e-05
```

The holdout scenario medians are:

```text
Low       50.00 days
Medium   122.50 days
High     122.50 days
```

Therefore, strict Low < Medium < High median ordering is **not reproduced in the temporal holdout**, although the overall holdout scenario comparison remains statistically differentiated:

```text
Kruskal-Wallis p = 0.00106511
```

This distinction is retained transparently rather than being used to retrospectively redefine the primary scenarios.

Validation limitations are similarly retained rather than being used to optimize previously selected probability representations.

---

# Robustness and Sensitivity

## 18 — Robustness Analysis

### `robustness_analysis/18_robustness_analysis.py`

Stress-tests the principal scientific conclusions across reasonable analytical alternatives already established in the pipeline.

The analysis evaluates sensitivity to:

- time period;
- scenario-definition method;
- Low-scenario probability representation;
- direct Monte Carlo versus DES architecture;
- DES dependence assumptions; and
- temporal validation behavior.

The positive continuous relationship is observed in the full sample and in both temporal partitions:

| Period | n | Pearson r | Spearman rho | Kendall tau |
|---|---:|---:|---:|---:|
| 2020–2025 | 136 | 0.3457 | 0.5453 | 0.3717 |
| 2020–2023 | 69 | 0.4798 | 0.6530 | 0.4686 |
| 2024–2025 | 67 | 0.3105 | 0.4706 | 0.3174 |

Scenario ordering is reproduced under the evaluated full-sample scenario definitions:

| Definition | Median Low | Median Medium | Median High |
|---|---:|---:|---:|
| Terciles | 43.50 | 83.50 | 126.00 |
| P25/P75 | 46.00 | 82.00 | 132.00 |
| Data-driven 1D | 55.50 | 123.50 | 134.50 |

However, agreement in individual scenario assignments varies across classification methods. Alternative definitions are therefore used to assess sensitivity rather than to redefine the primary tercile scenarios.

The Low-scenario representation also exhibits meaningful sensitivity in selected distributional quantities. For example, comparing the empirical primary representation with the Lognormal sensitivity representation gives:

```text
Median:
43.00 vs 53.44 days

P95:
125.00 vs 113.13 days

P99:
218.00 vs 154.30 days
```

Likewise, direct Monte Carlo and DES results are not numerically interchangeable, particularly for selected upper-tail quantities.

The conclusion-level robustness assessment therefore distinguishes:

```text
ROBUST
ROBUST_WITH_SENSITIVITY
SENSITIVE_TO_REPRESENTATION
MODEL_ARCHITECTURE_SENSITIVE
SENSITIVE_TO_DEPENDENCE_ASSUMPTION
ROBUST_DIRECTIONALLY
```

Robustness is evaluated **conclusion by conclusion**, rather than being reduced to a single omnibus score.

---

# Final Scientific Synthesis

## 19 — Final Synthesis

### `final_synthesis/19_final_synthesis.py`

Integrates the evidence generated throughout the complete computational pipeline.

This final stage does **not**:

- re-fit probability models;
- redefine scenario thresholds;
- select new probability distributions;
- alter validation results;
- remove unfavorable observations; or
- retrospectively optimize previous analytical decisions.

Instead, it consolidates:

- sample-construction evidence;
- data-reconstruction evidence;
- scenario-definition evidence;
- continuous statistical relationships;
- distributional assessment;
- stochastic-model results;
- Monte Carlo simulation;
- discrete-event simulation;
- temporal validation;
- robustness and sensitivity findings;
- methodological limitations; and
- interpretation boundaries.

Its purpose is to provide a reproducible bridge between the computational pipeline and the final scientific reporting of the study.

---

# Complete Execution Sequence

The complete computational sequence is:

```text
00  Sample selection
 │
01  SEACE PDF acquisition
 │
02  Consultation/observation reconstruction
 │
03  Analytical dataset integration
 │
04  Exploratory analysis
 │
05  Missing-data analysis
 │
06  Continuous relationship diagnostics
 │
07  Scenario definition
 │
08  Scenario robustness
 │
09  Probability-distribution fitting
 │
10  Distribution diagnostics
 │
11  Methodological assessment
 │
12  Stochastic model specification
 │
13  Monte Carlo convergence assessment
 │
14  Final Monte Carlo simulation
 │
15  Discrete-event simulation assessment
 │
16  Two-stage discrete-event simulation
 │
17  Temporal model validation
 │
18  Robustness and sensitivity analysis
 │
19  Final scientific synthesis
```

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
PRIMARY STOCHASTIC REFERENCE

        │
        ├──────────────────┐
        │                  ▼
        │          Two-stage DES
        │          SECONDARY PROCESS MODEL
        │
        └──────────────────┘
                 │
                 ▼

LEVEL 5
Temporal out-of-sample validation

                 │
                 ▼

LEVEL 6
Robustness and sensitivity analysis

                 │
                 ▼

LEVEL 7
Final scientific synthesis
```

This hierarchy is important because the different analytical layers answer different questions.

The observed procurement procedures remain the empirical evidence base. Scenario classification provides a structured representation of informational friction. Monte Carlo simulation characterizes scenario-specific stochastic award-time behavior, while the DES provides a secondary decomposition of the observed temporal process.

Neither simulation approach creates new empirical procurement observations.

---

# Reproducibility Rules

The computational workflow follows explicit rules intended to prevent retrospective optimization of results.

## Analytical population

The master analytical population remains:

```text
n = 137
```

Individual analyses may use fewer observations when a required variable is unavailable, but this does not redefine the master sample.

---

## Missing data

Missing temporal values are explicitly documented.

They are not automatically imputed to manufacture complete observations.

Consequently, different analytical components may have different effective sample sizes when they require different levels of temporal completeness.

---

## Scenario thresholds

Primary full-sample scenario thresholds are established before final stochastic simulation.

Alternative thresholds are used for robustness or sensitivity analysis rather than replacing the primary definition after observing favorable results.

Training-only thresholds used in temporal validation serve exclusively the out-of-sample validation experiment and do not replace the primary full-sample scenario classification.

---

## Probability distributions

Probability families are evaluated before final simulation.

The final architecture retains:

```text
Low       Empirical/nonparametric
Medium    Lognormal
High      Lognormal
```

Validation results are not used to retrospectively select a more favorable probability family.

---

## Simulation size

The operational Monte Carlo simulation budget is determined through an explicit numerical convergence assessment.

The resulting final budget is:

```text
50,000 iterations per scenario
```

Simulation iterations represent numerical draws from the stochastic model.

They do **not** increase the number of independent empirical procurement procedures.

---

## Discrete-event simulation

The DES does not invent unobserved process mechanisms.

Its structure is limited to the two temporal stages supported by the empirical dataset.

Observed stage-duration pairs are jointly resampled to preserve the dependence present in the empirical data.

Independent stage sampling is used only as a sensitivity counterfactual.

---

## Validation

Internal reproduction of calibration data is not treated as independent validation.

Temporal out-of-sample validation uses:

```text
Training     2020–2023
Holdout      2024–2025
```

Validation outcomes are reported even when they reveal imperfect predictive behavior.

They are not used to retrospectively optimize earlier analytical choices.

---

## Robustness

Robustness does not require every numerical estimate to remain invariant under alternative modeling assumptions.

Instead, the analysis distinguishes between conclusions that are directionally stable and quantities that are sensitive to:

- scenario definitions;
- probability representations;
- stochastic architecture;
- temporal period; or
- stage-dependence assumptions.

---

## Causal interpretation

The study is observational.

The pipeline evaluates:

- statistical association;
- stochastic behavior;
- scenario contrasts;
- predictive transportability; and
- robustness to alternative analytical specifications.

It does **not** identify a causal effect of consultation and observation volume on procurement duration.

---

# Running the Pipeline

Scripts should be executed from the repository root.

The complete execution sequence is:

```bash
python 01_scripts/00_select_sample.py
python 01_scripts/01_download_pdfs.py
python 01_scripts/02_count_queries.py
python 01_scripts/03_integrate_results.py

python 01_scripts/statistical_analysis/04_exploratory_analysis.py
python 01_scripts/statistical_analysis/05_missing_data_analysis.py
python 01_scripts/statistical_analysis/06_relationship_diagnostics.py
python 01_scripts/statistical_analysis/07_scenario_definition.py
python 01_scripts/statistical_analysis/08_scenario_robustness.py
python 01_scripts/statistical_analysis/09_distribution_fitting.py
python 01_scripts/statistical_analysis/10_distribution_diagnostics.py
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

The sequential order should be preserved because later stages consume or audit outputs and methodological decisions established earlier in the workflow.

---

# Outputs and Audit Trail

Structured analytical outputs are written primarily to:

```text
02_results/
```

Execution logs are stored under:

```text
03_logs/
```

Procedure-level source documents reconstructed locally from SEACE are stored under:

```text
05_pdfs/
```

The PDF archive itself is intentionally not distributed through the repository.

Likewise, raw OECE-SEACE source datasets required to reconstruct the initial sample are not duplicated in the repository. Their acquisition and expected local organization are documented in:

```text
00_data/README.md
```

The repository therefore separates:

```text
source reconstruction
        │
        ▼
computational scripts
        │
        ▼
structured analytical outputs
        │
        ▼
execution logs and audit evidence
```

This separation allows the analytical workflow to remain auditable without unnecessarily redistributing externally obtainable source material.

---

# Scientific Scope

This repository provides a transparent and reproducible computational implementation of the study.

The analytical results should be interpreted within the following boundaries:

- the master sample consists of **137 eligible road-infrastructure procurement procedures**;
- total award-time information is available for **136 of 137 procedures**;
- complete two-stage temporal decomposition is available for **109 of 137 procedures**;
- consultation and observation volume is used as the study's empirical proxy for pre-award information asymmetry / informational friction;
- Low, Medium, and High scenarios are primarily defined using terciles;
- the Low scenario uses an empirical/nonparametric primary stochastic representation;
- the Medium and High scenarios use Lognormal stochastic representations;
- the operational Monte Carlo simulation uses **50,000 iterations per scenario**, selected following numerical convergence assessment;
- direct total-duration Monte Carlo is the **primary stochastic reference**;
- discrete-event simulation provides a **secondary stage-level process decomposition**;
- DES stage dependence is preserved through joint empirical pair resampling;
- simulation draws do not constitute additional empirical procurement observations;
- temporal validation uses **2020–2023 for calibration and 2024–2025 as holdout data**;
- validation evidence includes both successful and imperfect predictive behavior;
- robustness does not imply that every numerical quantity is invariant to modeling assumptions; and
- the observational design does not establish causality.

The repository therefore prioritizes **reproducibility, traceability of analytical decisions, explicit model hierarchy, out-of-sample validation, sensitivity analysis, and transparent reporting of limitations** over retrospective optimization of results.
