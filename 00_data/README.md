# Input Data

This directory is reserved for the raw input datasets required to reproduce the sample-selection stage of the research.

The source data were obtained from the **OECE-SEACE Open Data Portal (Peru)** and correspond to public procurement records for the **2020–2025** study period.

> **Note:** The raw Excel files are not included in this repository because of their size and because they are publicly available from the official source.

## Data source

Two datasets were collected for each year from 2020 to 2025:

- **Procurement notice data** (`convocatoria`)
- **Contract award data** (`adjudicacion`)

This results in **12 source files**: six procurement-notice datasets and six contract-award datasets.

The files were downloaded manually from the OECE-SEACE Open Data Portal before execution of the computational pipeline.

## Manual data acquisition

### 1. Procurement notice data

Access the OECE-SEACE Open Data Portal and select **“Datos de la Convocatoria”** (Procurement Notice Data).

![Access to procurement notice data](../04_screenshots/01_open_data_portal_procurement_notices.png)

For each year from **2020 to 2025**, select **“Descargar todos los procesos”** (Download All Procedures).

![Download procurement notice data](../04_screenshots/02_download_procurement_notices.png)

Repeat the download for:

**2020 · 2021 · 2022 · 2023 · 2024 · 2025**

### 2. Contract award data

Return to the OECE-SEACE Open Data Portal and select **“Datos de la Adjudicación”** (Contract Award Data).

![Access to contract award data](../04_screenshots/03_open_data_portal_contract_awards.png)

For each year from **2020 to 2025**, select **“Descargar todos los procesos”** (Download All Procedures).

![Download contract award data](../04_screenshots/04_download_contract_awards.png)

Repeat the download for:

**2020 · 2021 · 2022 · 2023 · 2024 · 2025**

## Expected input files

After downloading the datasets, place the following 12 Excel files directly in this directory:

```text
00_data/
├── adjudicacion_2020.xlsx
├── adjudicacion_2021.xlsx
├── adjudicacion_2022.xlsx
├── adjudicacion_2023.xlsx
├── adjudicacion_2024.xlsx
├── adjudicacion_2025.xlsx
├── convocatoria_2020.xlsx
├── convocatoria_2021.xlsx
├── convocatoria_2022.xlsx
├── convocatoria_2023.xlsx
├── convocatoria_2024.xlsx
├── convocatoria_2025.xlsx
└── README.md
```

The original filenames must be preserved because the sample-selection script identifies the annual datasets programmatically using these names.

## Role in the computational pipeline

These files constitute the **raw data layer** of the research workflow:

```text
OECE-SEACE Open Data Portal
            │
            ▼
     12 raw Excel files
        (2020–2025)
            │
            ▼
   00_filtro_muestra.py
            │
            ▼
   Sample selection
            │
            ▼
 Subsequent processing,
 simulation and validation
```

The first script, `01_scripts/00_filtro_muestra.py`, reads the annual procurement-notice and contract-award datasets, integrates them, and applies the predefined sample-selection criteria used in the research.

No manual modification of the downloaded Excel files is required before running the script.

## Reproducibility

Manual intervention is limited to the initial acquisition of the publicly available source datasets. Once the 12 files have been placed in this directory, the subsequent stages of sample selection, data processing, simulation, and validation are performed through the Python scripts provided in this repository.

This structure separates:

1. **Primary data acquisition** from the official OECE-SEACE source.
2. **Computational processing** implemented through the reproducible research pipeline.

## Data availability

The original datasets are maintained by the **Organismo Especializado para las Contrataciones Públicas Eficientes (OECE)** through the SEACE Open Data Portal.

The 12 source files collectively occupy approximately **210 MB** and are therefore not duplicated in this repository.

To reproduce the analysis, users should obtain the corresponding datasets for 2020–2025 from the official source and place them in this directory using the filenames specified above.
