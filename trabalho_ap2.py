import pandas as pd
from pathlib import Path
import time
import requests
import matplotlib.pyplot as plt
import numpy as np

# ==========================================
# --- 1. CONFIGURAÇÕES E APIS -------------
# ==========================================
path = Path(__file__).parent.resolve()

# Mapeamento de Tickers e Premissas
tickers = {
    'Marfrig': 'MBRF3',
    'Klabin': 'KLBN11',
    'Weg': 'WEGE3'
}

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzgwNTcwNzA4LCJpYXQiOjE3Nzc5Nzg3MDgsImp0aSI6IjNmNTBiZWM4OWVkZDQzMWI5NTljZWFkYmFkZTdiNjYyIiwidXNlcl9pZCI6IjExOCJ9.4m2iY0iB32ZKdO6_uZb-H1Cu9zwOXJcenbCHAv-qTFE"
headers = {"Authorization": f"Bearer {token}"}
base_url = "https://laboratoriodefinancas.com/api/v2"

# ==========================================
# --- 2. COLETA DE CÂMBIO DINÂMICO (SGS) ---
# ==========================================
def fetch_bcb_exchange_rates():
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial=01/01/2024&dataFinal=31/12/2025"
    h = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    max_retries = 5
    delay = 10
    print("[SGS BCB] Buscando série histórica do Dólar (diário)...")
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=h, timeout=30)
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data)
                df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
                df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
                df['year'] = df['data'].dt.year
                
                averages = df.groupby('year')['valor'].mean().to_dict()
                print(f"[SGS BCB] Sucesso! Médias anuais calculadas: 2024={averages.get(2024, 0.0):.4f}, 2025={averages.get(2025, 0.0):.4f}")
                return averages
            else:
                print(f"[SGS BCB] Erro {r.status_code}. Tentando novamente em {delay}s...")
                time.sleep(delay)
        except Exception as e:
            print(f"[SGS BCB] Exceção: {e}. Tentando novamente em {delay}s...")
            time.sleep(delay)
    print("[SGS BCB] Falha ao obter dados. Utilizando taxas de fallback (2024=5.3920, 2025=5.5855)")
    return {2024: 5.392016, 2025: 5.585500}

exchange_rates = fetch_bcb_exchange_rates()
CAMBIO_2024 = exchange_rates.get(2024, 5.392016)
CAMBIO_2025 = exchange_rates.get(2025, 5.585500)

