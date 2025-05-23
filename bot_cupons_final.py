import time
import hmac
import hashlib
import json
import requests
import schedule
import os
from telegram import Bot

# --- Configurações do Telegram via variáveis de ambiente ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
bot = Bot(token=TELEGRAM_TOKEN)

# --- Configurações da Shopee Partners ---
partner_id = 18389690042
partner_key = "4YRPD6OLPJXSEERAW66WY6KLIOJJA5NZ"
base_url = "https://partner.shopee.com.br"
path = "/api/v2/product/search"

def gerar_assinatura(path, timestamp):
    base_string = f"{partner_id}{path}{timestamp}"
    return hmac.new(
        partner_key.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

def buscar_produtos_shopee():
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)

    url = f"{base_url}{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"
    payload = {
        "keyword": "oferta",
        "page_size": 3
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    mensagens = []
    for item in data["result_list"]["item_list"]:
    nome = item.get("item_basic", {}).get("name", "Produto")
    itemid = item.get("item_basic", {}).get("itemid")
    link = f"https://shope.ee/{itemid}"
    mensagens.append(f"🛍️ {nome}\n🔗 {link}")


    return mensagens

def enviar_cupons():
    mensagens = []

    # Mercado Livre com etiqueta 'migu'
    link_ml = "https://www.mercadolivre.com.br/ofertas?matt_tool=afiliados&tag=migu"
    mensagens.append(f"🔥 Oferta Mercado Livre: {link_ml}")

    try:
        mensagens += buscar_produtos_shopee()
    except Exception as e:
        mensagens.append("Erro ao buscar cupons da Shopee: " + str(e))

    mensagens.append("📦 Promo Amazon: https://amazon.com.br/exemplo")
    mensagens.append("🌍 Oferta AliExpress: https://aliexpress.com/exemplo")

    for mensagem in mensagens:
        bot.send_message(chat_id=GROUP_ID, text=mensagem)

schedule.every(15).minutes.do(enviar_cupons)

print("Bot de cupons rodando...")
while True:
    schedule.run_pending()
    time.sleep(1)
