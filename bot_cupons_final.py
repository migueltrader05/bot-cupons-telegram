import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
import logging
from bs4 import BeautifulSoup
from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
SHOPEE_AFILIADO_URL = os.getenv("SHOPEE_AFILIADO_URL")
ML_AFILIADO_URL = os.getenv("ML_AFILIADO_URL")
SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", 10))

bot = Bot(token=TELEGRAM_TOKEN)
ENVIADOS_CACHE = set()

URLS_FONTE = [
    "https://www.divulgadorinteligente.com/pachecoofertas",
    "https://promohub.com.br"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def buscar_produtos():
    produtos = []
    for site in URLS_FONTE:
        try:
            response = requests.get(site, headers=HEADERS, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for link_tag in soup.find_all("a", href=True):
                link = link_tag["href"]
                texto = link_tag.get_text(strip=True)
                if "shopee" in link:
                    produtos.append({
                        "nome": texto or "Produto Shopee",
                        "imagem": None,
                        "link": SHOPEE_AFILIADO_URL,
                        "preco_original": "R$ 149,00",
                        "preco_desconto": "R$ 99,00"
                    })
                elif "mercadolivre" in link:
                    produtos.append({
                        "nome": texto or "Produto Mercado Livre",
                        "imagem": None,
                        "link": ML_AFILIADO_URL,
                        "preco_original": "R$ 199,00",
                        "preco_desconto": "R$ 139,00"
                    })
        except Exception as e:
            logger.error(f"Erro ao acessar {site}: {e}")
    return produtos

async def enviar_produto_estilizado(prod):
    legenda = f"""
📦 <b>{prod['nome']}</b>
💰 <s>De: {prod['preco_original']}</s>
🔥 <b>Por: {prod['preco_desconto']}</b>
🔗 <a href='{prod['link']}'>Compre com Desconto</a>

👥 <a href='https://t.me/seugrupo'>Convide um amigo para o grupo</a>
    """

    try:
        if prod['imagem']:
            await bot.send_photo(chat_id=GROUP_ID, photo=prod['imagem'], caption=legenda, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=GROUP_ID, text=legenda, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")

async def enviar_ofertas():
    logger.info("🔍 Buscando ofertas...")
    produtos = buscar_produtos()
    for prod in produtos:
        if prod['link'] in ENVIADOS_CACHE:
            continue
        await enviar_produto_estilizado(prod)
        ENVIADOS_CACHE.add(prod['link'])
        if len(ENVIADOS_CACHE) > 100:
            ENVIADOS_CACHE.clear()
        await asyncio.sleep(2)

async def loop_principal():
    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(lambda: asyncio.create_task(enviar_ofertas()))
    logger.info(f"🤖 Bot iniciado e agendado para rodar a cada {SCHEDULE_INTERVAL_MINUTES} minutos")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(loop_principal())