# ==========================================
# --- 3. EXPORTAÇÕES E HISTÓRICO COMEXST ---
# ==========================================
def fetch_comex_data(name, filters, details):
    url_query = "https://api-comexstat.mdic.gov.br/general?language=pt"
    payload = {
        "flow": "export",
        "monthDetail": True,
        "period": {
            "from": "2015-01",
            "to": "2025-12"
        },
        "filters": filters,
        "details": details,
        "metrics": ["metricFOB", "metricKG"]
    }
    h = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Content-Type': 'application/json'
    }
    max_retries = 3
    delay = 10
    # Sleep mandatório para respeitar rate limits da API
    time.sleep(delay)
    for attempt in range(max_retries):
        try:
            r = requests.post(url_query, json=payload, headers=h, timeout=30)
            if r.status_code == 200:
                data = r.json().get('data', {}).get('list', [])
                return data
            elif r.status_code == 429:
                time.sleep(delay)
            else:
                time.sleep(delay)
        except Exception:
            time.sleep(delay)
    raise RuntimeError("Rate limit ou timeout no Comex Stat")

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
    grouped = grouped[(grouped['periodo'] >= '2015-01') & (grouped['periodo'] <= '2025-12')]
    
    if is_total:
        result = pd.DataFrame({
            'periodo': grouped['periodo'],
            'vl_fob': grouped['metricFOB']
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

def get_comex_dataframe(name, filters, details, filename, is_celulose=False, is_total=False):
    try:
        raw_data = fetch_comex_data(name, filters, details)
        if raw_data:
            print(f"[{name}] Sucesso ao buscar da API Comex Stat.")
            return process_comex_df(raw_data, is_celulose=is_celulose, is_total=is_total)
    except Exception as e:
        print(f"[{name}] API Indisponível/Rate Limit ({e}). Usando backup local: {filename}")
        
    file_path = path / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo de backup local não encontrado: {filename}")
        
    df_csv = pd.read_csv(file_path, sep=';', decimal=',', encoding='utf-8')
    df_csv['periodo'] = pd.to_datetime(df_csv['periodo'], format='mixed')
    
    # Filtrar período de 10 anos (2015 a 2025)
    df_csv = df_csv[(df_csv['periodo'] >= '2015-01') & (df_csv['periodo'] <= '2025-12')]
    
    if is_total:
        result = pd.DataFrame({
            'periodo': df_csv['periodo'],
            'vl_fob': pd.to_numeric(df_csv['vl_fob'], errors='coerce').fillna(0.0)
        })
    else:
        vl_fob = pd.to_numeric(df_csv['vl_fob'], errors='coerce').fillna(0.0)
        if 'kg_liquido' in df_csv.columns:
            kg_liquido = pd.to_numeric(df_csv['kg_liquido'], errors='coerce').fillna(0.0)
            preco = (vl_fob / kg_liquido).fillna(0.0)
        else:
            kg_liquido = 0.0
            preco = pd.to_numeric(df_csv['preco'], errors='coerce').fillna(0.0)
            
        result = pd.DataFrame({
            'periodo': df_csv['periodo'],
            'vl_fob': vl_fob,
            'kg_liquido': kg_liquido,
            'preco': preco
        })
        
    return result.sort_values('periodo').reset_index(drop=True)

# Buscar e processar os dados históricos da pauta exportadora
print("\n[Comex Stat] Iniciando extração da série histórica de 10 anos (2015-2025)...")
df_carne = get_comex_dataframe("Carne Bovina", [{"filter": "heading", "values": ["0201", "0202"]}], ["heading"], "carne_bovina.csv")
df_celulose = get_comex_dataframe("Celulose", [{"filter": "chapter", "values": ["47"]}], ["heading"], "celulose.csv", is_celulose=True)
df_maquinas = get_comex_dataframe("Máquinas (Weg)", [{"filter": "heading", "values": ["8501"]}], ["heading"], "maquinas.csv")
df_total = get_comex_dataframe("Total Indústria", [{"filter": "ISICSection", "values": ["C"]}], ["ISICSection"], "industria_transformacao.csv", is_total=True)

# Renomear colunas para evitar conflitos no merge
df_carne = df_carne.rename(columns={'vl_fob': 'vl_fob_carne', 'kg_liquido': 'kg_liquido_carne', 'preco': 'preco_carne'})
df_celulose = df_celulose.rename(columns={'vl_fob': 'vl_fob_celulose', 'kg_liquido': 'kg_liquido_celulose', 'preco': 'preco_celulose'})
df_maquinas = df_maquinas.rename(columns={'vl_fob': 'vl_fob_maquinas', 'kg_liquido': 'kg_liquido_maquinas', 'preco': 'preco_maquinas'})
df_total = df_total.rename(columns={'vl_fob': 'vl_fob_total'})

# Merge sequencial
df_merged = pd.merge(df_carne, df_celulose, on='periodo', how='inner')
df_merged = pd.merge(df_merged, df_maquinas, on='periodo', how='inner')
df_merged = pd.merge(df_merged, df_total, on='periodo', how='inner')

# Cálculo das participações históricas (%)
df_merged['share_carne'] = (df_merged['vl_fob_carne'] / df_merged['vl_fob_total']) * 100
df_merged['share_celulose'] = (df_merged['vl_fob_celulose'] / df_merged['vl_fob_total']) * 100
df_merged['share_maquinas'] = (df_merged['vl_fob_maquinas'] / df_merged['vl_fob_total']) * 100

# ==========================================
# --- 4. MOTOR FINANCEIRO E INDICADORES ---
# ==========================================
def get_value(df, conta):
    res = df[df['conta'] == conta]
    if res.empty:
        res = df[df['conta'].str.replace('.', '', regex=False) == conta.replace('.', '', regex=False)]
    if not res.empty:
        val = res.iloc[0]['valor']
        return float(val) if val is not None else 0.0
    return 0.0

def calcular_indicadores_financeiros(ticker, year):
    periodo = f"{year}4T"
    resp = requests.get(f"{base_url}/bolsa/balanco", headers=headers, params={"ticker": ticker, "ano_tri": periodo})
    if resp.status_code != 200 or len(resp.json()) == 0:
        # Fallback para o 3T no caso de atraso na publicação do balanço anual
        if year == 2025:
            periodo = "20253T"
            resp = requests.get(f"{base_url}/bolsa/balanco", headers=headers, params={"ticker": ticker, "ano_tri": periodo})
            if resp.status_code != 200 or len(resp.json()) == 0:
                return None
        else:
            return None
            
    data = resp.json()[0]
    df = pd.DataFrame(data['balanco'])
    
    # 1. Balanço Patrimonial (BP)
    ativo_total = get_value(df, '1')
    pl = get_value(df, '2.03')
    pc = get_value(df, '2.01')
    pnc = get_value(df, '2.02')
    
    # 2. Demonstração de Resultado do Exercício (DRE)
    receita = get_value(df, '3.01')
    lucro_bruto = get_value(df, '3.03')
    ebit = get_value(df, '3.05')
    lucro_liquido = get_value(df, '3.11')
    
    # Depreciação e Amortização (obtido da DVA ou DFC para totalizadores de depreciação)
    depre = abs(get_value(df, '7.04'))
    if depre == 0.0:
        depre = abs(get_value(df, '6.01.01.02'))
        
    ebitda = ebit + depre
    
    # NOPAT (Fórmula do Excel: EBITDA - Imposto de Renda Corrente)
    ir_corrente = get_value(df, '3.08.01')
    nopat = ebitda - ir_corrente
    
    # Investimento (Ativo Total)
    passivo_oneroso = pc + pnc
    investimento = passivo_oneroso + pl # Equivalente ao Ativo Total
    
    # Margens
    margem_bruta = lucro_bruto / receita if receita != 0 else 0
    margem_ebitda = ebitda / receita if receita != 0 else 0
    margem_ebit = ebit / receita if receita != 0 else 0
    margem_nopat = nopat / receita if receita != 0 else 0
    margem_liquida = lucro_liquido / receita if receita != 0 else 0
    
    # ROI & ROE & GAF
    roi = nopat / investimento if investimento != 0 else 0
    roe = lucro_liquido / pl if pl != 0 else 0
    gaf = roe / roi if roi != 0 else 0
    
    # CMPC (WACC)
    w1 = passivo_oneroso / investimento if investimento != 0 else 0
    w2 = pl / investimento if investimento != 0 else 0
    
    # Alíquota Efetiva de IR/CSLL
    lair = get_value(df, '3.07')
    ir_total = get_value(df, '3.08')
    ratio = ir_total / lair if lair != 0 else 0.34
    t = 0.34 if (ratio > 1.0 or ratio < 0.0) else ratio
    
    # Despesa Financeira Líquida e Custo da Dívida
    despesa_financeira = abs(get_value(df, '3.06.02'))
    dfl = despesa_financeira * (1.0 - t)
    ki = dfl / passivo_oneroso if passivo_oneroso != 0 else 0
    ke = 0.16
    
    cmpc = (w1 * ki) + (w2 * ke)
    
    # EVA
    eva = (roi - cmpc) * investimento
    
    return {
        "receita": receita,
        "lucro_bruto": lucro_bruto,
        "ebitda": ebitda,
        "ebit": ebit,
        "nopat": nopat,
        "lucro_liquido": lucro_liquido,
        "investimento": investimento,
        "margem_bruta": margem_bruta,
        "margem_ebitda": margem_ebitda,
        "margem_ebit": margem_ebit,
        "margem_nopat": margem_nopat,
        "margem_liquida": margem_liquida,
        "roi": roi,
        "roe": roe,
        "gaf": gaf,
        "cmpc": cmpc,
        "eva": eva
    }

financial_results = {}
for name, ticker in tickers.items():
    financial_results[name] = {}
    for year in [2024, 2025]:
        financial_results[name][year] = calcular_indicadores_financeiros(ticker, year)

# ==========================================
# --- 5. EXIBIÇÃO DE RESULTADOS (TERMINAL) --
# ==========================================
print("\n" + "="*80)
print("             INDICADORES CORPORATIVOS E DRE GERENCIAL (2024 vs 2025)            ")
print("="*80)

for name in tickers.keys():
    print(f"\n>>> {name.upper()} ({tickers[name]})")
    for year in [2024, 2025]:
        res = financial_results[name].get(year)
        if not res:
            print(f"  [{year}] Dados não disponíveis.")
            continue
            
        print(f"\n  Ano de Referência: {year}")
        print(f"  -------------------------------------------------------------")
        print(f"  DRE GERENCIAL:")
        print(f"    Receita Líquida:                 R$ {res['receita']:18,.2f}")
        print(f"    Lucro Bruto:                     R$ {res['lucro_bruto']:18,.2f}")
        print(f"    EBIT:                            R$ {res['ebit']:18,.2f}")
        print(f"    EBITDA:                          R$ {res['ebitda']:18,.2f}")
        print(f"    NOPAT:                           R$ {res['nopat']:18,.2f}")
        print(f"    Lucro Líquido:                   R$ {res['lucro_liquido']:18,.2f}")
        print(f"  INDICADORES FINANCEIROS:")
        print(f"    Margem Bruta:                    {res['margem_bruta']*100:18.4f}%")
        print(f"    Margem EBITDA:                   {res['margem_ebitda']*100:18.4f}%")
        print(f"    Margem EBIT:                     {res['margem_ebit']*100:18.4f}%")
        print(f"    Margem NOPAT:                    {res['margem_nopat']*100:18.4f}%")
        print(f"    Margem Líquida:                  {res['margem_liquida']*100:18.4f}%")
        print(f"    Retorno sobre Investimento (ROI):{res['roi']*100:18.4f}%")
        print(f"    Retorno sobre o Equity (ROE):    {res['roe']*100:18.4f}%")
        print(f"    Grau de Alavancagem Fin. (GAF):  {res['gaf']:18.4f}x")
        print(f"    Custo Médio de Capital (CMPC):   {res['cmpc']*100:18.4f}%")
        print(f"    Valor Econômico Adicionado (EVA):R$ {res['eva']:18,.2f}")
    print("="*80)

print("\n" + "="*80)
print("               ANÁLISE HISTÓRICA DE EXPORTAÇÕES (2015-2025)             ")
print("="*80)
print("  Média de Participação Histórica na Indústria de Transformação:")
print(f"    Carne Bovina (Marfrig):           {df_merged['share_carne'].mean():.4f}%")
print(f"    Celulose (Klabin):                {df_merged['share_celulose'].mean():.4f}%")
print(f"    Máquinas (Weg):                   {df_merged['share_maquinas'].mean():.4f}%")
print("="*80)

# ==========================================
# --- 6. VISUALIZAÇÃO GRÁFICA --------------
# ==========================================
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 10
plt.rcParams['axes.edgecolor'] = 'black'
plt.rcParams['axes.linewidth'] = 1.0

# --- Gráfico A: Comparação de EVA 2024 vs 2025 ---
companies = list(tickers.keys())
eva_2024 = [financial_results[c][2024]['eva'] / 1e6 for c in companies]
eva_2025 = [financial_results[c][2025]['eva'] / 1e6 for c in companies]

x = np.arange(len(companies))
width = 0.35

fig, ax = plt.subplots(figsize=(8, 6))
rects1 = ax.bar(x - width/2, eva_2024, width, label='2024', color='#3182ce', edgecolor='black', linewidth=1.2)
rects2 = ax.bar(x + width/2, eva_2025, width, label='2025', color='#0f2d59', edgecolor='black', linewidth=1.2)

ax.axhline(0, color='black', linewidth=1.2)
ax.set_ylabel('EVA (em Milhões de R$)', fontweight='bold')
ax.set_title('Comparação de EVA por Companhia (2024 vs 2025)', fontweight='bold', pad=15)
ax.set_xticks(x)
ax.set_xticklabels(companies, fontweight='bold')
ax.legend(frameon=True, edgecolor='black')
ax.grid(axis='y', linestyle='--', alpha=0.5)

# Remover linhas superior e direita
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Rótulos automáticos
all_evas = eva_2024 + eva_2025
max_val = max(all_evas)
min_val = min(all_evas)
y_range = max_val - min_val
offset = 0.02 * y_range

ax.set_ylim(min_val - 0.3 * y_range, max_val + 0.15 * y_range)


def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        pos = height + offset if height >= 0 else height - offset
        va = 'bottom' if height >= 0 else 'top'
        ax.text(rect.get_x() + rect.get_width()/2., pos,
                f'R$ {height:,.2f} M'.replace(',', 'X').replace('.', ',').replace('X', '.'),
                ha='center', va=va, fontsize=8, fontweight='bold')

autolabel(rects1)
autolabel(rects2)

plt.tight_layout()

# --- Gráfico B: Série Temporal de Exportações ---
fig2, ax2 = plt.subplots(figsize=(10, 6))
ax2.plot(df_merged['periodo'], df_merged['share_carne'], label='Carne Bovina (Marfrig)', color='#0f2d59', linewidth=2)
ax2.plot(df_merged['periodo'], df_merged['share_celulose'], label='Celulose (Klabin)', color='#90cdf4', linewidth=2)
ax2.plot(df_merged['periodo'], df_merged['share_maquinas'], label='Máquinas (Weg)', color='#3182ce', linewidth=2)

ax2.set_title('Participação Histórica nas Exportações da Indústria de Transformação (2015-2025)', fontweight='bold', pad=15)
ax2.set_xlabel('Período', fontweight='bold')
ax2.set_ylabel('% de Participação', fontweight='bold')

# Configurar limites e ticks do eixo X para focar exatamente entre 2015 e 2025
ax2.set_xlim(pd.Timestamp('2015-01-01'), pd.Timestamp('2025-12-01'))
ticks = pd.to_datetime(['2015-01-01', '2017-01-01', '2019-01-01', '2021-01-01', '2023-01-01', '2025-01-01'])
ax2.set_xticks(ticks)
ax2.set_xticklabels(['2015', '2017', '2019', '2021', '2023', '2025'])

ax2.legend(frameon=True, edgecolor='black')
ax2.grid(True, linestyle='--', alpha=0.5)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
plt.tight_layout()

# Exibir os gráficos na tela
plt.show()