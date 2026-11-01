# Stochastic Simulation of Information Asymmetry and Award-Time Uncertainty in Peruvian Road Infrastructure Tenders

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Reproducible Research](https://img.shields.io/badge/Reproducible-Research-brightgreen.svg)](#reproducibility)

## Overview

This repository contains the complete reproducible computational pipeline developed for the civil engineering thesis:

> **Simulación estocástica del efecto de la asimetría de información en la incertidumbre de los plazos de adjudicación en licitaciones de infraestructura vial peruana**  
> *Author:* Alan Bruce Hurtado Zavaleta  
> *Advisor:* Mg. Arq. José Franklin Gonzales Culqui  
> *Institution:* Universidad Nacional Toribio Rodríguez de Mendoza de Amazonas (UNTRM), Peru (2026)

The research analyzes public road-infrastructure procurement procedures registered in the Peruvian **OECE-SEACE Open Data Portal** during **2020–2025**. 

The computational workflow reconstructs the national tender population, audits procedural schedules, extracts and validates consultation and observation records (Q) from official administrative documents, models inter-stage duration distributions via location-scale parametric formulations and copula dependence, executes Discrete Event Simulations (DES) with Monte Carlo sampling, and formally tests the central hypothesis linking information asymmetry to award-time uncertainty.

The master analytical cohort comprises **2,004 eligible public road-infrastructure tenders** verified through a rigorous seven-gate quality control protocol.

---

## Central Research Hypothesis and Scientific Findings

### Hypothesis Contract
- **Alternative Hypothesis (H1):** Information asymmetry, measured by the volume of consultations and observations (Q), is positively associated with award-time uncertainty. Specifically, procurement procedures with Q above the 75th percentile (High Asymmetry) exhibit a significantly greater duration standard deviation (p < 0.05) than those below the 25th percentile (Low Asymmetry):
  $$\sigma_{\text{high}} > \sigma_{\text{low}}$$
- **Null Hypothesis (H0):** There is no significant difference in the standard deviation of procurement durations between High (Q > P75) and Low (Q < P25) asymmetry groups (p ≥ 0.05).

### Key Empirical & Simulation Results
1. **Hypothesis Formally Confirmed:** The Levene test (Brown-Forsythe) on historical empirical records yielded a test statistic of **109.062** with an overwhelming p-value of **1.48 × 10⁻²⁴**, formally rejecting H0 and confirming H1.
2. **Dispersion Multiplier:** The observed empirical standard deviation nearly doubles from **33.66 days** in Low Asymmetry to **58.15 days** in High Asymmetry (Observed Ratio: **1.73**; Bootstrap 95% Confidence Interval: **[1.27, 2.58]**, strictly greater than 1.0).
3. **Simulated DES Outcomes (N = 100,000 per scenario):**
   - **Low Asymmetry (Q < 7):** Mean = 30.45 d, Std (σ) = 17.60 d, 90th Percentile (P90) = 51.0 d.
   - **Medium Asymmetry (7 ≤ Q ≤ 35):** Mean = 45.25 d, Std (σ) = 30.32 d, 90th Percentile (P90) = 80.0 d.
   - **High Asymmetry (Q > 35):** Mean = 62.17 d, Std (σ) = 47.12 d, 90th Percentile (P90) = 115.0 d.
4. **Temporal Stability (2020–2025):** The variance expansion effect (σ_high > σ_low) holds true across every individual year of the six-year study period.
5. **Invariance to Partitioning:** The effect remains equally robust under a 3-part tertile classification (Levene p = 6.65 × 10⁻²⁷, Ratio: 1.75).

---

## Specific Objectives and Computational Pipeline

The computational pipeline consists of **10 sequentially numbered scripts (00–09)** organized into four modules matching the study's specific objectives:

```text
road-tender-simulation/
│
├── 00_data/                     # Source datasets from OECE-SEACE (2020–2025)
│   └── README.md
│
├── 01_scripts/                  # Executable computational pipeline (Scripts 00 to 09)
│   ├── 01_sample_and_data/          # Objective 1: Sample screening, SEACE scraping, and curation
│   ├── 02_statistical_analysis/     # Objective 2: EDA, continuous calibration, and scenarios
│   ├── 03_stochastic_simulation/    # Objective 3: MC convergence and Discrete Event Simulation
│   ├── 04_model_validation/         # Objective 4: Goodness-of-fit, hypothesis tests, and sensitivity
│   └── README.md
│
├── 02_results/                  # Structured analytical workbooks, models, and figures
│   ├── 01_sample_and_data/
│   ├── 02_statistical_analysis/
│   ├── 03_stochastic_simulation/
│   ├── 04_model_validation/
│   └── README.md
│
├── 03_logs/                     # Timestamped execution audit logs
│   └── README.md
│
├── 04_screenshots/              # Visual step-by-step documentation for manual SEACE downloads
│
├── 05_pdfs/                     # Official procurement documents (Pliegos & Actas)
│   └── README.md
│
├── .gitignore
├── LICENSE
└── README.md
```

### Detailed Script Mapping

| Step | Script | Specific Objective | Function |
|---|---|---|---|
| 00 | `00_select_sample.py` | OE1 | Links notice and award records; filters road-infrastructure public tenders |
| 01 | `01_download_pdfs.py` | OE1 | Scrapes SEACE fiches, audits schedules, and downloads Pliegos and Actas |
| 02 | `02_count_queries.py` | OE1 | Extracts auditable consultation and observation count (Q) from PDFs |
| 03 | `03_integrate_results.py` | OE1 | Enforces seven-gate quality control; builds master cohort (N = 2,004) |
| 04 | `04_exploratory_analysis.py` | OE2 | Non-parametric correlation, Shapiro-Wilk, and interval variance decomposition |
| 05 | `05_scenarios_and_calibration.py`| OE2 | Fits location-scale Lognormal, Hurdle model, copula, and defines P25/P75 |
| 06 | `06_convergence_analysis.py` | OE3 | MCSE stability audit proving N = 100,000 required for variance convergence |
| 07 | `07_discrete_event_simulation.py`| OE3 | Two-stage DES engine generating 300,000 synthetic runs across scenarios |
| 08 | `08_model_validation.py` | OE4 | Validates real vs. simulated fit (K-S, Welch t-test) and tests H1 (Levene test) |
| 09 | `09_sensitivity_analysis.py` | OE4 | Evaluates robustness across tertiles, copula dependence, and yearly cohorts |

---

## Core Analytical Architecture

### Information Asymmetry Proxy (Q)
The primary independent variable is the number of technical consultations and observations ($Q$) submitted by bidders during the pre-bid stage and answered by the tender committee in the official response document (*Pliego de Absolución*). Cases where no queries were submitted are formally confirmed as $Q = 0$ via official administrative acts (*Actas de no formulación*). The master cohort includes **110 verified Q = 0 tenders**.

### Modeled Time Horizon
The stochastic horizon spans from the closing of the query formulation stage to the contract award (*Otorgamiento de la Buena Pro*), partitioned into three consecutive, non-overlapping intervals:
$$T_{\text{total}} = T_1 \,(\text{Absolución}) + T_2 \,(\text{Integración}) + T_3 \,(\text{Evaluación / Buena Pro})$$

- **$T_1$:** Modeled via a conditional Lognormal distribution with location dependent on $Q$.
- **$T_2$:** Modeled as a two-part Hurdle distribution ($p_{\text{zero}} = 99.8\%$ duration is 0 days; empirical positive support).
- **$T_3$:** Modeled via a conditional Lognormal distribution with location and scale dependent on $Q$.
- **Dependence:** Coupled via a multivariate Gaussian copula fitted from empirical residual ranks using randomized Probability Integral Transforms (PIT).

---

## Reproduction Instructions

### 1. Environment Setup
Clone the repository and install dependencies in a Python 3.11+ environment:
```bash
git clone https://github.com/AlanBruce10/road-tender-simulation.git
cd road-tender-simulation

python -m pip install pandas numpy scipy openpyxl matplotlib playwright pymupdf
python -m playwright install chromium
```

### 2. Source Data Placement
Download the 12 annual OECE-SEACE Open Data Excel files (2020–2025) following the instructions in `00_data/README.md` and place them inside `00_data/`.

### 3. Pipeline Execution
Run the complete workflow sequentially from the repository root:
```bash
# Data Preparation (OE1)
python 01_scripts/01_sample_and_data/00_select_sample.py
python 01_scripts/01_sample_and_data/01_download_pdfs.py --all
python 01_scripts/01_sample_and_data/02_count_queries.py
python 01_scripts/01_sample_and_data/03_integrate_results.py

# Statistical Calibration (OE2)
python 01_scripts/02_statistical_analysis/04_exploratory_analysis.py
python 01_scripts/02_statistical_analysis/05_scenarios_and_calibration.py

# Stochastic Simulation (OE3)
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py
python 01_scripts/03_stochastic_simulation/07_discrete_event_simulation.py

# Validation & Robustness (OE4)
python 01_scripts/04_model_validation/08_model_validation.py
python 01_scripts/04_model_validation/09_sensitivity_analysis.py
```

All analytical outputs, summary tables, and high-resolution figures are automatically generated under `02_results/`.

---

## Methodological Boundaries and Interpretation

- **Observational Nature:** Statistical associations and simulation differences quantify empirical uncertainty and procedural friction; they are not interpreted as unconfounded causal treatments.
- **Published Schedules vs. Physical Events:** Process dates represent official published schedule milestones extracted from SEACE fiches (`date_nature = published_schedule_not_verified_actual_events`).
- **No Data Imputation:** Missing procedural dates or unresolvable document counts are tracked explicitly and excluded from downstream parametric modeling without synthetic imputation.

---

## Citation

If this repository or its findings are used in academic research, please cite:

> Hurtado Zavaleta, A. B. (2026). *Simulación estocástica del efecto de la asimetría de información en la incertidumbre de los plazos de adjudicación en licitaciones de infraestructura vial peruana* [Tesis de Grado, Universidad Nacional Toribio Rodríguez de Mendoza de Amazonas]. Repositorio Institucional UNTRM.

---

## Author & Advisor

- **Author:** Alan Bruce Hurtado Zavaleta (`@AlanBruce10`)  
  *Escuela Profesional de Ingeniería Civil, UNTRM, Chachapoyas, Perú*  
  Email: `4571604421@untrm.edu.pe`
- **Advisor:** Mg. Arq. José Franklin Gonzales Culqui  
  *Facultad de Ingeniería Civil y Arquitectura, UNTRM*  
  Email: `jose.gonzales@untrm.edu.pe`

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
