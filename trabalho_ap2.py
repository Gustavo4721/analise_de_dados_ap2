import pandas as pd
import os
import matplotlib.pyplot as plt

# --- 1. CONFIGURAÇÕES DE DIRETÓRIO ---
path = '/Users/gustavomendes/Faculdade/3° Semestre/Programação para Análise de Dados/trabalho_ap2'

# --- 2. PARÂMETROS ECONÔMICOS (REFERÊNCIA 2025) ---
# Taxa de câmbio média anual estimada para 2025
CAMBIO_2025 = 5.10

# Estimativas de Receita de Exportação (em R$ Bilhões) apenas de solo brasileiro
receitas_br_brl = {
    'Klabin': 11.2,  
    'Marfrig': 48.5, 
    'Weg': 23.2      
}

# --- 3. CARREGAMENTO E LIMPEZA (COMEX STAT) ---
file_path = os.path.join(path, 'produtos_industria_transformacao.csv')
df_sh4 = pd.read_csv(file_path, sep=';', decimal=',', encoding='utf-8')

# Conversão da coluna de valor para numérico
col_valor_usd = '2025 - Valor US$ FOB'
df_sh4[col_valor_usd] = pd.to_numeric(df_sh4[col_valor_usd], errors='coerce').fillna(0)

# Valor Total da Indústria de Transformação em 2025 (Denominador)
total_it_usd = df_sh4[col_valor_usd].sum()

# --- 4. CÁLCULO DO ÍNDICE HERFINDAHL-HIRSCHMAN (HHI) ---
# Calcula o share (s_i) de cada setor SH4 na Indústria de Transformação
df_sh4['share'] = df_sh4[col_valor_usd] / total_it_usd
# HHI = Soma dos quadrados das participações
hhi_pauta = (df_sh4['share'] ** 2).sum()

# --- 5. ANÁLISE DE PARTICIPAÇÃO CORPORATIVA ---
# Criando a tabela de empresas com os nomes das colunas definidos
df_empresas = pd.DataFrame(list(receitas_br_brl.items()), columns=['Empresa', 'Receita_BRL'])

# Converter R$ Bilhões para US$ Unidades para comparação com o MDIC
df_empresas['Receita_USD'] = (df_empresas['Receita_BRL'] * 1e9) / CAMBIO_2025

# Cálculo da Participação na Indústria de Transformação (PE_IT %)
df_empresas['Participacao_IT_%'] = (df_empresas['Receita_USD'] / total_it_usd) * 100

# --- 6. EXIBIÇÃO DOS RESULTADOS ---
print("--- RESULTADOS DA PESQUISA (2025) ---")
print(f"Exportação Total da Indústria de Transformação: US$ {total_it_usd/1e9:.2f} Bilhões")
print(f"Índice de Concentração (HHI) da Pauta: {hhi_pauta:.4f}")
print("\n--- Participação das Empresas Líderes ---")
print(df_empresas)

# --- 7. VISUALIZAÇÃO ---
plt.figure(figsize=(10, 6))
plt.bar(df_empresas['Empresa'], df_empresas['Participacao_IT_%'], color=['#004a8d', '#009541', '#6d6e71'])
plt.title('Participação no Volume Total de Exportações da Indústria de Transformação (2025)')
plt.ylabel('% de Participação')
plt.grid(axis='y', linestyle='--', alpha=0.6)
plt.show()