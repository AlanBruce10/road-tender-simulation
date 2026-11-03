# Stochastic Simulation (Monte Carlo & Discrete Event Simulation)

This directory contains the computational simulation engines that model the award-time uncertainty of Peruvian road procurement procedures.

These scripts fulfill **Specific Objective 3** of the thesis:
> *Model stochastically the procurement duration for each information asymmetry scenario using Monte Carlo simulation and Discrete Event Simulation (DES) in Python.*

---

## Workflow Overview

| Script | Title | Methodological Role |
|---|---|---|
| `06_convergence_analysis.py` | Monte Carlo Convergence Assessment | Evaluates Monte Carlo precision across M1/M2/M4 and low/medium/high Q scenarios, supporting scenario-specific sizes from 50,000 to 2,000,000 iterations |
| `07_discrete_event_simulation.py` | Discrete Event Simulation Engine | Executes the multi-stage DES timeline generating 300,000 synthetic trajectories (100k per scenario) across primary and sensitivity schemes |

---

## 1. Script 06 — Monte Carlo Convergence Analysis

### Purpose
`06_convergence_analysis.py` evaluates numerical precision for conditional Monte Carlo simulation of published administrative schedule intervals. It provides an importable simulation core and scenario-specific iteration decisions for subsequent work in Script 07. It does not establish predictive validity or amend the officially approved thesis project.

### Key Methodological Features
- **Conditional architecture:** Three correlated intervals connect query close, absolution end, integration end and scheduled award end. Their sum is the simulated total. The sequence does not implement queues, resources or an independent DES engine.
- **Verified input:** Loads Script 05's `sixa-calibration-bundle/1.0`, its SHA-256 export manifest and linked 2,004 joint profiles. It consumes exported coefficients, transformations, institutional coding, variable ordering and model-specific Gaussian copulas. M2 is the reference, M1 the Q-only comparator and M4 the government/ln(procedure reference amount) alternative. No recalibration is performed.
- **Profile handling:** Empirical scenarios resample complete Q/government/nominal procedure-amount tuples using normalized subset weights. Primary boundaries are read from the bundle: low Q < 7, medium 7 <= Q <= 35, high Q > 35. FONAFE retains its special centered-contrast treatment. Empty conditional cells are rejected. Amount is a procedure reference amount, not an item amount or a monetary eligibility filter.
- **Temporal identity:** `T = D1 + D2 + D3`, without implicit rounding or minimum-day adjustments. The simulated sum and Script 05's independently calibrated TOTAL marginal are different distributions; they must not be substituted or forced to agree. Empirical validation of the sum belongs to Script 08.
- **Precision metrics:** Mean, sample standard deviation, P90, P95 and strict P(T > t) for t = 30, 45, 60, 75, 90, 120, 150 and 180 calendar days. Standard-deviation precision uses the fourth central moment; quantile intervals use order statistics/binomial ranks; exceedances use Wilson intervals, including nonzero uncertainty when no exceedance occurs.
- **Operational tolerances:** Pointwise 95% interval halfwidths must not exceed max(0.25 days, 0.5% of the mean), max(0.50 days, 1% of the standard deviation), max(0.50 days, 1% of P90), max(1 day, 2% of P95), and 0.005 probability units (0.5 percentage points) for each exceedance. These are numerical precision targets, not predictive-validity or engineering-equivalence criteria.
- **Acceptance:** At least 27 of 30 independent replicates must simultaneously meet all twelve metric tolerances. The smallest accepted evaluated N must also preserve acceptance at larger evaluated sizes and meet the implemented numerical-agreement check against those sizes. Agreement uses a Welch-style t margin between replicate averages; this is separate from single-run precision. Pointwise intervals and the 27/30 heuristic do not provide a simultaneous 95% coverage guarantee. If only the largest N qualifies, the absence of higher-size confirmation is explicit. Failure yields `PRECISION_NOT_REACHED`, without a forced recommendation.
- **Reproducible streams:** NumPy `SeedSequence` keys derive from the configuration identifier, N and replicate. Stream results do not depend on execution order. Initial and supplementary experiments use separate seeds and namespaces and never pool replicates.

### Protocols and Approved Results
The `initial` protocol evaluates M2/M1/M4 and all three Q scenarios at N = 1,000, 5,000, 10,000, 50,000 and 100,000, with 30 independent replicates per size, root seed `20251025` and 44,820,000 realizations. The original unchunked path remains the default for this protocol. The three low-Q mixtures qualified at 50,000; the other six returned `PRECISION_NOT_REACHED` through 100,000.

