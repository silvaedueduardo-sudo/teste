import requests
import time
from datetime import datetime
import csv
from pathlib import Path

# === PARÂMETROS ===
INTERVALO_SEGUNDOS = 60  # A cada 60 segundos (podes alterar)
MARGEM_LUCRO = 0.005      # 0.5% de lucro mínimo para vender
HISTORICO_LIMITE = 100    # Nº de preços a manter para indicadores

# === ESTADO ===
historico_precos = []
estado = {"comprado": False, "preco_compra": 0.0}

# === FICHEIROS ===
csv_path = Path("registo_transacoes_inteligente.csv")
log_path = Path("bot_fundo_local.log")

headers_csv = [
    "Data/Hora", "Tipo de operação", "Preço de compra (€)", "Preço de venda (€)",
    "Lucro bruto (€)", "Lucro líquido (€)"
]

def log(msg):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{agora}] {msg}"
    print(linha)
    with open(log_path, "a") as f:
        f.write(linha + "\n")

def obter_preco_bitcoin():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": "bitcoin", "vs_currencies": "eur"}
    response = requests.get(url, params=params, timeout=10)
    return response.json()["bitcoin"]["eur"]

def escrever_csv(linha):
    escrever_cabecalho = not csv_path.exists()
    with open(csv_path, "a", newline="") as file:
        writer = csv.writer(file)
        if escrever_cabecalho:
            writer.writerow(headers_csv)
        writer.writerow(linha)


def media_movel_simples(dados, periodo):
    if not dados:
        return 0.0
    if len(dados) < periodo:
        return sum(dados) / len(dados)
    return sum(dados[-periodo:]) / periodo


def media_movel_exponencial(dados, periodo):
    if len(dados) < periodo:
        return media_movel_simples(dados, periodo)
    k = 2 / (periodo + 1)
    ema = media_movel_simples(dados[:periodo], periodo)
    for preco in dados[periodo:]:
        ema = preco * k + ema * (1 - k)
    return ema


def calcular_rsi(dados, periodo=14):
    if len(dados) < periodo + 1:
        return 50.0
    ganhos = 0.0
    perdas = 0.0
    for i in range(len(dados) - periodo, len(dados)):
        delta = dados[i] - dados[i - 1]
        if delta >= 0:
            ganhos += delta
        else:
            perdas -= delta
    media_ganho = ganhos / periodo
    media_perda = perdas / periodo
    if media_perda == 0:
        return 100.0
    rs = media_ganho / media_perda
    return 100 - (100 / (1 + rs))

def correr_bot():
    while True:
        try:
            preco = obter_preco_bitcoin()
            historico_precos.append(preco)
            if len(historico_precos) > HISTORICO_LIMITE:
                historico_precos.pop(0)

            log(f"Preço atual BTC: {preco:.2f} €")

            ema_curta = ema_longa = rsi = None
            if len(historico_precos) >= 26:
                ema_curta = media_movel_exponencial(historico_precos, 12)
                ema_longa = media_movel_exponencial(historico_precos, 26)
                rsi = calcular_rsi(historico_precos, 14)
                log(f"EMA12: {ema_curta:.2f} | EMA26: {ema_longa:.2f} | RSI14: {rsi:.2f}")

            # VERIFICAÇÃO DE COMPRA
            if not estado["comprado"]:
                if len(historico_precos) >= 26:
                    if (
                        historico_precos[-2] < historico_precos[-3]
                        and historico_precos[-2] < historico_precos[-1]
                        and ema_curta > ema_longa
                        and rsi < 30
                    ):
                        estado["comprado"] = True
                        estado["preco_compra"] = historico_precos[-2]
                        log(
                            f"COMPRA SIMULADA a {estado['preco_compra']:.2f} € | EMA12: {ema_curta:.2f}, EMA26: {ema_longa:.2f}, RSI14: {rsi:.2f}"
                        )

            # VERIFICAÇÃO DE VENDA
            else:
                preco_compra = estado["preco_compra"]
                condicao_venda = preco >= preco_compra * (1 + MARGEM_LUCRO)
                if rsi is not None and (rsi > 70 or ema_curta < ema_longa):
                    condicao_venda = True
                if condicao_venda:
                    lucro_bruto = preco - preco_compra
                    lucro_liquido = lucro_bruto * (1 - 0.28 - 0.10)

                    info_metricas = (
                        f" | EMA12: {ema_curta:.2f}, EMA26: {ema_longa:.2f}, RSI14: {rsi:.2f}"
                        if rsi is not None
                        else ""
                    )
                    log(
                        f"VENDA SIMULADA a {preco:.2f} € | Lucro bruto: {lucro_bruto:.2f} €, líquido: {lucro_liquido:.2f} €{info_metricas}"
                    )

                    escrever_csv([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "venda",
                        round(preco_compra, 2),
                        round(preco, 2),
                        round(lucro_bruto, 2),
                        round(lucro_liquido, 2)
                    ])

                    estado["comprado"] = False
                    estado["preco_compra"] = 0.0

        except Exception as e:
            log(f"Erro: {e}")

        time.sleep(INTERVALO_SEGUNDOS)

# === EXECUÇÃO ===
if __name__ == "__main__":
    log("BOT INICIADO")
    correr_bot()
