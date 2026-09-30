import pandas as pd
import numpy as np
from pathlib import Path

RAW_DATA = Path(r"D:\00_THESIS_ALAN_BRUCE\Raw_Data_SEACE")
RESULTADOS = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\03_resultados")
RESULTADOS.mkdir(parents=True, exist_ok=True)

EXCEL_BASE = RESULTADOS / "BASE_FINAL_137_PROCESOS.xlsx"
EXCEL_EMBUDO = RESULTADOS / "flujo_seleccion_muestra.xlsx"

def log(mensaje):
    print(mensaje)

embudo = []

def agregar_etapa(nombre, cantidad):
    embudo.append({"etapa": nombre, "cantidad": int(cantidad)})
    log(f"  -> {nombre}: {cantidad:,}")

def main():
    log("=" * 70)
    log(" GENERACION DE LA MUESTRA - TESIS ALAN BRUCE")
    log("=" * 70)

    log("\n[1] Leyendo archivos del SEACE 2020-2025...")

    conv = pd.DataFrame()
    adj = pd.DataFrame()

    for year in range(2020, 2026):
        try:
            c = pd.read_excel(RAW_DATA / f"convocatoria_{year}.xlsx")
            a = pd.read_excel(RAW_DATA / f"adjudicacion_{year}.xlsx")
            conv = pd.concat([conv, c], ignore_index=True)
            adj = pd.concat([adj, a], ignore_index=True)
            log(f"  {year}: convocatorias={len(c):,}, adjudicaciones={len(a):,}")
        except Exception as e:
            log(f"  {year}: ERROR - {e}")

    log(f"\n  TOTAL CONVOCATORIAS: {len(conv):,}")
    log(f"  TOTAL ADJUDICACIONES: {len(adj):,}")

    agregar_etapa("Universo inicial - Convocatorias 2020-2025", len(conv))
    agregar_etapa("Universo inicial - Adjudicaciones 2020-2025", len(adj))

    log("\n[2] Haciendo MERGE por codigoconvocatoria + n_item...")
    merged = pd.merge(
        conv, adj,
        on=['codigoconvocatoria', 'n_item'],
        how='inner',
        suffixes=('_conv', '_adj')
    )
    log(f"  Resultado: {len(merged):,} filas")
    agregar_etapa("Despues del MERGE (convocatoria + adjudicacion)", len(merged))

    log("\n[3] Filtrando por objeto contractual = 'Obra'...")
    if 'objetocontractual_conv' in merged.columns:
        filtro_obra = merged[
            merged['objetocontractual_conv'].str.upper().str.contains('OBRA', na=False)
        ].copy()
    else:
        filtro_obra = merged.copy()
    log(f"  Resultado: {len(filtro_obra):,}")
    agregar_etapa("Filtro 1: Objeto contractual = 'Obra'", len(filtro_obra))

    log("\n[4] Filtrando por infraestructura vial (palabras clave)...")
    palabras_viales = 'VIAL|CARRETERA|PUENTE|CAMINO|PAVIMENT|ASFALTO|TRÁNSITO|TRANSITO|AUTOPISTA'
    filtro_vial = filtro_obra[
        filtro_obra['descripcion_proceso_conv'].str.contains(palabras_viales, case=False, na=False)
    ].copy()
    log(f"  Resultado: {len(filtro_vial):,}")
    agregar_etapa("Filtro 2: Descripcion con palabras clave viales", len(filtro_vial))

    log("\n[5] Filtrando por monto referencial > 25 millones soles...")
    filtro_monto = filtro_vial[
        filtro_vial['monto_referencial_item'] > 25000000
    ].copy()
    log(f"  Resultado: {len(filtro_monto):,}")
    agregar_etapa("Filtro 3: Monto referencial > S/ 25,000,000", len(filtro_monto))

    log("\n[6] Filtrando por modalidad = Licitacion Publica...")
    filtro_lp = filtro_monto[
        filtro_monto['tipoprocesoseleccion_conv'].str.contains('LICITACIÓN PÚBLICA', case=False, na=False)
    ].copy()
    log(f"  Resultado: {len(filtro_lp):,}")
    agregar_etapa("Filtro 4: Modalidad = 'Licitacion Publica'", len(filtro_lp))

    log("\n[7] Aplicando filtros de exclusion...")
    palabras_excluir = ('AGUA POTABLE|ALCANTARILLADO|SALUD|HOSPITAL|'
                        'ESTABLECIMIENTO DE SALUD|REDES COMPLEMENTARIAS|'
                        'MURO DE PROTECCIÓN|DRENAJE|FLUVIAL|ADQUISICION|ADQUISICIÓN|'
                        'PRESA|IRRIGACIÓN|PUENTE PEATONAL')
    filtro_excluido = filtro_lp[
        ~filtro_lp['descripcion_proceso_conv'].str.contains(palabras_excluir, case=False, na=False)
    ].copy()
    log(f"  Resultado: {len(filtro_excluido):,}")
    agregar_etapa("Filtro 5: Exclusiones (agua, salud, drenaje, etc.)", len(filtro_excluido))

    log("\n[8] Eliminando duplicados por codigo de convocatoria...")
    filtrado = filtro_excluido.drop_duplicates(
        subset=['codigoconvocatoria'],
        keep='first'
    ).copy()
    log(f"  Resultado: {len(filtrado):,}")
    agregar_etapa("Filtro 6: Procesos unicos (sin duplicados)", len(filtrado))

    log("\n[9] Calculando plazos...")
    filtrado['fecha_convocatoria_conv'] = pd.to_datetime(
        filtrado['fecha_convocatoria_conv'], errors='coerce', dayfirst=True)
    filtrado['fechaintegracionbases'] = pd.to_datetime(
        filtrado['fechaintegracionbases'], errors='coerce', dayfirst=True)
    filtrado['fecha_buenapro'] = pd.to_datetime(
        filtrado['fecha_buenapro'], errors='coerce', dayfirst=True)

    filtrado['duracion_etapa_consultas_dias'] = (
        filtrado['fechaintegracionbases'] - filtrado['fecha_convocatoria_conv']
    ).dt.days
    filtrado['duracion_etapa_evaluacion_dias'] = (
        filtrado['fecha_buenapro'] - filtrado['fechaintegracionbases']
    ).dt.days
    filtrado['plazo_total_adjudicacion_dias'] = (
        filtrado['fecha_buenapro'] - filtrado['fecha_convocatoria_conv']
    ).dt.days

    log("  Plazos calculados.")

    log("\n[10] Preparando columnas finales...")
    columnas_finales = [
        'codigoconvocatoria',
        'descripcion_proceso_conv',
        'montoreferencial',
        'monto_adjudicado_item_soles',
        'fecha_convocatoria_conv',
        'fechaintegracionbases',
        'fecha_buenapro',
        'duracion_etapa_consultas_dias',
        'duracion_etapa_evaluacion_dias',
        'plazo_total_adjudicacion_dias'
    ]

    base_final = filtrado[columnas_finales].copy()
    base_final.rename(columns={
        'descripcion_proceso_conv': 'descripcion_proceso',
        'fecha_convocatoria_conv': 'fecha_convocatoria'
    }, inplace=True)

    base_final['cant_consultas_observaciones'] = None

    log(f"\n[11] Guardando Excel base: {EXCEL_BASE.name}")
    base_final.to_excel(EXCEL_BASE, index=False)
    log(f"  Guardado: {EXCEL_BASE}")

    log(f"\n[12] Guardando flujo de seleccion (embudo)...")
    df_embudo = pd.DataFrame(embudo)
    df_embudo.to_excel(EXCEL_EMBUDO, index=False)
    log(f"  Guardado: {EXCEL_EMBUDO}")

    log("\n[13] Verificacion piloto 2020...")
    codigos_piloto = [664728, 638506, 676061, 696209, 654278, 654914, 653257,
                      645854, 693199, 619504, 678446, 686773, 644853, 619659]
    presentes = base_final[base_final['codigoconvocatoria'].isin(codigos_piloto)]
    log(f"  Codigos piloto encontrados: {len(presentes)} de 14")

    log("\n" + "=" * 70)
    log(" EMBUDO DE SELECCION")
    log("=" * 70)
    for etapa in embudo:
        log(f"  {etapa['etapa']}: {etapa['cantidad']:,}")

    log("\n" + "=" * 70)
    log(f" MUESTRA FINAL: {len(base_final)} procesos")
    log("=" * 70)

if __name__ == "__main__":
    main()
