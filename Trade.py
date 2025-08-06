import requests
import time
from datetime import datetime
import csv
from pathlib import Path

# === PARÂMETROS ===
INTERVALO_SEGUNDOS = 60  # A cada 60 segundos (podes alterar)
MARGEM_LUCRO = 0.005      # 0.5% de lucro mínimo para vender
HISTORICO_LIMITE = 20     # Nº de preços a manter para detetar mínimos

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

def correr_bot():
    while True:
        try:
            preco = obter_preco_bitcoin()
            historico_precos.append(preco)
            if len(historico_precos) > HISTORICO_LIMITE:
                historico_precos.pop(0)

            log(f"Preço atual BTC: {preco:.2f} €")

            # VERIFICAÇÃO DE COMPRA
            if not estado["comprado"]:
                if len(historico_precos) >= 3:
                    if historico_precos[-2] < historico_precos[-3] and historico_precos[-2] < historico_precos[-1]:
                        estado["comprado"] = True
                        estado["preco_compra"] = historico_precos[-2]
                        log(f"🔵 COMPRA SIMULADA a {estado['preco_compra']:.2f} €")

            # VERIFICAÇÃO DE VENDA
            else:
                preco_compra = estado["preco_compra"]
                if preco >= preco_compra * (1 + MARGEM_LUCRO):
                    lucro_bruto = preco - preco_compra
                    lucro_liquido = lucro_bruto * (1 - 0.28 - 0.10)

                    log(f"🟢 VENDA SIMULADA a {preco:.2f} € | Lucro bruto: {lucro_bruto:.2f} €, líquido: {lucro_liquido:.2f} €")

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
            log(f"⚠️ Erro: {e}")

        time.sleep(INTERVALO_SEGUNDOS)

# === EXECUÇÃO ===
if __name__ == "__main__":
    log("📈 BOT INICIADO")
    correr_bot()
