import pandas as pd
from pathlib import Path
import time
import requests
import matplotlib.pyplot as plt

# ==========================================
# --- 1. PARÂMETROS E CONFIGURAÇÕES GERAIS ---
# ==========================================
path = Path(__file__).parent.resolve()

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

# Mapeamento de Empresas para Tickers
tickers = {
    'Marfrig': 'MBRF3',
    'Klabin': 'KLBN11',
    'Weg': 'WEGE3'
}

# Estimativas para o cálculo do EVA
parametros_eva = {
    'MBRF3':  {'roi': 0.12, 'cmpc': 0.10}, 
    'KLBN11': {'roi': 0.15, 'cmpc': 0.11},
    'WEGE3':  {'roi': 0.22, 'cmpc': 0.13}
}


# ==========================================
# --- 2. ANÁLISE DE EXPORTAÇÕES E HHI ---
# ==========================================
file_path = path / 'produtos_industria_transformacao.csv'
df_sh4 = pd.read_csv(file_path, sep=';', decimal=',', encoding='utf-8')

col_valor_usd = '2025 - Valor US$ FOB'
df_sh4[col_valor_usd] = pd.to_numeric(df_sh4[col_valor_usd], errors='coerce').fillna(0)
total_it_usd = df_sh4[col_valor_usd].sum()

df_sh4['share'] = df_sh4[col_valor_usd] / total_it_usd
hhi_pauta = (df_sh4['share'] ** 2).sum()

df_empresas = pd.DataFrame(list(receitas_br_brl.items()), columns=['Empresa', 'Receita_BRL'])
df_empresas['Receita_USD'] = (df_empresas['Receita_BRL'] * 1e9) / CAMBIO_2025
df_empresas['Participacao_IT_%'] = (df_empresas['Receita_USD'] / total_it_usd) * 100

