import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
import logging
from typing import Optional, List, Dict
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

# --- Configuração inicial ---
load_dotenv()

# --- Configuração de logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_best_sellers.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ConfigurationError(Exception):
    pass

class APIConnectionError(Exception):
    pass

def get_env_var(name: str, default: Optional[str] = None, required: bool = True) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ConfigurationError(f"Variável de ambiente obrigatória '{name}' não está definida.")
    return value

# --- Configurações ---
TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN")
GROUP_ID = int(get_env_var("GROUP_ID"))
ADMIN_CHAT_ID = get_env_var("ADMIN_CHAT_ID", required=False)
AFFILIATE_TAG = get_env_var("AFFILIATE_TAG", required=False)
INVITE_LINK = get_env_var("INVITE_LINK", "https://t.me/+seugrupocupons")

CATEGORIES = {
    "Eletrônicos": 11036732,
    "Beleza": 11036847,
    "Casa": 11036834,
    "Moda": 11036802,
    "Acessórios": 11036858,
    "Bebês": 11036872
}

SCHEDULE_INTERVAL = int(get_env_var("SCHEDULE_INTERVAL_MINUTES", "10"))
ACTIVE_HOURS = {
    "start": int(get_env_var("ACTIVE_HOURS_START", "9")),
    "end": int(get_env_var("ACTIVE_HOURS_END", "23")),
}

SHOPEE_CONFIG = {
    "partner_id": get_env_var("SHOPEE_PARTNER_ID"),
    "partner_key": get_env_var("SHOPEE_PARTNER_KEY"),
    "base_url": get_env_var("SHOPEE_BASE_URL", "https://partner.shopeemobile.com"),
    "page_size": 5,
    "max_retries": 3,
    "retry_delay": 5
}

bot = Bot(token=TELEGRAM_TOKEN)

def gerar_assinatura(path: str, timestamp: int) -> str:
    base_string = f"{SHOPEE_CONFIG['partner_id']}{path}{timestamp}"
    return hmac.new(
        SHOPEE_CONFIG['partner_key'].encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

async def encurtar_link(url: str) -> str:
    try:
        response = requests.get(f"http://tinyurl.com/api-create.php?url={url}")
        if response.status_code == 200:
            return response.text
    except:
        pass
    return url

async def notify_admin(message: str):
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        except:
            pass

async def buscar_mais_vendidos_shopee(category_id: int) -> List[Dict]:
    path = "/api/v2/product/get_item_list"
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)

    url = f"{SHOPEE_CONFIG['base_url']}{path}?partner_id={SHOPEE_CONFIG['partner_id']}&timestamp={timestamp}&sign={sign}"
    payload = {
        "category_id": category_id,
        "sort_by": "pop",
        "page_size": SHOPEE_CONFIG["page_size"],
        "offset": 0,
        "filter": "feeds"
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(SHOPEE_CONFIG["max_retries"]):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            if "items" not in data:
                return []

            produtos = []
            for item in data["items"]:
                item_basic = item.get("item_basic", {})
                if item_basic.get("sold", 0) < 100:
                    continue

                nome = item_basic.get("name", "Produto sem nome")
                itemid = item_basic.get("itemid")
                imagem = item_basic.get("image")
                link = await encurtar_link(f"https://shope.ee/{itemid}?utm_source=afiliado&utm_medium={AFFILIATE_TAG}")
                imagem_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else None

                preco_original = item_basic.get("price_before_discount", item_basic.get("price", 0)) / 100000
                preco_atual = item_basic.get("price", 0) / 100000

                produtos.append({
                    "nome": nome,
                    "imagem": imagem_url,
                    "link": link,
                    "preco_original": f"R$ {preco_original:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
                    "preco_atual": f"R$ {preco_atual:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                })

            return produtos
        except Exception as e:
            if attempt == SHOPEE_CONFIG["max_retries"] - 1:
                raise APIConnectionError(str(e))
            await asyncio.sleep(SHOPEE_CONFIG["retry_delay"])

async def enviar_produto_estilizado(produto: Dict, categoria: str):
    legenda = (
        f"🎯 <b>{produto['nome'][:100]}</b>\n\n"
        f"💥 <s>{produto['preco_original']}</s> 👉 <b>{produto['preco_atual']}</b>\n\n"
        f"🔗 <a href='{produto['link']}'>Compre agora</a>\n"
        f"📣 Convidar amigos: <a href='{INVITE_LINK}'>{INVITE_LINK}</a>"
    )

    if produto["imagem"]:
        await bot.send_photo(
            chat_id=GROUP_ID,
            photo=produto["imagem"],
            caption=legenda,
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=legenda,
            parse_mode="HTML"
        )

async def enviar_todos_os_mais_vendidos():
    hora_atual = time.localtime().tm_hour
    if not (ACTIVE_HOURS["start"] <= hora_atual < ACTIVE_HOURS["end"]):
        logger.info("Fora do horário ativo.")
        return

    for nome_categoria, categoria_id in CATEGORIES.items():
        await bot.send_message(chat_id=GROUP_ID, text=f"🔎 Buscando os mais vendidos em {nome_categoria}...")
        try:
            produtos = await buscar_mais_vendidos_shopee(categoria_id)
            for produto in produtos:
                await enviar_produto_estilizado(produto, nome_categoria)
                await asyncio.sleep(2)
        except Exception as e:
            await notify_admin(f"Erro ao buscar {nome_categoria}: {str(e)}")
            logger.error(f"Erro ao buscar {nome_categoria}: {str(e)}")

async def loop_principal():
    schedule.every(SCHEDULE_INTERVAL).minutes.do(lambda: asyncio.create_task(enviar_todos_os_mais_vendidos()))
    logger.info("📅 Bot agendado para rodar...")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(loop_principal())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
