import os
import time
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# --- Configurações ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
SHOPEE_AFIL_LINK = "https://s.shopee.com.br/30bjw3P88I"
ML_AFIL_LINK = "https://mercadolivre.com/sec/1XMEDg1"
INTERVALO_MINUTOS = 10

bot = Bot(token=TELEGRAM_TOKEN)
logging.basicConfig(level=logging.INFO)

ENVIADOS_CACHE = set()

# --- Scraping do site Pacheco Ofertas ---
def buscar_links_ofertas():
    url = "https://www.divulgadorinteligente.com/pachecoofertas"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        produtos = []

        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            texto = link.get_text(strip=True)

            if "shopee" in href.lower():
                produtos.append({
                    "nome": texto or "Oferta Shopee",
                    "link": SHOPEE_AFIL_LINK,
                    "origem": "Shopee"
                })
            elif "mercadolivre" in href.lower():
                produtos.append({
                    "nome": texto or "Oferta Mercado Livre",
                    "link": ML_AFIL_LINK,
                    "origem": "Mercado Livre"
                })
        return produtos
    except Exception as e:
        logging.error(f"Erro ao buscar ofertas: {e}")
        return []

# --- Enviar para o Telegram ---
async def enviar_telegram(prod):
    if prod['nome'] in ENVIADOS_CACHE:
        return

    legenda = (
        f"🎁 <b>{prod['nome']}</b>\n"
        f"🔗 <a href='{prod['link']}'>Aproveitar agora</a>\n\n"
        f"📦 Origem: {prod['origem']}\n"
        f"🚀 Participe do grupo para mais ofertas"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Ver Oferta", url=prod['link'])]
    ])
    try:
        await bot.send_message(chat_id=GROUP_ID, text=legenda, parse_mode="HTML", reply_markup=markup)
        ENVIADOS_CACHE.add(prod['nome'])
        logging.info(f"Enviado: {prod['nome']}")
    except Exception as e:
        logging.error(f"Erro ao enviar Telegram: {e}")

# --- Loop principal ---
async def agendar():
    while True:
        produtos = buscar_links_ofertas()
        for prod in produtos:
            await enviar_telegram(prod)
            await asyncio.sleep(2)
        await asyncio.sleep(INTERVALO_MINUTOS * 60)

if __name__ == "__main__":
    asyncio.run(agendar())

