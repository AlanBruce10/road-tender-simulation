# Simulación estocástica del efecto de la asimetría de información en la incertidumbre de los plazos de adjudicación en licitaciones de infraestructura vial peruana

**Autor:** Br. Alan Bruce Hurtado Zavaleta  
**Asesor:** Mg. Arq. José Franklin Gonzales Culqui  
**Universidad:** Universidad Nacional Toribio Rodríguez de Mendoza de Amazonas (UNTRM)  
**Año:** 2026

---

## Descripción

Este repositorio contiene el código fuente del pipeline computacional desarrollado para la tesis de investigación.

El pipeline procesa los Datos Abiertos del OECE-SEACE (periodo 2020-2025) para:

1. Construir una muestra censal de 137 procesos de licitación pública de infraestructura vial.
2. Contar las consultas y observaciones formuladas por los postores.
3. Clasificar los procesos en tres escenarios de asimetría informativa (baja, media y alta).

El objetivo es modelar estocásticamente el efecto de la asimetría de información sobre la incertidumbre de los plazos de adjudicación, proporcionando una herramienta predictiva para las entidades públicas.

---

## Estructura del repositorio

```text
.
├── 01_scripts/
│   ├── 00_filtro_muestra.py
│   ├── 01_descargar_pdfs.py
│   ├── 02_contar_consultas.py
│   ├── 03_integrar_resultados.py
│   └── 04_calcular_escenarios.py
└── README.md
```

## Función de los scripts

| Script | Función | Entrada | Salida |
|---|---|---|---|
| `00_filtro_muestra.py` | Filtrado del universo | 12 archivos XLSX (2020-2025) | `BASE_FINAL_137_PROCESOS.xlsx` |
| `01_descargar_pdfs.py` | Descarga de PDFs | `BASE_FINAL_137_PROCESOS.xlsx` | 137 PDFs en carpeta local |
| `02_contar_consultas.py` | Conteo de consultas | 137 PDFs | `conteos_consultas.xlsx` |
| `03_integrar_resultados.py` | Integración de resultados | Base + conteos | `BASE_FINAL_CON_CONTEOS.xlsx` |
| `04_calcular_escenarios.py` | Clasificación en escenarios | `BASE_FINAL_CON_CONTEOS.xlsx` | Tablas y figuras |

---

## Requisitos

- Python 3.11.7 o superior
- `pandas`
- `numpy`
- `playwright`
- `pymupdf`
- `google-genai`
- `openpyxl`

### Instalación

```bash
pip install pandas numpy playwright pymupdf google-genai openpyxl
playwright install chromium
```

---

## Uso

Los scripts deben ejecutarse de forma secuencial:

```bash
python 01_scripts/00_filtro_muestra.py
python 01_scripts/01_descargar_pdfs.py
python 01_scripts/02_contar_consultas.py
python 01_scripts/03_integrar_resultados.py
python 01_scripts/04_calcular_escenarios.py
```

## Flujo de procesamiento

```text
12 archivos XLSX (2020-2025)
          │
          ▼
┌─────────────────────────────┐
│ Script 00                   │
│ Filtrado del universo       │
└──────────────┬──────────────┘
               │
               ▼
 BASE_FINAL_137_PROCESOS.xlsx
               │
               ▼
┌─────────────────────────────┐
│ Script 01                   │
│ Descarga de PDFs            │
└──────────────┬──────────────┘
               │
               ▼
           137 PDFs
               │
               ▼
┌─────────────────────────────┐
│ Script 02                   │
│ Conteo de consultas         │
└──────────────┬──────────────┘
               │
               ▼
     conteos_consultas.xlsx
               │
               ▼
┌─────────────────────────────┐
│ Script 03                   │
│ Integración de resultados   │
└──────────────┬──────────────┘
               │
               ▼
 BASE_FINAL_CON_CONTEOS.xlsx
               │
               ▼
┌─────────────────────────────┐
│ Script 04                   │
│ Clasificación en escenarios │
└──────────────┬──────────────┘
               │
               ▼
        Tablas y figuras
```

---

## Nota sobre la API Key de Gemini

El Script 02 (`02_contar_consultas.py`) utiliza Gemini como método de respaldo para el conteo de consultas en PDFs escaneados o ambiguos.

Para ejecutarlo, cada usuario debe obtener su propia API Key de Google AI Studio:

https://aistudio.google.com/app/apikey

Luego debe reemplazar en el script:

```python
API_KEY = "TU_API_KEY_DE_GEMINI"
```

por su propia clave:

```python
API_KEY = "su_clave_personal_aqui"
```

> **Importante:** Nunca se debe publicar una API Key real en GitHub.

El método principal del Script 02 es el procesamiento local con PyMuPDF, que no requiere API Key. Gemini se utiliza únicamente como mecanismo de respaldo para los casos en los que la extracción o interpretación local no permite determinar el número de consultas de manera confiable.

---

## Resultados principales

La aplicación del pipeline produjo los siguientes resultados:

- **Muestra final:** 137 procesos de licitación pública de infraestructura vial.
- **Percentil 25 (P25):** 23 consultas y observaciones.
- **Percentil 75 (P75):** 134 consultas y observaciones.

### Distribución por escenario de asimetría informativa

| Escenario | Número de procesos | Porcentaje |
|---|---:|---:|
| Baja asimetría | 36 | 26.3 % |
| Media asimetría | 67 | 48.9 % |
| Alta asimetría | 34 | 24.8 % |
| **Total** | **137** | **100.0 %** |

Los escenarios se establecen a partir de los percentiles P25 y P75 de la distribución del número de consultas y observaciones.

---

## Reproducibilidad

El pipeline fue diseñado para mantener la trazabilidad del procesamiento de los datos, desde los archivos originales de Datos Abiertos del OECE-SEACE hasta la generación de la base consolidada utilizada en el análisis estadístico y la simulación estocástica.

La ejecución secuencial de los scripts permite reproducir las principales etapas de:

1. Selección y filtrado de procedimientos.
2. Descarga de documentación.
3. Extracción y conteo de consultas y observaciones.
4. Integración de resultados.
5. Clasificación de los procedimientos según nivel de asimetría informativa.

---

## Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo `LICENSE` para más detalles.

---

## Contacto

**Autor:** Alan Bruce Hurtado Zavaleta  
**Correo:** 4571604421@untrm.edu.pe  
**GitHub:** [@AlanBruce10](https://github.com/AlanBruce10)