The prospective `supplement` protocol uses root seed `2026110306`, stream namespace `supplement_v1:`, 30 independent replicates at every size below, and 544,500,000 realizations. Every predefined size is evaluated even if a smaller one qualifies.

| Configuration | Supplementary N evaluated |
|---|---|
| M1 medium | 150,000; 250,000; 500,000 |
| M2 medium | 250,000; 500,000; 750,000 |
| M4 medium | 250,000; 500,000; 750,000 |
| M1 high | 500,000; 750,000; 1,000,000 |
| M2 high | 1,000,000; 2,000,000; 3,000,000 |
| M4 high | 1,000,000; 2,000,000; 3,000,000 |

The supplement processes blocks of 100,000, retaining every simulated total and calculating exact quantiles. It preserves random draw order; BLAS blocking may introduce floating-point roundoff. Tests verify close numerical equivalence without changing the statistical definitions. The controlled supplemental run completed in 706.24 seconds with a peak working set of 190.05 MiB.

| Model | Low Q | Medium Q | High Q |
|---|---:|---:|---:|
| M1 | 50,000 | 150,000 | 500,000 |
| M2 — reference | 50,000 | 500,000 | 2,000,000 |
| M4 | 50,000 | 250,000 | 2,000,000 |

These are the **smallest accepted sizes among those evaluated**, not exact mathematical minima. All recommendations have confirmation at larger evaluated sizes within their respective experiment. No common N has been certified across all nine configurations. The initial and supplementary artifacts remain independent evidence; original decisions, tolerances and replicas are preserved.

### Execution
From the repository root, use the existing approved local bundle and a fresh independent output root:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --output-root 02_results/reproducibility/script06_initial_new --protocol initial --seed 20251025
```

The supplementary protocol is reproduced separately:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --bundle-dir 02_results/reproducibility/script05_sixa_export_20261102_01/02_results/02_statistical_analysis --output-root 02_results/reproducibility/script06_supplement_new --protocol supplement --seed 2026110306 --chunk-size 100000
```

Both output directories must be fresh. Running these commands performs complete studies; synthetic tests are separate:

```bash
python 01_scripts/03_stochastic_simulation/06_convergence_analysis.py --self-test
```

The **26 automated tests** cover marginals, copulas, temporal sums, transformations, fixed profiles versus mixtures, deterministic streams, exact quantiles, chunk equivalence, original and supplementary plans, precision decisions, 27/30 boundaries, missing/duplicate metrics, corrupted contracts, hashes, publication failures and protected results. They include 23 loader-corruption variants and use isolated synthetic directories.

### Main Outputs (`02_results/03_stochastic_simulation/`)
Paths are relative to the chosen output root.

- `06_1_convergence_metrics.csv`: Twelve estimates, precision halfwidths, tolerances and metric flags for each configuration/N/replicate.
- `06_2_convergence_decision.json`: Protocol, plan, seed, stream namespace, block size, per-size acceptance/stability, recommended N or explicit nonacceptance, scope and dependency versions.
- `06_run_manifest.json`: Script/input fingerprints and SHA-256 values for the metrics and decisions. Publication verifies artifacts in a staging directory before renaming the complete directory; existing results are rejected.

Controlled local evidence is preserved under:

- Initial: `02_results/reproducibility/script06_real_20261103T030931307613Z/`.
- Supplement: `02_results/reproducibility/script06_supplement_real_20261103T032752392276Z/`.

Each contains the analytical outputs in `02_results/03_stochastic_simulation/` and execution logs, pre-execution integrity fingerprints and an execution-verification record at its root. The supplement additionally retains `flow_identifiers.json` for all 540 independent streams. These local evidence files are excluded from Git; publishing source and documentation does not publish data or results.

### Scope and Downstream Responsibilities
Precision applies only to the nine empirical model/scenario mixtures evaluated with fixed calibrated parameters. It is not a certificate for arbitrary fixed profiles, amount bands, sparsely represented government levels or future populations. In particular, national/FONAFE support limitations from Script 05 persist. Monte Carlo error, inherent interval variability, profile heterogeneity, parameter uncertainty and model-selection uncertainty are distinct.

Script 07 requires a separate audit and controlled adaptation to reuse the importable core and scenario-specific decisions; its existing implementation is not approved by this convergence study. Script 08 must assess empirical validity of the phase-sum distribution with appropriate dependence-aware validation. Script 09 handles substantive model/scenario sensitivities. No causal claim, verified actual-duration claim or independent DES capability follows from numerical convergence.

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
