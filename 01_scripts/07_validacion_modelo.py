import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

RESULTADOS_DIR = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\03_resultados")
SIMULACION_DIR = Path(r"D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\05_simulacion")
SIMULACION_DIR.mkdir(parents=True, exist_ok=True)

EXCEL_BASE = RESULTADOS_DIR / "BASE_FINAL_CON_CONTEOS.xlsx"
EXCEL_SALIDA = SIMULACION_DIR / "validacion_modelo.xlsx"

N_ITERACIONES = 10000
SEMILLA = 42

def main():
    print("=" * 70)
    print(" VALIDACION DEL MODELO")
    print("=" * 70)

    np.random.seed(SEMILLA)

    df = pd.read_excel(EXCEL_BASE)
    df = df.dropna(subset=['plazo_total_adjudicacion_dias'])
    print(f"\nTotal de procesos: {len(df)}")

    p25 = df['cant_consultas_observaciones'].quantile(0.25)
    p75 = df['cant_consultas_observaciones'].quantile(0.75)

    def clasificar(valor):
        if valor <= p25:
            return "Baja asimetria"
        elif valor <= p75:
            return "Media asimetria"
        else:
            return "Alta asimetria"

    df['escenario'] = df['cant_consultas_observaciones'].apply(clasificar)

    escenarios = ["Baja asimetria", "Media asimetria", "Alta asimetria"]
    resultados = []

    for escenario in escenarios:
        print("\n" + "=" * 70)
        print(f" ESCENARIO: {escenario}")
        print("=" * 70)

        datos_reales = df[df['escenario'] == escenario]['plazo_total_adjudicacion_dias'].values
        datos_reales = datos_reales[datos_reales > 0]

        shape, loc, scale = stats.lognorm.fit(datos_reales, floc=0)
        simulados = stats.lognorm.rvs(shape, loc, scale, size=N_ITERACIONES, random_state=SEMILLA)

        print(f"\nDatos reales: n = {len(datos_reales)}, media = {datos_reales.mean():.2f}, desv = {datos_reales.std():.2f}")
        print(f"Datos simulados: n = {len(simulados)}, media = {simulados.mean():.2f}, desv = {simulados.std():.2f}")

        ks_stat, ks_pvalue = stats.kstest(datos_reales, simulados)
        print(f"\n[1] Prueba K-S (simulados vs reales):")
        print(f"    Estadistico: {ks_stat:.4f}")
        print(f"    p-valor: {ks_pvalue:.4f}")
        print(f"    Conclusion: {'NO hay diferencia significativa (p > 0.05)' if ks_pvalue > 0.05 else 'SI hay diferencia significativa (p < 0.05)'}")

        t_stat, t_pvalue = stats.ttest_ind(datos_reales, simulados, equal_var=False)
        print(f"\n[2] Prueba t-Student (medias):")
        print(f"    t: {t_stat:.4f}")
        print(f"    p-valor: {t_pvalue:.4f}")
        print(f"    Conclusion: {'NO hay diferencia significativa (p > 0.05)' if t_pvalue > 0.05 else 'SI hay diferencia significativa (p < 0.05)'}")

        lev_stat, lev_pvalue = stats.levene(datos_reales, simulados)
        print(f"\n[3] Prueba de Levene (varianzas):")
        print(f"    Estadistico: {lev_stat:.4f}")
        print(f"    p-valor: {lev_pvalue:.4f}")
        print(f"    Conclusion: {'NO hay diferencia significativa (p > 0.05)' if lev_pvalue > 0.05 else 'SI hay diferencia significativa (p < 0.05)'}")

        resultados.append({
            "Escenario": escenario,
            "N_real": len(datos_reales),
            "Media_real": datos_reales.mean(),
            "Desv_real": datos_reales.std(),
            "Media_sim": simulados.mean(),
            "Desv_sim": simulados.std(),
            "KS_estadistico": ks_stat,
            "KS_pvalor": ks_pvalue,
            "KS_conclusion": "Valido" if ks_pvalue > 0.05 else "No valido",
            "t_estadistico": t_stat,
            "t_pvalor": t_pvalue,
            "t_conclusion": "Valido" if t_pvalue > 0.05 else "No valido",
            "Levene_estadistico": lev_stat,
            "Levene_pvalor": lev_pvalue,
            "Levene_conclusion": "Valido" if lev_pvalue > 0.05 else "No valido"
        })

    df_resultados = pd.DataFrame(resultados)
    df_resultados.to_excel(EXCEL_SALIDA, index=False)

    print("\n" + "=" * 70)
    print(" RESUMEN DE VALIDACION")
    print("=" * 70)
    print(df_resultados[["Escenario", "KS_pvalor", "KS_conclusion",
                          "t_pvalor", "t_conclusion",
                          "Levene_pvalor", "Levene_conclusion"]].to_string(index=False))

    print(f"\n\nResultados guardados en: {EXCEL_SALIDA}")

    print("\n" + "=" * 70)
    print(" FIN DE LA VALIDACION")
    print("=" * 70)

if __name__ == "__main__":
    main()