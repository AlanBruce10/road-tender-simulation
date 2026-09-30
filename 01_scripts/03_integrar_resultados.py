import pandas as pd
from pathlib import Path

RESULTADOS_DIR = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\03_resultados")

EXCEL_BASE = RESULTADOS_DIR / "BASE_FINAL_137_PROCESOS.xlsx"
EXCEL_CONTEOS = RESULTADOS_DIR / "conteos_consultas.xlsx"
EXCEL_SALIDA = RESULTADOS_DIR / "BASE_FINAL_CON_CONTEOS.xlsx"

def main():
    print("=" * 60)
    print(" INTEGRACION DE RESULTADOS")
    print("=" * 60)

    print(f"\n[1/4] Leyendo Excel base: {EXCEL_BASE.name}")
    if not EXCEL_BASE.exists():
        print(f"   ERROR: No existe {EXCEL_BASE}")
        return
    df_base = pd.read_excel(EXCEL_BASE)
    print(f"      Filas: {len(df_base)}")

    print(f"\n[2/4] Leyendo Excel de conteos: {EXCEL_CONTEOS.name}")
    if not EXCEL_CONTEOS.exists():
        print(f"   ERROR: No existe {EXCEL_CONTEOS}")
        print(f"   Verifica el nombre del archivo en: {RESULTADOS_DIR}")
        return
    df_conteos = pd.read_excel(EXCEL_CONTEOS)
    print(f"      Filas: {len(df_conteos)}")

    print(f"\n[3/4] Integrando datos...")

    df_base["codigoconvocatoria"] = df_base["codigoconvocatoria"].astype(str)
    df_conteos["codigoconvocatoria"] = df_conteos["codigoconvocatoria"].astype(str)

    columnas_merge = [
        "codigoconvocatoria",
        "tipo_documento",
        "total_consultas_observaciones",
        "metodo",
        "confianza",
        "estado_conteo",
        "notas"
    ]

    columnas_disponibles = [c for c in columnas_merge if c in df_conteos.columns]
    df_conteos_subset = df_conteos[columnas_disponibles]

    df_final = df_base.merge(
        df_conteos_subset,
        on="codigoconvocatoria",
        how="left"
    )

    print(f"      Filas despues del merge: {len(df_final)}")

    df_final["cant_consultas_observaciones"] = df_final["total_consultas_observaciones"]

    sin_conteo = df_final[df_final["cant_consultas_observaciones"].isna()]
    print(f"\n      Procesos sin conteo: {len(sin_conteo)}")

    if len(sin_conteo) > 0:
        print("      Codigos sin conteo:")
        for cod in sin_conteo["codigoconvocatoria"].tolist()[:20]:
            print(f"        - {cod}")

    print(f"\n[4/4] Guardando Excel final: {EXCEL_SALIDA.name}")
    df_final.to_excel(EXCEL_SALIDA, index=False)
    print(f"      Guardado en: {EXCEL_SALIDA}")

    print("\n" + "=" * 60)
    print(" RESUMEN ESTADISTICO")
    print("=" * 60)

    con_conteo = df_final[df_final["cant_consultas_observaciones"].notna()]
    print(f"Procesos con conteo: {len(con_conteo)}")
    print(f"Procesos sin conteo: {len(df_final) - len(con_conteo)}")

    if len(con_conteo) > 0:
        print(f"\nEstadisticas de cant_consultas_observaciones:")
        print(f"  Media: {con_conteo['cant_consultas_observaciones'].mean():.2f}")
        print(f"  Mediana: {con_conteo['cant_consultas_observaciones'].median()}")
        print(f"  Maximo: {con_conteo['cant_consultas_observaciones'].max()}")
        print(f"  Minimo: {con_conteo['cant_consultas_observaciones'].min()}")
        print(f"  Desviacion estandar: {con_conteo['cant_consultas_observaciones'].std():.2f}")

        print(f"\nPercentiles:")
        for p in [25, 50, 75, 90]:
            valor = con_conteo['cant_consultas_observaciones'].quantile(p/100)
            print(f"  P{p}: {valor:.2f}")

    print("\n" + "=" * 60)
    print(" FIN DEL PROCESO")
    print("=" * 60)

if __name__ == "__main__":
    main()
