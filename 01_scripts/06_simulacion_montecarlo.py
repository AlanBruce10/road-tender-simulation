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
EXCEL_SALIDA = SIMULACION_DIR / "resultados_montecarlo.xlsx"

N_ITERACIONES = 10000
SEMILLA = 42

def main():
    print("=" * 70)
    print(" SIMULACION DE MONTE CARLO")
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

    print(f"\nIteraciones por escenario: {N_ITERACIONES}")

    for escenario in escenarios:
        print("\n" + "=" * 70)
        print(f" ESCENARIO: {escenario}")
        print("=" * 70)

        datos_reales = df[df['escenario'] == escenario]['plazo_total_adjudicacion_dias'].values
        datos_reales = datos_reales[datos_reales > 0]

        shape, loc, scale = stats.lognorm.fit(datos_reales, floc=0)

        print(f"N real: {len(datos_reales)}")
        print(f"Media real: {datos_reales.mean():.2f} dias")
        print(f"Desv. real: {datos_reales.std():.2f} dias")

        simulados = stats.lognorm.rvs(shape, loc, scale, size=N_ITERACIONES, random_state=SEMILLA)

        media_sim = simulados.mean()
        desv_sim = simulados.std()
        p50_sim = np.percentile(simulados, 50)
        p80_sim = np.percentile(simulados, 80)
        p95_sim = np.percentile(simulados, 95)

        p95_real = np.percentile(datos_reales, 95)
        prob_retraso = np.mean(simulados > p95_real) * 100

        ks_stat, p_value = stats.kstest(datos_reales, 'lognorm', args=(shape, loc, scale))

        print(f"\nSimulados ({N_ITERACIONES} iteraciones):")
        print(f"  Media: {media_sim:.2f} dias")
        print(f"  Desv. estandar: {desv_sim:.2f} dias")
        print(f"  P50: {p50_sim:.2f} dias")
        print(f"  P80: {p80_sim:.2f} dias")
        print(f"  P95: {p95_sim:.2f} dias")
        print(f"  Prob. retraso extremo (> P95 real = {p95_real:.2f}): {prob_retraso:.2f}%")

        resultados.append({
            "Escenario": escenario,
            "N_real": len(datos_reales),
            "Media_real": datos_reales.mean(),
            "Desv_real": datos_reales.std(),
            "Media_sim": media_sim,
            "Desv_sim": desv_sim,
            "P50_sim": p50_sim,
            "P80_sim": p80_sim,
            "P95_sim": p95_sim,
            "P95_real": p95_real,
            "Prob_retraso_extremo": prob_retraso,
            "KS_estadistico": ks_stat,
            "KS_pvalor": p_value
        })

    df_resultados = pd.DataFrame(resultados)
    df_resultados.to_excel(EXCEL_SALIDA, index=False)

    print("\n" + "=" * 70)
    print(" RESUMEN COMPARATIVO")
    print("=" * 70)
    print(df_resultados.to_string(index=False))

    print(f"\n\nResultados guardados en: {EXCEL_SALIDA}")

    print("\n" + "=" * 70)
    print(" FIN DE LA SIMULACION")
    print("=" * 70)

if __name__ == "__main__":
    main()