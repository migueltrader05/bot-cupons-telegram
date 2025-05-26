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

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
SHOPEE_AFILIADO_URL = os.getenv("SHOPEE_AFILIADO_URL")
ML_AFILIADO_URL = os.getenv("ML_AFILIADO_URL")
SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", 10))

bot = Bot(token=TELEGRAM_TOKEN)

# Busca produtos no site do Pacheco Ofertas
def buscar_produtos():
    url = "https://www.divulgadorinteligente.com/pachecoofertas"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Erro ao acessar site de ofertas: {e}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    produtos = []

    for div in soup.select(".product" or "div:has(img)"):
        try:
            titulo = div.select_one("h2, h3, strong").get_text(strip=True)
            imagem = div.select_one("img")["src"] if div.select_one("img") else None
            link = div.select_one("a[href]")["href"]
            preco = "R$ 99,99"
            # Detecta origem do link
            if "shopee" in link:
                link_afiliado = SHOPEE_AFILIADO_URL
            elif "mercadolivre" in link:
                link_afiliado = ML_AFILIADO_URL
            else:
                continue

            produtos.append({
                "nome": titulo,
                "imagem": imagem,
                "link": link_afiliado,
                "preco_original": "R$ 129,90",
                "preco_desconto": preco
            })
        except Exception:
            continue

    return produtos

async def enviar_produto_estilizado(prod):
    legenda = f"""
📦 <b>{prod['nome']}</b>
💰 <s>De: {prod['preco_original']}</s>
🔥 <b>Por: {prod['preco_desconto']}</b>
📸 <a href='{prod['imagem']}'>Imagem do Produto</a>
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
        await enviar_produto_estilizado(prod)
        await asyncio.sleep(2)

async def loop_principal():
    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(lambda: asyncio.create_task(enviar_ofertas()))
    logger.info(f"🤖 Bot iniciado e agendado para rodar a cada {SCHEDULE_INTERVAL_MINUTES} minutos")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(loop_principal())
