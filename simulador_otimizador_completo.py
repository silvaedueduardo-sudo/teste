
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
import random
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.utils.dataframe import dataframe_to_rows

warnings.filterwarnings("ignore")

# === CONFIGURAÇÕES ===
MOEDAS = ["BTCUSDT"]
DATA_INICIO = "2025-03-05"
DATA_FIM = "2025-03-15"
VALOR_INICIAL = 1000.0
NUM_SIMULACOES = 10

RSI_COMPRA_RANGE = (20, 45)
RSI_VENDA_RANGE = (55, 85)
PASTA_CSV = Path("dados_binance")

TAXA_TRANSACAO = 0.001
TAXA_IMPOSTO = 0.28
RESERVA_PROVISAO = 0.1

# === ESTRATÉGIAS ===
def rsi_basico(rsi_c, rsi_v):
    def estrategia(linha, estado):
        rsi = linha["RSI"]
        if rsi < rsi_c:
            return "compra", f"RSI < {rsi_c}", estado
        elif rsi > rsi_v:
            return "venda", f"RSI > {rsi_v}", estado
        return None, "", estado
    return estrategia

def rsi_cruzamento(linha, estado):
    rsi = linha["RSI"]
    h = estado.get("rsi", [])
    h.append(rsi)
    estado["rsi"] = h
    if len(h) < 2:
        return None, "", estado
    ant, atual = h[-2], h[-1]
    if ant < 30 and atual >= 30:
        return "compra", "RSI cruzou 30 ↑", estado
    elif ant > 70 and atual <= 70:
        return "venda", "RSI cruzou 70 ↓", estado
    return None, "", estado

def sma_cruzamento(linha, estado):
    preco = linha["close"]
    h = estado.get("precos", [])
    h.append(preco)
    estado["precos"] = h
    if len(h) < 15:
        return None, "", estado
    sma5 = pd.Series(h[-5:]).mean()
    sma15 = pd.Series(h[-15:]).mean()
    if sma5 > sma15:
        return "compra", "SMA5 > SMA15", estado
    elif sma5 < sma15:
        return "venda", "SMA5 < SMA15", estado
    return None, "", estado

def reversao(linha, estado):
    preco = linha["close"]
    h = estado.get("precos", [])
    h.append(preco)
    estado["precos"] = h
    if len(h) < 4:
        return None, "", estado
    if h[-1] < h[-2] < h[-3]:
        return "compra", "3 quedas seguidas", estado
    elif h[-1] > h[-2] > h[-3]:
        return "venda", "3 subidas seguidas", estado
    return None, "", estado

def combinada(linha, estado):
    preco = linha["close"]
    rsi = linha["RSI"]
    h = estado.get("precos", [])
    h.append(preco)
    estado["precos"] = h
    if len(h) < 10:
        return None, "", estado
    sma10 = pd.Series(h[-10:]).mean()
    if rsi < 35 and preco < sma10:
        return "compra", "RSI < 35 e preco < SMA10", estado
    elif rsi > 65 and preco > sma10:
        return "venda", "RSI > 65 e preco > SMA10", estado
    return None, "", estado

