import pandas as pd
import os
import requests
import matplotlib.pyplot as plt

# ==========================================
# --- 1. PARÂMETROS E CONFIGURAÇÕES GERAIS ---
# ==========================================
path = '/Users/gustavomendes/Faculdade/3° Semestre/Programação para Análise de Dados/trabalho_ap2'

# Parâmetros Macroeconômicos e de Exportação (2025)
CAMBIO_2025 = 5.10
receitas_br_brl = {
    'Klabin': 11.2,  
    'Marfrig': 48.5, 
    'Weg': 23.2      
}

# Parâmetros Financeiros e API
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzgwNTcwNzA4LCJpYXQiOjE3Nzc5Nzg3MDgsImp0aSI6IjNmNTBiZWM4OWVkZDQzMWI5NTljZWFkYmFkZTdiNjYyIiwidXNlcl9pZCI6IjExOCJ9.4m2iY0iB32ZKdO6_uZb-H1Cu9zwOXJcenbCHAv-qTFE"
headers = {"Authorization": f"Bearer {token}"}
base_url = "https://laboratoriodefinancas.com/api/v2"

# Mapeamento de Empresas para Tickers (Ajustado para MBRF3)
tickers = {
    'Marfrig': 'MBRF3',
    'Klabin': 'KLBN11',
    'Weg': 'WEGE3'
}

# Estimativas para o cálculo do EVA (Substitua pelos valores exatos da sua pesquisa)
parametros_eva = {
    'MBRF3':  {'roi': 0.12, 'cmpc': 0.10}, 
    'KLBN11': {'roi': 0.15, 'cmpc': 0.11},
    'WEGE3':  {'roi': 0.22, 'cmpc': 0.13}
}


# ==========================================
# --- 2. ANÁLISE DE EXPORTAÇÕES E HHI ---
# ==========================================
file_path = os.path.join(path, 'produtos_industria_transformacao.csv')
df_sh4 = pd.read_csv(file_path, sep=';', decimal=',', encoding='utf-8')

col_valor_usd = '2025 - Valor US$ FOB'
df_sh4[col_valor_usd] = pd.to_numeric(df_sh4[col_valor_usd], errors='coerce').fillna(0)
total_it_usd = df_sh4[col_valor_usd].sum()

df_sh4['share'] = df_sh4[col_valor_usd] / total_it_usd
hhi_pauta = (df_sh4['share'] ** 2).sum()

df_empresas = pd.DataFrame(list(receitas_br_brl.items()), columns=['Empresa', 'Receita_BRL'])
df_empresas['Receita_USD'] = (df_empresas['Receita_BRL'] * 1e9) / CAMBIO_2025
df_empresas['Participacao_IT_%'] = (df_empresas['Receita_USD'] / total_it_usd) * 100


# ==========================================
# --- 3. EXTRAÇÃO FINANCEIRA E CÁLCULOS ---
# ==========================================
def encontrar_contas_contabeis(df):
    ativo_total = float(df[df["conta"]=='1']['valor'].iloc[0])
    ativo_circ = float(df[df["conta"]=='1.01']['valor'].iloc[0])
    passivo_circ = float(df[df["conta"]=='2.01']['valor'].iloc[0])
    passivo_n_circ = float(df[df["conta"]=='2.02']['valor'].iloc[0])
    
    filtro_arlp = df["conta"] == '1.02.01'
    arlp = float(df[filtro_arlp]['valor'].iloc[0]) if not df[filtro_arlp].empty else 0.0
    
    filtro_estoque = df["descricao"].str.contains('estoque', case=False)
    estoque = float(df[filtro_estoque]['valor'].iloc[0]) if not df[filtro_estoque].empty else 0.0

    filtro_disponibilidades = df["conta"].isin(['1.01.01', '1.01.02'])
    caixa_equivalentes = df[filtro_disponibilidades]['valor'].astype(float).sum()

    filtro_despesa = df["descricao"].str.contains('antecipada', case=False)
    despesa_antecipada = float(df[filtro_despesa]['valor'].iloc[0]) if not df[filtro_despesa].empty else 0.0

    return {
        "ativo_total": ativo_total,
        "ativo_circ": ativo_circ,
        "passivo_circ": passivo_circ,
        "passivo_n_circ": passivo_n_circ,
        "arlp": arlp,
        "estoque": estoque,
        "despesa_antecipada": despesa_antecipada,
        "caixa_equivalentes": caixa_equivalentes
    }

def calcular_indicadores(d, roi, cmpc):
    # Investimento (Capital Empregado) = Ativo Total - Passivo Circulante
    investimento = d["ativo_total"] - d["passivo_circ"]
    
    return {
        'ccl': d["ativo_circ"] - d["passivo_circ"],
        'lc': d["ativo_circ"] / d["passivo_circ"],
        'lg': (d["ativo_circ"] + d["arlp"]) / (d["passivo_circ"] + d["passivo_n_circ"]),
        'ls': (d["ativo_circ"] - d["estoque"] - d["despesa_antecipada"]) / d["passivo_circ"],
        'la': d["caixa_equivalentes"] / d["passivo_circ"],
        'eva': (roi - cmpc) * investimento
    }

