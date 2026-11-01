# Execution Logs and Computational Audit Trail

This directory stores the timestamped audit logs generated automatically during the execution of the computational pipeline.

Every Python script in the repository records runtime information, computational parameters, environment specifications, execution checkpoints, and mathematical diagnostics to ensure absolute auditability and scientific reproducibility.

---

## Directory Organization

Logs are structured into four subdirectories corresponding to the pipeline's analytical stages:

```text
03_logs/
│
├── 01_sample_and_data/          # Logs for Scripts 00, 01, 02, and 03
├── 02_statistical_analysis/     # Logs for Scripts 04 and 05
├── 03_stochastic_simulation/    # Logs for Scripts 06 and 07
└── 04_model_validation/         # Logs for Scripts 08 and 09
```

---

## Logged Information

Each execution log records:
1. **Timestamping:** Precise start, checkpoint, and completion times in UTC format.
2. **Software Environment:** Versions of Python, NumPy, SciPy, Pandas, and operating system details.
3. **Reproducibility Seeds:** Exact pseudo-random generator seeds (e.g., `SEED = 20251025`).
4. **Data Integrity:** Cryptographic SHA-256 fingerprints of all input datasets and generated output artifacts.
5. **Execution Metrics:** Convergence statistics, iteration counts, statistical test statistics (p-values, Levene, Welch t-test), and procedural status flags.

---

## Version Control Policy

Individual execution log files (*.log) are generated locally during pipeline runs and are excluded from Git tracking via .gitignore to avoid unnecessary repository bloat. This documentation file remains tracked to preserve the directory structure.