# === SIMULAÇÃO ===
def simular(df, nome_estrategia, func, take_profit_pct=0.05, stop_loss_pct=0.03):
    transacoes = []
    saldo_usdt = VALOR_INICIAL
    saldo_moeda = 0.0
    provisao = 0.0
    em_posicao = False
    estado = {}
    custo_da_compra = 0.0

    for _, linha in df.iterrows():
        preco = linha["close"]
        tempo = linha["timestamp"]
        decisao, motivo, estado = func(linha, estado)

        # Verificar SL/TP mesmo que a estratégia não tenha sinalizado venda
        if em_posicao:
            valor_atual = saldo_moeda * preco * (1 - TAXA_TRANSACAO)
            lucro_bruto = valor_atual - custo_da_compra

            if lucro_bruto >= custo_da_compra * take_profit_pct:
                decisao = "venda"
                motivo = f"Take Profit ({take_profit_pct*100:.1f}%)"
            elif lucro_bruto <= -custo_da_compra * stop_loss_pct:
                decisao = "venda"
                motivo = f"Stop Loss ({stop_loss_pct*100:.1f}%)"

        if decisao == "compra" and not em_posicao:
            custo_da_compra = saldo_usdt
            saldo_moeda = (saldo_usdt * (1 - TAXA_TRANSACAO)) / preco
            saldo_usdt = 0
            em_posicao = True
            transacoes.append((tempo, "COMPRA", preco, saldo_moeda, saldo_usdt, "", "", motivo))

        elif decisao == "venda" and em_posicao:
            valor_bruto = saldo_moeda * preco
            valor_liquido = valor_bruto * (1 - TAXA_TRANSACAO)
            lucro_bruto = valor_liquido - custo_da_compra

            if lucro_bruto > 0:
                imposto = lucro_bruto * TAXA_IMPOSTO
                reserva = (lucro_bruto - imposto) * RESERVA_PROVISAO
            else:
                imposto = 0
                reserva = 0

            saldo_usdt = valor_liquido - imposto - reserva
            provisao += reserva
            saldo_moeda = 0
            em_posicao = False

            transacoes.append((tempo, "VENDA", preco, saldo_moeda, saldo_usdt, imposto, reserva, motivo))

    preco_final = df.iloc[-1]["close"]
    valor_liquido_final = saldo_usdt + saldo_moeda * preco_final
    valor_total = valor_liquido_final + provisao
    lucro = valor_total - VALOR_INICIAL
    rentabilidade = (lucro / VALOR_INICIAL) * 100

    df_trans = pd.DataFrame(transacoes, columns=[
        "timestamp", "tipo", "preco", "moeda", "usdt", "imposto", "provisao", "motivo"
    ])
    resumo = {
        "Estratégia": nome_estrategia,
        "Saldo Final (sem provisão)": round(valor_liquido_final, 2),
        "Provisão Acumulada": round(provisao, 2),
        "Valor Total (com provisão)": round(valor_total, 2),
        "Lucro": round(lucro, 2),
        "Rentabilidade (%)": round(rentabilidade, 2),
        "Transações": len(df_trans)
    }
    return df_trans, resumo

# === EXECUTAR PARA CADA MOEDA ===
TP = 0.05  # Take Profit 5%
SL = 0.03  # Stop Loss 3%

