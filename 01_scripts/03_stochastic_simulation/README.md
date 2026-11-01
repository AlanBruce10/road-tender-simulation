# Stochastic Simulation (Monte Carlo & Discrete Event Simulation)

This directory contains the computational simulation engines that model the award-time uncertainty of Peruvian road procurement procedures.

These scripts fulfill **Specific Objective 3** of the thesis:
> *Model stochastically the procurement duration for each information asymmetry scenario using Monte Carlo simulation and Discrete Event Simulation (DES) in Python.*

---

## Workflow Overview

| Script | Title | Methodological Role |
|---|---|---|
| `06_convergence_analysis.py` | Monte Carlo Convergence Assessment | Evaluates numerical stability across N from 1,000 to 100,000; proves why N = 10,000 is insufficient for variance and validates N = 100,000 |
| `07_discrete_event_simulation.py` | Discrete Event Simulation Engine | Executes the multi-stage DES timeline generating 300,000 synthetic trajectories (100k per scenario) across primary and sensitivity schemes |

---

## 1. Script 06 — Monte Carlo Convergence Analysis

### Purpose
Before running the definitive simulations, `06_convergence_analysis.py` performs a formal stability audit to mathematically determine the minimum sample size required so that Monte Carlo sampling error does not distort the second statistical moment (the standard deviation, σ).

### Key Methodological Findings
- **Sample Sizes Evaluated:** N in [1,000, 2,500, 5,000, 10,000, 15,000, 20,000, 25,000, 30,000, 40,000, 50,000, 75,000, 100,000].
- **Error Metric:** Tracks the Monte Carlo Standard Error of the standard deviation: MCSE(σ) ≈ σ / √(2·N).
- **Justification for N = 100,000:**
  - In the Low Asymmetry scenario, σ stabilizes at N = 40,000 (MCSE = 0.055 d).
  - In the Medium Asymmetry scenario, σ stabilizes at N = 30,000 (MCSE = 0.097 d).
  - In the High Asymmetry scenario (heavy upper tail of controversies), at N = 10,000 the MCSE is 0.336 d, exceeding the tolerance threshold. It reaches strict numerical stability only at N = 100,000 (MCSE = 0.150 d).
- **Decision:** Adopts **N = 100,000 iterations per scenario** as the unified operational sample size.

### Execution
From the repository root:
```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py
```

### Main Outputs (`02_results/03_stochastic_simulation/`)
- `06_1_convergence_metrics.xlsx`: Running cumulative means, standard deviations, MCSEs, and relative changes.
- `06_2_convergence_decision.json`: Machine-readable contract establishing N = 100,000 for Script 07.
- `figures/06_1_convergence_trajectory.png`: Stabilization trajectories of σ and MCSE as a function of N.

---

## 2. Script 07 — Discrete Event Simulation (DES) Engine

### Purpose
`07_discrete_event_simulation.py` models the procurement process as an administrative queuing sequence of discrete stochastic events, preserving multivariate stage correlations via the fitted Gaussian copula.

### Process Flow Representation
The model advances through four discrete milestones:
1. **Event 0 (t = 0):** Closing of query formulation period.
2. **Event 1 (t₁ = t₀ + Δt₁):** Publication of response document (Absolución de Consultas).
3. **Event 2 (t₂ = t₁ + Δt₂):** Integration of final tender terms (Integración de Bases).
4. **Event 3 (t₃ = t₂ + Δt₃):** Award of the contract (Otorgamiento de la Buena Pro).
Total duration: T_total = t₃ − t₀ = Δt₁ + Δt₂ + Δt₃.

### Simulation Specifications
- **Total Synthesized Iterations:** 300,000 runs (100,000 for Low, 100,000 for Medium, 100,000 for High).
- **Parallel Sensitivity Run:** Simultaneously evaluates the tertile partition scheme under the same random seed (20251025).
- **Discretization:** Continuous synthetic values are mapped to integer calendar days matching public procurement administration practice.
- **Risk Metrics:** Calculates quantiles (P10, P25, P50, P75, P90, P95, P99) and exceedance probabilities P(T > 30, 45, 60, 75, 90, 120, 150, 180 days).

### Execution
From the repository root:
```bash
python 01_scripts/03_stochastic_simulation/07_discrete_event_simulation.py
```

### Main Outputs (`02_results/03_stochastic_simulation/`)
- `07_1_simulated_trajectories.csv.gz`: Compressed master archive containing all 300,000 simulated stage and total durations.
- `07_2_simulation_summary.xlsx`: Statistical metrics and exceedance risk tables.
- `figures/07_1_duration_distributions_by_scenario.png`: Comparative probability density functions (KDE).
- `figures/07_2_exceedance_risk_curves.png`: Empirical survival curves P(T > t).
- `figures/07_3_stage_decomposition.png`: Cumulative bar charts showing stage-by-stage bottleneck contributions.
