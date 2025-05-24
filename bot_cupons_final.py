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

    SHOPEE_CONFIG = {
        "partner_id": get_env_var("SHOPEE_PARTNER_ID"),
        "partner_key": get_env_var("SHOPEE_PARTNER_KEY"),
        "base_url": get_env_var("SHOPEE_BASE_URL", "https://partner.shopeemobile.com"),
        "page_size": int(get_env_var("SHOPEE_PAGE_SIZE", "5")),
        "max_retries": int(get_env_var("SHOPEE_MAX_RETRIES", "3")),
        "retry_delay": int(get_env_var("SHOPEE_RETRY_DELAY", "5")),
    }

    SCHEDULE_INTERVAL = int(get_env_var("SCHEDULE_INTERVAL_MINUTES", "10"))
    ACTIVE_HOURS = {
        "start": int(get_env_var("ACTIVE_HOURS_START", "9")),
        "end": int(get_env_var("ACTIVE_HOURS_END", "23")),
    }

    bot = Bot(token=TELEGRAM_TOKEN)
except (ConfigurationError, ValueError) as e:
    logger.error(f"Erro de configuração: {str(e)}")
    raise

# --- Utilitários ---
def gerar_assinatura(path: str, timestamp: int) -> str:
    base_string = f"{SHOPEE_CONFIG['partner_id']}{path}{timestamp}"
    return hmac.new(
        SHOPEE_CONFIG['partner_key'].encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

async def encurtar_link(url: str) -> str:
    try:
        response = requests.get(f"http://tinyurl.com/api-create.php?url={url}", timeout=5)
        if response.status_code == 200:
            return response.text
    except:
        pass
    return url

async def notify_admin(message: str) -> None:
    if ADMIN_CHAT_ID:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message)
        except Exception as e:
            logger.error(f"Falha ao notificar admin: {str(e)}")

# --- API Shopee: Busca por palavra-chave ---
async def buscar_destaques_shopee() -> List[Dict]:
    path = "/api/v2/product/search"
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)

    url = f"{SHOPEE_CONFIG['base_url']}{path}?partner_id={SHOPEE_CONFIG['partner_id']}&timestamp={timestamp}&sign={sign}"

    payload = {
        "keyword": "promoção",
        "page_size": SHOPEE_CONFIG["page_size"]
    }

    headers = {"Content-Type": "application/json"}

    for attempt in range(SHOPEE_CONFIG["max_retries"]):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            produtos = []
            if "result_list" in data and "item_list" in data["result_list"]:
                for item in data["result_list"]["item_list"]:
                    item_basic = item.get("item_basic", {})

                    nome = item_basic.get("name", "Produto sem nome")
                    itemid = item_basic.get("itemid")
                    imagem = item_basic.get("image")
                    link = await encurtar_link(f"https://shope.ee/{itemid}")
                    imagem_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else None

                    produtos.append({
                        "nome": nome,
                        "imagem": imagem_url,
                        "link": link,
                        "preco_original": "R$ 299,00",
                        "preco_atual": "R$ 199,00",
                        "vendas": 100,
                        "rating": 5,
                        "loja": "Shopee"
                    })
            return produtos

        except requests.RequestException as e:
            logger.error(f"Erro na conexão (tentativa {attempt + 1}): {str(e)}")
            if attempt == SHOPEE_CONFIG["max_retries"] - 1:
                raise APIConnectionError("Falha ao buscar produtos")
            await asyncio.sleep(SHOPEE_CONFIG["retry_delay"])

# --- Enviar mensagem ---
async def enviar_produto_estilizado(produto: Dict) -> None:
    legenda = (
        f"🎁 <b>{produto['nome']}</b>\n\n"
        f"💰 De: <s>{produto['preco_original']}</s>\n"
        f"👉 Por: <b>{produto['preco_atual']}</b>\n\n"
        f"🔗 <a href='{produto['link']}'>Compre agora</a>\n\n"
        f"🚀👀 Para mais ofertas, acesse:\n<a href='https://linktr.ee/grupocupons'>linktr.ee/grupocupons</a>"
    )

    try:
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
        logger.info(f"Produto enviado: {produto['nome']}")
    except Exception as e:
        logger.error(f"Erro ao enviar produto: {str(e)}")

# --- Loop principal ---
async def enviar_destaques():
    hora = time.localtime().tm_hour
    if not (ACTIVE_HOURS["start"] <= hora < ACTIVE_HOURS["end"]):
        logger.info("Fora do horário ativo")
        return

    try:
        produtos = await buscar_destaques_shopee()
        if not produtos:
            await bot.send_message(
                chat_id=GROUP_ID,
                text="📊 Nenhum destaque encontrado no momento.",
                parse_mode="HTML"
            )
            return

        await bot.send_message(
            chat_id=GROUP_ID,
            text="🏆 <b>DESTAQUES EM PROMOÇÃO</b> 🏆",
            parse_mode="HTML"
        )

        for produto in produtos:
            await enviar_produto_estilizado(produto)
            await asyncio.sleep(2)
    except Exception as e:
        logger.error(f"Erro inesperado: {str(e)}")
        await notify_admin(f"Erro no envio de destaques: {str(e)}")

async def loop_principal():
    schedule.every(SCHEDULE_INTERVAL).minutes.do(
        lambda: asyncio.create_task(enviar_destaques())
    )

    logger.info("🔁 Bot agendado para rodar...")
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(loop_principal())