for moeda in MOEDAS:
    caminho = PASTA_CSV / f"{moeda}.csv"
    if not caminho.exists():
        print(f"⚠️ CSV não encontrado para {moeda}")
        continue

    df_raw = pd.read_csv(caminho, parse_dates=["timestamp"])
    df_raw = df_raw[(df_raw["timestamp"] >= DATA_INICIO) & (df_raw["timestamp"] <= DATA_FIM)].copy()
    df_raw.reset_index(drop=True, inplace=True)
    if df_raw.empty:
        print(f"⚠️ Sem dados para {moeda}")
        continue

    print(f"🔄 Simulando {moeda}...")

    sheets = {}
    resumos = []

    # RSI Básico - Monte Carlo
    for i in range(NUM_SIMULACOES):
        rsi_c = random.randint(*RSI_COMPRA_RANGE)
        rsi_v = random.randint(*RSI_VENDA_RANGE)
        if rsi_c >= rsi_v:
            continue
        nome = f"RSI_MC_{rsi_c}_{rsi_v}"
        func = rsi_basico(rsi_c, rsi_v)
        df_trans, resumo = simular(df_raw.copy(), nome, func, TP, SL)
        sheets[nome[:31]] = df_trans
        resumo.update({
            "RSI_COMPRA": rsi_c,
            "RSI_VENDA": rsi_v,
            "Moeda": moeda
        })
        resumos.append(resumo)

    # RSI Cruzamento com variação de limites
    for low, high in [(25, 70), (30, 65), (35, 60)]:
        def rsi_cruz_var(linha, estado, l=low, h=high):
            rsi = linha["RSI"]
            hlist = estado.get("rsi", [])
            hlist.append(rsi)
            estado["rsi"] = hlist
            if len(hlist) < 2:
                return None, "", estado
            ant, atual = hlist[-2], hlist[-1]
            if ant < l and atual >= l:
                return "compra", f"RSI cruzou {l} ↑", estado
            elif ant > h and atual <= h:
                return "venda", f"RSI cruzou {h} ↓", estado
            return None, "", estado

        nome = f"RSI_Cruz_{low}_{high}"
        df_trans, resumo = simular(df_raw.copy(), nome, rsi_cruz_var, TP, SL)
        sheets[nome[:31]] = df_trans
        resumo.update({"RSI_COMPRA": low, "RSI_VENDA": high, "Moeda": moeda})
        resumos.append(resumo)

    # SMA Cruzamento com variações
    for sma_c, sma_l in [(3, 10), (5, 15), (8, 21)]:
        def sma_var(linha, estado, sc=sma_c, sl=sma_l):
            preco = linha["close"]
            h = estado.get("precos", [])
            h.append(preco)
            estado["precos"] = h
            if len(h) < sl:
                return None, "", estado
            sma_c_val = pd.Series(h[-sc:]).mean()
            sma_l_val = pd.Series(h[-sl:]).mean()
            if sma_c_val > sma_l_val:
                return "compra", f"SMA{sc} > SMA{sl}", estado
            elif sma_c_val < sma_l_val:
                return "venda", f"SMA{sc} < SMA{sl}", estado
            return None, "", estado

        nome = f"SMA_{sma_c}_{sma_l}"
        df_trans, resumo = simular(df_raw.copy(), nome, sma_var, TP, SL)
        sheets[nome[:31]] = df_trans
        resumo.update({"RSI_COMPRA": "", "RSI_VENDA": "", "Moeda": moeda})
        resumos.append(resumo)

    # Reversão: 2, 3, 4 candles
    for n in [2, 3, 4]:
        def reversao_n(linha, estado, n_candles=n):
            preco = linha["close"]
            h = estado.get("precos", [])
            h.append(preco)
            estado["precos"] = h
            if len(h) < n_candles + 1:
                return None, "", estado
            if all(h[-i] < h[-i-1] for i in range(1, n_candles+1)):
                return "compra", f"{n_candles} quedas seguidas", estado
            elif all(h[-i] > h[-i-1] for i in range(1, n_candles+1)):
                return "venda", f"{n_candles} subidas seguidas", estado
            return None, "", estado

        nome = f"Reversao_{n}"
        df_trans, resumo = simular(df_raw.copy(), nome, reversao_n, TP, SL)
        sheets[nome[:31]] = df_trans
        resumo.update({"RSI_COMPRA": "", "RSI_VENDA": "", "Moeda": moeda})
        resumos.append(resumo)

    # Combinada com variações
    for rsi_c, rsi_v, sma_p in [(30, 70, 10), (35, 65, 15), (40, 60, 20)]:
        def combinada_var(linha, estado, rc=rsi_c, rv=rsi_v, sp=sma_p):
            preco = linha["close"]
            rsi = linha["RSI"]
            h = estado.get("precos", [])
            h.append(preco)
            estado["precos"] = h
            if len(h) < sp:
                return None, "", estado
            sma_val = pd.Series(h[-sp:]).mean()
            if rsi < rc and preco < sma_val:
                return "compra", f"RSI<{rc} & close<SMA{sp}", estado
            elif rsi > rv and preco > sma_val:
                return "venda", f"RSI>{rv} & close>SMA{sp}", estado
            return None, "", estado

        nome = f"Comb_{rsi_c}_{rsi_v}_SMA{sma_p}"
        df_trans, resumo = simular(df_raw.copy(), nome, combinada_var, TP, SL)
        sheets[nome[:31]] = df_trans
        resumo.update({"RSI_COMPRA": rsi_c, "RSI_VENDA": rsi_v, "Moeda": moeda})
        resumos.append(resumo)

    # Excel com ranking
    EXCEL_SAIDA = f"resultados_otimizacao_ranking_{moeda}.xlsx"
    with pd.ExcelWriter(EXCEL_SAIDA, engine="openpyxl") as writer:
        df_resumos = pd.DataFrame(resumos)
        df_resumos.to_excel(writer, sheet_name="Resumo", index=False)

        df_ranking = df_resumos.copy().sort_values(by="Valor Total (com provisão)", ascending=False)
        df_ranking.insert(0, "Ranking", range(1, len(df_ranking) + 1))
        df_ranking.to_excel(writer, sheet_name="Ranking", index=False)

        for nome, df_aba in sheets.items():
            df_aba.to_excel(writer, sheet_name=nome[:31], index=False)

print("✅ Simulação final com TP/SL e variação de estratégias concluída.")
