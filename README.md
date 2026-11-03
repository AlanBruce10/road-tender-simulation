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

### Key Empirical & Simulation Results
1. **Historical scenario sensitivity:** The high/low SD ratio is 1.728 for P25/P75 and 1.752 for tertiles. Whole-component bootstrap 95% intervals are [1.169, 2.653] and [1.280, 2.369], respectively. These contrasts are descriptive.
2. **Residual dependence pilot:** All 117 contrasts met their Monte Carlo precision tolerances. Under M1 high, the adjusted-minus-identity changes were +0.51151 days in SD and +1.00337 days in P95.
3. **Simulated DES Outcomes (N = 100,000 per scenario):**
   - **Low Asymmetry (Q < 7):** Mean = 30.45 d, Std (σ) = 17.60 d, 90th Percentile (P90) = 51.0 d.
   - **Medium Asymmetry (7 ≤ Q ≤ 35):** Mean = 45.25 d, Std (σ) = 30.32 d, 90th Percentile (P90) = 80.0 d.
   - **High Asymmetry (Q > 35):** Mean = 62.17 d, Std (σ) = 47.12 d, 90th Percentile (P90) = 115.0 d.
4. **Annual comparisons (2020–2025):** High-Q historical dispersion was larger in the five years with sufficient support. The 2023 contrast was withheld.


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
| 07 | `07_conditional_monte_carlo_simulation.py`| OE3 | Conditional Monte Carlo orchestrator reusing Script 06 with model/scenario-specific N |
| 08 | `08_model_validation.py` | OE4 | Separates internal phase-sum diagnostics, saved marginal grouped-CV evaluation and the absence of joint OOF validation |
| 09 | `09_sensitivity_analysis.py` | OE4 | Descriptive and structural sensitivity plus a paired residual dependence pilot |

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
python 01_scripts/03_stochastic_simulation/07_conditional_monte_carlo_simulation.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --initial-dir 02_results/reproducibility/script06_real_20261103T030931307613Z/02_results/03_stochastic_simulation --supplement-dir 02_results/reproducibility/script06_supplement_real_20261103T032752392276Z/02_results/03_stochastic_simulation --output-root 02_results/reproducibility/script07_new --models M1 M2 M4 --scenarios low medium high --seed 2026110307 --chunk-size 50000

# Validation & Robustness (OE4)
python 01_scripts/04_model_validation/08_model_validation.py --calibration-dir 02_results/reproducibility/script05_nested_20261102T054434700539Z_1eec8469/02_results/02_statistical_analysis --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --simulation-dir 02_results/reproducibility/script07_real_20261103T035847496236Z/02_results/03_stochastic_simulation --output-root 02_results/reproducibility/script08_new --bootstrap-reps 2000 --seed 2026110308
# Set the directory variables as described in the Script 09 contract.
python 01_scripts/04_model_validation/09_sensitivity_analysis.py --calibration-dir "$CALIBRATION_DIR" --bundle-dir "$BUNDLE_DIR" --simulation-dir "$SIMULATION_DIR" --validation-dir "$VALIDATION_DIR" --output-root "$STAGE1_ROOT" --bootstrap-reps 2000 --seed 2026110309
python 01_scripts/04_model_validation/09_sensitivity_analysis.py stage2 --bundle-dir "$BUNDLE_DIR" --output-root "$STAGE2_ROOT"
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
