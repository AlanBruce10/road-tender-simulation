import pandas as pd

df = pd.read_excel(r'D:\00_THESIS_ALAN_BRUCE\CORRER CÓDIGO PARA CONSULTAS Y OBSERVACIONES\03_resultados\BASE_FINAL_CON_CONTEOS.xlsx')

p25 = df['cant_consultas_observaciones'].quantile(0.25)
p75 = df['cant_consultas_observaciones'].quantile(0.75)

print(f"P25: {p25}")
print(f"P75: {p75}")

def clasificar(valor):
    if valor <= p25:
        return "Baja asimetria"
    elif valor <= p75:
        return "Media asimetria"
    else:
        return "Alta asimetria"

df['escenario'] = df['cant_consultas_observaciones'].apply(clasificar)

print("\nDistribucion por escenario:")
print(df['escenario'].value_counts())

print("\nEstadisticas por escenario:")
for escenario in ["Baja asimetria", "Media asimetria", "Alta asimetria"]:
    grupo = df[df['escenario'] == escenario]
    print(f"\n{escenario}:")
    print(f"  N: {len(grupo)}")
    print(f"  Media consultas: {grupo['cant_consultas_observaciones'].mean():.2f}")
    print(f"  Media plazo: {grupo['plazo_total_adjudicacion_dias'].mean():.2f}")
    print(f"  Desv. plazo: {grupo['plazo_total_adjudicacion_dias'].std():.2f}")