resultados_financeiros = {}

print("\n### STATUS DE CONEXÃO COM A API ###")
for nome, ticker in tickers.items():
    # Sistema de Fallback: Se 20254T não estiver disponível, tenta os trimestres anteriores
    periodos_tentativa = ["20254T", "20253T", "20244T"]
    dados_encontrados = False
    
    for periodo in periodos_tentativa:
        resp = requests.get(f"{base_url}/bolsa/balanco", headers=headers, params={"ticker": ticker, "ano_tri": periodo})
        
        if resp.status_code == 200 and len(resp.json()) > 0:
            try:
                df_balanco = pd.DataFrame(resp.json()[0]['balanco'])
                contas = encontrar_contas_contabeis(df_balanco)
                
                roi = parametros_eva[ticker]['roi']
                cmpc = parametros_eva[ticker]['cmpc']
                
                indicadores = calcular_indicadores(contas, roi, cmpc)
                resultados_financeiros[nome] = indicadores
                
                print(f"[{nome}] OK - Dados processados (Referência: {periodo})")
                dados_encontrados = True
                break
            except IndexError:
                continue
                
    if not dados_encontrados:
        resultados_financeiros[nome] = None
        print(f"[{nome}] FALHA - Dados não encontrados em nenhum período.")


# ==========================================
# --- 4. EXIBIÇÃO ESTRUTURADA DOS RESULTADOS ---
# ==========================================
print("\n### RESULTADOS DE EXPORTAÇÃO (2025) ###")
print(f"* Exportação Total da Indústria de Transformação: US$ {total_it_usd/1e9:.2f} Bilhões")
print(f"* Índice de Concentração (HHI) da Pauta: {hhi_pauta:.4f}")

for index, row in df_empresas.iterrows():
    print(f"* Participação {row['Empresa']}: {row['Participacao_IT_%']:.4f}%")


print("\n### INDICADORES FINANCEIROS DE LIQUIDEZ E CRIAÇÃO DE VALOR ###")
for nome in tickers.keys():
    print(f"\n**{nome.upper()} ({tickers[nome]})**")
    if resultados_financeiros[nome]:
        ind = resultados_financeiros[nome]
        
        ccl_formatado = f"R$ {ind['ccl']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        eva_formatado = f"R$ {ind['eva']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        
        print(f"  * Capital Circulante Líquido (CCL): {ccl_formatado}")
        print(f"  * Liquidez Corrente (LC): {ind['lc']:.4f}")
        print(f"  * Liquidez Geral (LG): {ind['lg']:.4f}")
        print(f"  * Liquidez Seca (LS): {ind['ls']:.4f}")
        print(f"  * Liquidez Imediata (LA): {ind['la']:.4f}")
        print(f"  * Economic Value Added (EVA): {eva_formatado}")
    else:
        print("  * Dados não disponíveis.")


# ==========================================
# --- 5. VISUALIZAÇÃO GRÁFICA ---
# ==========================================
# Gráfico 1: Participação no Volume de Exportações (HHI / Market Share)
plt.figure(figsize=(10, 6))
plt.bar(df_empresas['Empresa'], df_empresas['Participacao_IT_%'], color=['#004a8d', '#009541', '#6d6e71'])
plt.title('Participação no Volume Total de Exportações da Indústria de Transformação (2025)')
plt.ylabel('% de Participação')
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.show()

# Extração dos dados de EVA para o gráfico 2
empresas_eva = []
valores_eva_milhoes = []
cores_empresas = {'Marfrig': '#004a8d', 'Klabin': '#009541', 'Weg': '#6d6e71'}
cores_grafico = []

for nome in tickers.keys():
    if resultados_financeiros[nome] and 'eva' in resultados_financeiros[nome]:
        empresas_eva.append(nome)
        valores_eva_milhoes.append(resultados_financeiros[nome]['eva'] / 1e6)
        cores_grafico.append(cores_empresas.get(nome, '#333333'))

# Gráfico 2: Comparação da Criação de Valor (EVA)
if empresas_eva:
    plt.figure(figsize=(10, 6))
    bars = plt.bar(empresas_eva, valores_eva_milhoes, color=cores_grafico)
    
    # Linha zero para destacar EVA positivo x negativo
    plt.axhline(0, color='black', linewidth=1.5)
    
    plt.title('Economic Value Added (EVA) Estimado')
    plt.ylabel('EVA (em Milhões de R$)')
    plt.grid(axis='y', linestyle='--', alpha=0.6)
    
    for bar in bars:
        yval = bar.get_height()
        posicao_texto = yval + (abs(yval) * 0.05) if yval >= 0 else yval - (abs(yval) * 0.05)
        plt.text(bar.get_x() + bar.get_width()/2, posicao_texto, 
                 f'R$ {yval:,.1f} mi'.replace(',', 'X').replace('.', ',').replace('X', '.'), 
                 ha='center', va='bottom' if yval >= 0 else 'top', fontweight='bold')
                 
    plt.show()