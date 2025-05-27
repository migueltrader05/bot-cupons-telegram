import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
import logging
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
SHOPEE_AFILIADO_URL = os.getenv("SHOPEE_AFILIADO_URL")
ML_AFILIADO_URL = os.getenv("ML_AFILIADO_URL")
AMAZON_AFILIADO_ID = os.getenv("AMAZON_AFILIADO_ID", "maxx0448-20")
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

def converter_amazon(link):
    if "amazon.com.br" in link:
        if "tag=" in link:
            return link
        separador = "&" if "?" in link else "?"
        return f"{link}{separador}tag={AMAZON_AFILIADO_ID}"
    return link

def identificar_origem(link):
    if "shopee" in link:
        return "Shopee"
    elif "mercadolivre" in link:
        return "Mercado Livre"
    elif "amazon" in link:
        return "Amazon"
    else:
        return "Outros"

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
                origem = identificar_origem(link)

                if "shopee" in link:
                    link_convertido = SHOPEE_AFILIADO_URL
                elif "mercadolivre" in link:
                    link_convertido = ML_AFILIADO_URL
                elif "amazon.com.br" in link:
                    link_convertido = converter_amazon(link)
                else:
                    continue

                produtos.append({
                    "nome": texto or f"Produto {origem}",
                    "imagem": None,
                    "link": link_convertido,
                    "preco_original": "R$ 149,00",
                    "preco_desconto": "R$ 99,00",
                    "origem": origem
                })
        except Exception as e:
            logger.error(f"Erro ao acessar {site}: {e}")
    return produtos

async def enviar_produto_estilizado(prod):
    legenda = f"""
🔥 <b>{prod['nome']}</b>

🏬 Loja: <i>{prod['origem']}</i>
💸 De: <s>{prod['preco_original']}</s>
👉 Por: <b>{prod['preco_desconto']}</b>

🛙 <a href='{prod['link']}'>Clique aqui para comprar</a>

📢 Compartilhe com amigos e receba mais ofertas:
👉 <a href='https://t.me/seugrupo'>Entrar no grupo VIP</a>
"""

    try:
        if prod['imagem']:
            await bot.send_photo(chat_id=GROUP_ID, photo=prod['imagem'], caption=legenda, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=GROUP_ID, text=legenda, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")

async def enviar_ofertas():
    hora_brasilia = datetime.utcnow() - timedelta(hours=3)
    if not (7 <= hora_brasilia.hour < 23):
        logger.info("Fora do horário de envio (07h às 23h). Ignorando execução.")
        return

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
