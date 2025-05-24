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

# --- Classes de Exceção ---
class ConfigurationError(Exception):
    pass

class APIConnectionError(Exception):
    pass

# --- Validação de variáveis de ambiente ---
def get_env_var(name: str, default: Optional[str] = None, required: bool = True) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise ConfigurationError(f"Variável de ambiente obrigatória '{name}' não está definida.")
    return value

# --- Configurações ---
try:
    TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN")
    GROUP_ID = int(get_env_var("GROUP_ID"))
    ADMIN_CHAT_ID = get_env_var("ADMIN_CHAT_ID", required=False)

    SCHEDULE_INTERVAL = int(get_env_var("SCHEDULE_INTERVAL_MINUTES", "10"))
    ACTIVE_HOURS = {
        "start": int(get_env_var("ACTIVE_HOURS_START", "9")),
        "end": int(get_env_var("ACTIVE_HOURS_END", "23")),
    }

    bot = Bot(token=TELEGRAM_TOKEN)

except (ConfigurationError, ValueError) as e:
    logger.error(f"Erro de configuração: {str(e)}")
    raise

# --- Categorias fixas para envio ---
CATEGORIAS = {
    "Eletrônicos": 11036732,
    "Beleza": 11036649,
    "Casa": 11036842,
    "Moda": 11036000,
    "Acessórios": 11036893,
    "Bebê": 11036043
}

# --- Utilitários ---
def gerar_assinatura(path: str, timestamp: int, partner_id: str, partner_key: str) -> str:
    base_string = f"{partner_id}{path}{timestamp}"
    return hmac.new(
        partner_key.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

async def encurtar_link(url: str) -> str:
    for _ in range(3):
        try:
            response = requests.get(f"http://tinyurl.com/api-create.php?url={url}", timeout=5)
            if response.status_code == 200:
                return response.text
        except requests.RequestException:
            await asyncio.sleep(2)
    return url

async def notify_admin(message: str) -> None:
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        except Exception as e:
            logger.error(f"Falha ao notificar admin: {str(e)}")

# --- API Shopee por categoria ---
async def buscar_mais_vendidos_categoria(categoria_id: int) -> List[Dict]:
    partner_id = get_env_var("SHOPEE_PARTNER_ID")
    partner_key = get_env_var("SHOPEE_PARTNER_KEY")
    base_url = "https://partner.shopeemobile.com"
    path = "/api/v2/product/get_item_list"
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp, partner_id, partner_key)

    url = f"{base_url}{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"
    payload = {
        "category_id": categoria_id,
        "sort_by": "pop",
        "page_size": 5,
        "offset": 0,
        "filter": "feeds"
    }
    headers = {"Content-Type": "application/json"}

    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()

            if not data.get("items"):
                return []

            produtos = []
            for item in data["items"]:
                basic = item.get("item_basic", {})
                if basic.get("sold", 0) < 50:
                    continue

                nome = basic.get("name", "Produto")
                itemid = basic.get("itemid")
                imagem = basic.get("image")
                link = await encurtar_link(f"https://shope.ee/{itemid}")
                imagem_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else None
                preco_de = basic.get("price_before_discount", basic.get("price", 0)) / 100000
                preco_por = basic.get("price", 0) / 100000
                rating = basic.get("item_rating", {}).get("rating_star", 0)
                vendas = basic.get("sold", 0)

                produtos.append({
                    "nome": nome,
                    "imagem": imagem_url,
                    "link": link,
                    "preco_original": f"R$ {preco_de:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
                    "preco_atual": f"R$ {preco_por:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
                    "rating": rating,
                    "vendas": vendas
                })
            return produtos

        except Exception as e:
            logger.error(f"Erro na conexão (tentativa {attempt+1}): {e}")
            await asyncio.sleep(3)
    raise APIConnectionError("Falha após 3 tentativas")

# --- Envio Telegram ---
async def enviar_produto_estilizado(produto: Dict, titulo: str) -> None:
    legenda = (
        f"🔥 <b>{titulo}</b> 🔥\n"
        f"🛍️ <b>{produto['nome'][:100]}</b>\n"
        f"⭐ {produto['rating']} | 📈 {produto['vendas']} vendidos\n"
        f"💰 De: <s>{produto['preco_original']}</s>\n👉 Por: <b>{produto['preco_atual']}</b>\n\n"
        f"🔗 <a href='{produto['link']}'>Comprar com desconto</a>"
    )
    if produto["imagem"]:
        await bot.send_photo(GROUP_ID, produto["imagem"], caption=legenda, parse_mode="HTML")
    else:
        await bot.send_message(GROUP_ID, text=legenda, parse_mode="HTML")

async def enviar_relatorio_geral():
    hora = time.localtime().tm_hour
    if not (ACTIVE_HOURS["start"] <= hora < ACTIVE_HOURS["end"]):
        logger.info("Fora do horário de envio")
        return

    for nome, categoria_id in CATEGORIAS.items():
        try:
            await bot.send_message(GROUP_ID, text=f"🔎 Buscando os mais vendidos em {nome}...", parse_mode="HTML")
            produtos = await buscar_mais_vendidos_categoria(categoria_id)
            if not produtos:
                await bot.send_message(GROUP_ID, text=f"⚠️ Nenhum produto popular encontrado em {nome}.")
                continue
            for prod in produtos:
                await enviar_produto_estilizado(prod, nome)
                await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Erro em categoria {nome}: {e}")
            await notify_admin(f"Erro em categoria {nome}: {e}")

# --- Agendamento ---
async def loop_principal():
    schedule.every(SCHEDULE_INTERVAL).minutes.do(lambda: asyncio.create_task(enviar_relatorio_geral()))
    logger.info("📅 Bot agendado para rodar...")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(loop_principal())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"Falha crítica: {e}")
        raise

