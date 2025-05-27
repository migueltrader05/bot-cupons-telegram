# -*- coding: utf-8 -*-
import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def get_env_variable(var_name, default=None, required=True):
    value = os.getenv(var_name, default)
    if required and value is None:
        logger.error(f"Erro Crítico: Variável de ambiente obrigatória '{var_name}' não definida.")
        raise ValueError(f"Variável de ambiente obrigatória '{var_name}' não definida.")
    if value is None and default is not None:
        logger.warning(f"Variável de ambiente '{var_name}' não definida, usando valor padrão: '{default}'")
    return value

try:
    TELEGRAM_TOKEN = get_env_variable("TELEGRAM_TOKEN")
    GROUP_ID = int(get_env_variable("GROUP_ID"))
    SHOPEE_AFILIADO_ID = get_env_variable("SHOPEE_AFILIADO_ID", required=False)
    ML_AFILIADO_ID = get_env_variable("ML_AFILIADO_ID", required=False)
    AMAZON_AFILIADO_ID = get_env_variable("AMAZON_AFILIADO_ID", default="maxx0448-20")
    SCHEDULE_INTERVAL_MINUTES = int(get_env_variable("SCHEDULE_INTERVAL_MINUTES", default=10))
    HORARIO_INICIO_ENVIO = 7
    HORARIO_FIM_ENVIO = 23
    MAX_CACHE_SIZE = int(get_env_variable("MAX_CACHE_SIZE", default=200))
    FUSO_HORARIO_BRASILIA = ZoneInfo(get_env_variable("FUSO_HORARIO", default="America/Sao_Paulo"))
except ValueError as e:
    exit(1)
except Exception as e:
    logger.error(f"Erro inesperado ao carregar configurações: {e}")
    exit(1)

try:
    bot = Bot(token=TELEGRAM_TOKEN)
except Exception as e:
    logger.error(f"Erro ao inicializar o bot do Telegram: {e}")
    exit(1)

ENVIADOS_CACHE = set()

URLS_FONTE = {
    "divulgadorinteligente": "https://www.divulgadorinteligente.com/pachecoofertas",
    "promohub": "https://promohub.com.br"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
REQUEST_TIMEOUT = 20

def extrair_dados_divulgadorinteligente(soup, base_url):
    produtos = []
    offer_links = soup.select("a[href*='amazon.com.br'], a[href*='shopee.com.br'], a[href*='mercadolivre.com.br']")
    logger.info(f"[divulgadorinteligente] Encontrados {len(offer_links)} links candidatos a ofertas.")
    for link_tag in offer_links:
        link = link_tag.get("href")
        if not link:
            continue

        nome_tag = link_tag.select_one("h4") or link_tag
        nome = nome_tag.get_text(strip=True) if nome_tag else "Produto sem nome"
        origem = "Amazon" if "amazon" in link else ("Shopee" if "shopee" in link else "Mercado Livre")

        preco_desconto = "R$ ???"
        preco_tag = link_tag.select_one("h4 > span") or link_tag.find("span")
        if preco_tag:
            preco_desconto = preco_tag.get_text(strip=True)

        imagem_tag = link_tag.select_one("img")
        imagem = urljoin(base_url, imagem_tag.get("src") or imagem_tag.get("data-src")) if imagem_tag else None

        produtos.append({
            "nome": nome,
            "link": link,
            "origem": origem,
            "imagem": imagem,
            "preco_original": "",
            "preco_desconto": preco_desconto
        })
    return produtos

def extrair_dados_promohub(soup, base_url):
    produtos = []
    offer_cards = soup.select("div.card, article.shadow-sm")
    logger.info(f"[promohub] Encontrados {len(offer_cards)} cards candidatos a ofertas.")
    for card in offer_cards:
        link_tag = card.select_one("a[href*='shopee.com.br'], a[href*='mercadolivre.com.br']")
        if not link_tag:
            continue

        link = link_tag.get("href")
        if not link:
            continue

        nome_tag = card.select_one("h2, h3, p.title, p.font-semibold")
        nome = nome_tag.get_text(strip=True) if nome_tag else "Produto sem nome"

        preco_tag = card.select_one("span.price, div.price")
        preco = preco_tag.get_text(strip=True) if preco_tag else "R$ ???"

        imagem_tag = card.select_one("img")
        imagem = urljoin(base_url, imagem_tag.get("src") or imagem_tag.get("data-src")) if imagem_tag else None

        origem = "Shopee" if "shopee" in link else "Mercado Livre"

        produtos.append({
            "nome": nome,
            "link": link,
            "origem": origem,
            "imagem": imagem,
            "preco_original": "",
            "preco_desconto": preco
        })
    return produtos

async def enviar_oferta(produto):
    try:
        legenda = (
            f"<b>{produto['nome']}</b>\n"
            f"🏬 Loja: {produto['origem']}\n"
            f"💰 <b>{produto['preco_desconto']}</b>\n"
            f"🔗 <a href='{produto['link']}'>Clique para aproveitar</a>\n\n"
            f"👥 Compartilhe com amigos: <a href='https://t.me/seugrupo'>Grupo de Ofertas</a>"
        )
        if produto['imagem']:
            await bot.send_photo(
                chat_id=GROUP_ID,
                photo=produto['imagem'],
                caption=legenda,
                parse_mode=ParseMode.HTML
            )
        else:
            await bot.send_message(
                chat_id=GROUP_ID,
                text=legenda,
                parse_mode=ParseMode.HTML
            )
        logger.info(f"Mensagem enviada: {produto['nome']}")
    except TelegramError as e:
        logger.error(f"Erro ao enviar produto: {e}")
