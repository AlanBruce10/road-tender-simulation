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
EXCEL_SALIDA = SIMULACION_DIR / "ajuste_distribuciones.xlsx"

def main():
    print("=" * 70)
    print(" AJUSTE DE DISTRIBUCIONES DE PROBABILIDAD")
    print("=" * 70)

    df = pd.read_excel(EXCEL_BASE)
    df = df.dropna(subset=['plazo_total_adjudicacion_dias'])
    print(f"\nTotal de procesos: {len(df)}")

    p25 = df['cant_consultas_observaciones'].quantile(0.25)
    p75 = df['cant_consultas_observaciones'].quantile(0.75)
    print(f"P25 = {p25}")
    print(f"P75 = {p75}")

    def clasificar(valor):
        if valor <= p25:
            return "Baja asimetria"
        elif valor <= p75:
            return "Media asimetria"
        else:
            return "Alta asimetria"

    df['escenario'] = df['cant_consultas_observaciones'].apply(clasificar)

    escenarios = ["Baja asimetria", "Media asimetria", "Alta asimetria"]
    distribuciones = ["Lognormal", "Weibull", "Gamma"]

    resultados = []

    for escenario in escenarios:
        print("\n" + "=" * 70)
        print(f" ESCENARIO: {escenario}")
        print("=" * 70)

        datos = df[df['escenario'] == escenario]['plazo_total_adjudicacion_dias'].values
        datos = datos[datos > 0]

        print(f"N: {len(datos)}")
        print(f"Media: {datos.mean():.2f} dias")
        print(f"Desv. estandar: {datos.std():.2f} dias")
        print(f"Minimo: {datos.min():.2f}")
        print(f"Maximo: {datos.max():.2f}")

        for dist_name in distribuciones:
            try:
                if dist_name == "Lognormal":
                    shape, loc, scale = stats.lognorm.fit(datos, floc=0)
                    params = f"sigma={shape:.4f}, scale={scale:.4f}"
                    ks_stat, p_value = stats.kstest(
                        datos, 'lognorm', args=(shape, loc, scale))
                    aic = 2 * 3 - 2 * np.sum(stats.lognorm.logpdf(datos, shape, loc, scale))

                elif dist_name == "Weibull":
                    shape, loc, scale = stats.weibull_min.fit(datos, floc=0)
                    params = f"shape={shape:.4f}, scale={scale:.4f}"
                    ks_stat, p_value = stats.kstest(
                        datos, 'weibull_min', args=(shape, loc, scale))
                    aic = 2 * 3 - 2 * np.sum(stats.weibull_min.logpdf(datos, shape, loc, scale))

                elif dist_name == "Gamma":
                    shape, loc, scale = stats.gamma.fit(datos, floc=0)
                    params = f"alpha={shape:.4f}, scale={scale:.4f}"
                    ks_stat, p_value = stats.kstest(
                        datos, 'gamma', args=(shape, loc, scale))
                    aic = 2 * 3 - 2 * np.sum(stats.gamma.logpdf(datos, shape, loc, scale))

                ajusta = "SI" if p_value > 0.05 else "NO"

                print(f"\n  {dist_name}:")
                print(f"    Parametros: {params}")
                print(f"    K-S: {ks_stat:.4f}")
                print(f"    p-valor: {p_value:.4f}")
                print(f"    AIC: {aic:.2f}")
                print(f"    Ajusta (p > 0.05): {ajusta}")

                resultados.append({
                    "Escenario": escenario,
                    "Distribucion": dist_name,
                    "N": len(datos),
                    "Parametros": params,
                    "KS_estadistico": ks_stat,
                    "KS_pvalor": p_value,
                    "AIC": aic,
                    "Ajusta": ajusta
                })

            except Exception as e:
                print(f"\n  {dist_name}: ERROR - {str(e)[:100]}")

    df_resultados = pd.DataFrame(resultados)

    print("\n" + "=" * 70)
    print(" RESUMEN: MEJOR DISTRIBUCION POR ESCENARIO")
    print("=" * 70)

    mejores = []
    for escenario in escenarios:
        subset = df_resultados[df_resultados["Escenario"] == escenario]
        if len(subset) == 0:
            continue
        mejor = subset.loc[subset["AIC"].idxmin()]
        mejores.append(mejor)
        print(f"\n{escenario}:")
        print(f"  Mejor distribucion (menor AIC): {mejor['Distribucion']}")
        print(f"  Parametros: {mejor['Parametros']}")
        print(f"  K-S: {mejor['KS_estadistico']:.4f}")
        print(f"  p-valor: {mejor['KS_pvalor']:.4f}")
        print(f"  Ajusta: {mejor['Ajusta']}")

    df_mejores = pd.DataFrame(mejores)
    df_mejores.to_excel(EXCEL_SALIDA, index=False)
    print(f"\n\nResultados guardados en: {EXCEL_SALIDA}")

    print("\n" + "=" * 70)
    print(" FIN DEL AJUSTE")
    print("=" * 70)

if __name__ == "__main__":
    main()