# --- 2.1 ANÁLISE HISTÓRICA CONSOLIDADA (PD.MERGE) ---
# Função para buscar dados da API Comex Stat com retry em caso de erro 429
def fetch_comex_data(name, filters, details):
    url_query = "https://api-comexstat.mdic.gov.br/general?language=pt"
    payload = {
        "flow": "export",
        "monthDetail": True,
        "period": {
            "from": "2016-01",
            "to": "2026-12"  # Contorna o bug do filtro de meses na API Comex Stat
        },
        "filters": filters,
        "details": details,
        "metrics": ["metricFOB", "metricKG"]
    }
    max_retries = 5
    delay = 12
    for attempt in range(max_retries):
        print(f"[{name}] Buscando dados na API Comex Stat (tentativa {attempt + 1}/{max_retries})...")
        try:
            r = requests.post(url_query, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json().get('data', {}).get('list', [])
                print(f"[{name}] Sucesso! {len(data)} registros retornados.")
                return data
            elif r.status_code == 429:
                print(f"[{name}] Limite de requisições (429). Aguardando {delay}s...")
                time.sleep(delay)
            else:
                print(f"[{name}] Erro {r.status_code}: {r.text}. Aguardando {delay}s...")
                time.sleep(delay)
        except Exception as e:
            print(f"[{name}] Exceção: {e}. Aguardando {delay}s...")
            time.sleep(delay)
    raise RuntimeError(f"Falha crítica ao buscar dados para {name} após {max_retries} tentativas.")

def process_comex_df(raw_data, is_celulose=False, is_total=False):
    if not raw_data:
        return pd.DataFrame()
    df = pd.DataFrame(raw_data)
    df['metricFOB'] = pd.to_numeric(df['metricFOB'], errors='coerce').fillna(0)
    df['metricKG'] = pd.to_numeric(df['metricKG'], errors='coerce').fillna(0)
    
    if is_celulose:
        df = df[df['headingCode'] != '4707']
        
    groupby_cols = ['year', 'monthNumber']
    grouped = df.groupby(groupby_cols).agg({
        'metricFOB': 'sum',
        'metricKG': 'sum'
    }).reset_index()
    
    grouped['periodo'] = pd.to_datetime(grouped['year'] + '-' + grouped['monthNumber'])
    grouped = grouped[grouped['periodo'] <= '2026-04']
    
    if is_total:
        result = pd.DataFrame({
            'periodo': grouped['periodo'],
            'vl_fob': grouped['metricFOB'],
            'quantum': 0.0,
            'preco': 0.0
        })
    else:
        vl_fob = grouped['metricFOB']
        kg_liquido = grouped['metricKG']
        preco = (vl_fob / kg_liquido).fillna(0)
        result = pd.DataFrame({
            'periodo': grouped['periodo'],
            'vl_fob': vl_fob,
            'kg_liquido': kg_liquido,
            'preco': preco
        })
    return result.sort_values('periodo').reset_index(drop=True)

# Buscar os dados via API com espaçamento de 10s para respeitar limites
raw_carne = fetch_comex_data("Carne Bovina", [{"filter": "heading", "values": ["0201", "0202"]}], ["heading"])
time.sleep(10)

raw_celulose = fetch_comex_data("Celulose", [{"filter": "chapter", "values": ["47"]}], ["heading"])
time.sleep(10)

raw_maquinas = fetch_comex_data("Máquinas (Weg)", [{"filter": "heading", "values": ["8501"]}], ["heading"])
time.sleep(10)

raw_total = fetch_comex_data("Total Indústria", [{"filter": "ISICSection", "values": ["C"]}], ["ISICSection"])

# Processar as bases
df_carne = process_comex_df(raw_carne)
df_celulose = process_comex_df(raw_celulose, is_celulose=True)
df_maquinas = process_comex_df(raw_maquinas)
df_total = process_comex_df(raw_total, is_total=True)

# Renomeação das colunas para evitar colisão antes do merge
df_carne = df_carne.rename(columns={
    'vl_fob': 'vl_fob_carne', 'kg_liquido': 'kg_liquido_carne', 'preco': 'preco_carne'
})
df_celulose = df_celulose.rename(columns={
    'vl_fob': 'vl_fob_celulose', 'kg_liquido': 'kg_liquido_celulose', 'preco': 'preco_celulose'
})
df_maquinas = df_maquinas.rename(columns={
    'vl_fob': 'vl_fob_maquinas', 'kg_liquido': 'kg_liquido_maquinas', 'preco': 'preco_maquinas'
})
df_total = df_total.rename(columns={
    'vl_fob': 'vl_fob_total', 'quantum': 'quantum_total', 'preco': 'preco_total'
})

# Junção sequencial com pd.merge
df_merged = pd.merge(df_carne, df_celulose, on='periodo', how='inner')
df_merged = pd.merge(df_merged, df_maquinas, on='periodo', how='inner')
df_merged = pd.merge(df_merged, df_total, on='periodo', how='inner')

# Cálculo das participações (shares) mensais históricas (%)
df_merged['share_carne'] = (df_merged['vl_fob_carne'] / df_merged['vl_fob_total']) * 100
df_merged['share_celulose'] = (df_merged['vl_fob_celulose'] / df_merged['vl_fob_total']) * 100
df_merged['share_maquinas'] = (df_merged['vl_fob_maquinas'] / df_merged['vl_fob_total']) * 100


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

print("\n### ANÁLISE HISTÓRICA E EVOLUÇÃO DAS EXPORTAÇÕES (2016-2026) ###")
print(f"* Média de Participação Histórica no Total da Indústria:")
print(f"  * Carne Bovina (Marfrig): {df_merged['share_carne'].mean():.4f}%")
print(f"  * Celulose (Klabin): {df_merged['share_celulose'].mean():.4f}%")
print(f"  * Máquinas (Weg): {df_merged['share_maquinas'].mean():.4f}%")


# ==========================================
# --- 5. VISUALIZAÇÃO GRÁFICA (PADRÃO ACADÊMICO) ---
# ==========================================
# Configurações globais para estilo de publicação científica (monocromático azul / sem hachuras)
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.edgecolor'] = 'black'
plt.rcParams['axes.linewidth'] = 1.0

# --- Gráfico 1: Participação no Volume de Exportações (Rosca / Donut Chart) ---
# Cálculo das parcelas considerando o total da indústria de transformação
val_marfrig = (receitas_br_brl['Marfrig'] * 1e9) / CAMBIO_2025
val_klabin = (receitas_br_brl['Klabin'] * 1e9) / CAMBIO_2025
val_weg = (receitas_br_brl['Weg'] * 1e9) / CAMBIO_2025
val_outros = total_it_usd - (val_marfrig + val_klabin + val_weg)

labels_g1 = ['Marfrig (Carne Bovina)', 'Weg (Máquinas)', 'Klabin (Celulose)', 'Outros Setores']
sizes_g1 = [val_marfrig, val_weg, val_klabin, val_outros]
shares_g1 = [s / total_it_usd * 100 for s in sizes_g1]

# Paleta monocromática de tons de azul
colors_g1 = ['#0f2d59', '#3182ce', '#90cdf4', '#e2e8f0']

fig1, ax1 = plt.subplots(figsize=(8, 6))
wedges, texts = ax1.pie(
    shares_g1, 
    startangle=140, 
    colors=colors_g1, 
    wedgeprops=dict(width=0.4, edgecolor='black', linewidth=1.2)
)

# Rótulos com percentuais na legenda lateral para evitar sobreposições
legend_labels = [f'{lbl}: {sh:.2f}%' for lbl, sh in zip(labels_g1, shares_g1)]
ax1.legend(wedges, legend_labels, title="Empresa / Setor", loc="center left", bbox_to_anchor=(1, 0.5), frameon=True, edgecolor='black')
ax1.set_title("Participação das Empresas nas Exportações Totais da Indústria (2025)", fontweight='bold', pad=15)
plt.tight_layout()
plt.show()

# --- Gráfico 2: Comparação de EVA (Barras Monocromáticas com Rótulos) ---
# Extração dos dados de EVA
empresas_eva = []
valores_eva_milhoes = []
for nome in tickers.keys():
    if resultados_financeiros[nome] and 'eva' in resultados_financeiros[nome]:
        empresas_eva.append(nome)
        valores_eva_milhoes.append(resultados_financeiros[nome]['eva'] / 1e6)

if empresas_eva:
    # Paleta de tons de azul para as barras correspondentes (Marfrig, Klabin, Weg)
    colors_g2 = ['#0f2d59', '#90cdf4', '#3182ce']
    
    fig2, ax2 = plt.subplots(figsize=(8, 6))
    bars = ax2.bar(empresas_eva, valores_eva_milhoes, color=colors_g2, edgecolor='black', linewidth=1.2, width=0.4)
    
    ax2.axhline(0, color='black', linewidth=1.5)
    
    # Rótulo com valores formatados acima das barras
    for bar in bars:
        yval = bar.get_height()
        posicao_texto = yval + 0.05 if yval >= 0 else yval - 0.15
        ax2.text(
            bar.get_x() + bar.get_width()/2, 
            posicao_texto, 
            f'R$ {yval:,.2f} mi'.replace(',', 'X').replace('.', ',').replace('X', '.'), 
            ha='center', va='bottom' if yval >= 0 else 'top', fontweight='bold'
        )
        
    ax2.set_ylabel('EVA Estimado (em Milhões de R$)', fontweight='bold')
    ax2.set_title('Comparação da Criação de Valor (Economic Value Added - EVA)', fontweight='bold', pad=15)
    
    # Ajusta os limites e layout para padrão acadêmico
    ax2.set_ylim(0, max(valores_eva_milhoes) * 1.25)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)
    ax2.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()

# --- Gráfico 3: Evolução Histórica das Participações (Série Temporal) ---
fig3, ax3 = plt.subplots(figsize=(10, 6))
ax3.plot(
    df_merged['periodo'], df_merged['share_carne'], 
    label='Carne Bovina (Marfrig)', color='#0f2d59', linestyle='-', linewidth=2
)
ax3.plot(
    df_merged['periodo'], df_merged['share_celulose'], 
    label='Celulose (Klabin)', color='#90cdf4', linestyle='-', linewidth=2
)
ax3.plot(
    df_merged['periodo'], df_merged['share_maquinas'], 
    label='Máquinas (Weg)', color='#3182ce', linestyle='-', linewidth=2
)

ax3.set_title('Evolução da Participação dos Setores nas Exportações Totais da Indústria de Transformação (2016-2026)', fontweight='bold', pad=15)
ax3.set_xlabel('Período', fontweight='bold')
ax3.set_ylabel('% de Participação', fontweight='bold')
ax3.legend(frameon=True, edgecolor='black')
ax3.grid(True, linestyle='--', alpha=0.5)
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)
plt.tight_layout()
plt.show()