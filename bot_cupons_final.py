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
    # Telegram
    TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN")
    GROUP_ID = int(get_env_var("GROUP_ID"))
    ADMIN_CHAT_ID = get_env_var("ADMIN_CHAT_ID", required=False)

    # Shopee
    SHOPEE_CONFIG = {
        "partner_id": get_env_var("SHOPEE_PARTNER_ID"),
        "partner_key": get_env_var("SHOPEE_PARTNER_KEY"),
        "base_url": get_env_var("SHOPEE_BASE_URL", "https://partner.shopeemobile.com"),
        "category_id": int(get_env_var("SHOPEE_CATEGORY_ID", "11036732")),  # Eletrônicos como padrão
        "page_size": int(get_env_var("SHOPEE_PAGE_SIZE", "5")),
        "max_retries": int(get_env_var("SHOPEE_MAX_RETRIES", "3")),
        "retry_delay": int(get_env_var("SHOPEE_RETRY_DELAY", "5")),
    }

    # Agendamento
    SCHEDULE_INTERVAL = int(get_env_var("SCHEDULE_INTERVAL_MINUTES", "10"))  # Alterado para 10 minutos
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
    for attempt in range(3):
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

# --- API Shopee - Produtos Mais Vendidos ---
async def buscar_mais_vendidos_shopee() -> List[Dict]:
    """Busca produtos mais vendidos por categoria"""
    path = "/api/v2/product/get_item_list"
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)

    url = f"{SHOPEE_CONFIG['base_url']}{path}?partner_id={SHOPEE_CONFIG['partner_id']}&timestamp={timestamp}&sign={sign}"

    payload = {
        "category_id": SHOPEE_CONFIG["category_id"],
        "sort_by": "pop",  # Ordenar por popularidade (mais vendidos)
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

            if "error" in data:
                raise APIConnectionError(f"API Shopee retornou erro: {data['error']}")

            if not data.get("items"):
                return []

            produtos = []
            for item in data["items"]:
                item_basic = item.get("item_basic", {})

                # Verifica se tem vendas significativas
                if item_basic.get("sold", 0) < 100:  # Filtra produtos com menos de 100 vendas
                    continue

                nome = item_basic.get("name", "Produto sem nome")
                itemid = item_basic.get("itemid")
                imagem = item_basic.get("image")
                link = await encurtar_link(f"https://shope.ee/{itemid}")
                imagem_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else None

                # Extrai preços e vendas
                preco_original = item_basic.get("price_before_discount", item_basic.get("price", 0)) / 100000
                preco_atual = item_basic.get("price", 0) / 100000
                vendas = item_basic.get("sold", 0)
                rating = item_basic.get("item_rating", {}).get("rating_star", 0)

                # Formatação
                preco_original_str = f"R$ {preco_original:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
                preco_atual_str = f"R$ {preco_atual:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

                produtos.append({
                    "nome": nome,
                    "imagem": imagem_url,
                    "link": link,
                    "preco_original": preco_original_str,
                    "preco_atual": preco_atual_str,
                    "vendas": vendas,
                    "rating": rating,
                    "loja": item_basic.get("shop_name", "Loja Shopee")
                })

            return produtos

        except requests.RequestException as e:
            logger.error(f"Erro na conexão (tentativa {attempt + 1}): {str(e)}")
            if attempt == SHOPEE_CONFIG["max_retries"] - 1:
                raise APIConnectionError(f"Falha após {SHOPEE_CONFIG['max_retries']} tentativas")
            await asyncio.sleep(SHOPEE_CONFIG["retry_delay"])

# --- Telegram ---
async def enviar_produto_estilizado(produto: Dict) -> None:
    """Envia mensagem formatada com informações do produto"""
    keyboard = [
        [
            InlineKeyboardButton("🛒 Comprar Agora", url=produto["link"]),
            InlineKeyboardButton("⭐ Avaliações", callback_data="ratings_info")
        ],
        [InlineKeyboardButton("🏪 Ver Mais da Loja", callback_data="store_info")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    rating_emoji = "⭐" * int(produto["rating"]) + "☆" * (5 - int(produto["rating"])) if produto["rating"] else "Sem avaliações"

    legenda = (
        f"🔥 <b>{produto['nome'][:100]}</b>\n\n"
        f"🏪 <i>{produto['loja']}</i>\n"
        f"📈 <b>{produto['vendas']:,}</b> vendas\n\n"
        f"{rating_emoji}\n\n"
        f"💰 <s>{produto['preco_original']}</s>\n"
        f"👉 <b>{produto['preco_atual']}</b>\n\n"
        f"🛍️ <a href='{produto['link']}'>Compre agora com desconto!</a>"
    )

    try:
        if produto["imagem"]:
            await bot.send_photo(
                chat_id=GROUP_ID,
                photo=produto["imagem"],
                caption=legenda,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(
                chat_id=GROUP_ID,
                text=legenda,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        logger.info(f"Produto enviado: {produto['nome']}")
    except Exception as e:
        logger.error(f"Erro ao enviar produto: {str(e)}")
        raise

async def enviar_relatorio_vendas() -> None:
    current_hour = time.localtime().tm_hour
    if not (ACTIVE_HOURS["start"] <= current_hour < ACTIVE_HOURS["end"]):
        logger.info("Fora do horário ativo. Não enviando mensagens.")
        return

    logger.info("Buscando produtos mais vendidos...")

    try:
        produtos = await buscar_mais_vendidos_shopee()
        if not produtos:
            await bot.send_message(
                chat_id=GROUP_ID,
                text="📊 Hoje não encontramos produtos populares. Voltamos em breve com mais destaques!",
                parse_mode="HTML"
            )
            return

        await bot.send_message(
            chat_id=GROUP_ID,
            text=f"🏆 <b>DESTAQUES DO DIA - MAIS VENDIDOS</b> 🏆\n\n"
                 "Confira os produtos que estão bombando na Shopee hoje!\n"
                 "🛒 Itens com melhor avaliação e mais vendidos\n\n"
                 "⏳ Ofertas válidas por tempo limitado!",
            parse_mode="HTML"
        )

        for produto in produtos:
            await enviar_produto_estilizado(produto)
            await asyncio.sleep(3)

        await bot.send_message(
            chat_id=GROUP_ID,
            text="📢 <b>Quer mais ofertas?</b>\n\n"
                 "Acesse nosso canal exclusivo:\n"
                 "👉 @cupons_diarios\n\n"
                 "#Shopee #Ofertas #MaisVendidos",
            parse_mode="HTML"
        )

    except APIConnectionError as e:
        error_msg = f"Erro na API Shopee: {str(e)}"
        await bot.send_message(
            chat_id=GROUP_ID,
            text="⚠️ Estamos com dificuldades para acessar as informações de produtos no momento. "
                 "Tente novamente mais tarde!",
            parse_mode="HTML"
        )
        await notify_admin(f"ERRO NA API: {error_msg}")
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        await notify_admin(f"ERRO GRAVE: {error_msg}")
        logger.exception("Erro no envio de relatório")

# --- Agendamento ---
async def loop_principal() -> None:
    schedule.every(SCHEDULE_INTERVAL).minutes.do(
        lambda: asyncio.create_task(enviar_relatorio_vendas())
    )

    startup_msg = (
        "🛍️ Bot de Mais Vendidos Iniciado!\n\n"
        f"📊 Categoria: {SHOPEE_CONFIG['category_id']}\n"
        f"⏰ Intervalo: {SCHEDULE_INTERVAL} minutos\n"
        f"🕒 Horário ativo: {ACTIVE_HOURS['start']}h-{ACTIVE_HOURS['end']}h\n"
        f"📦 Produtos por envio: {SHOPEE_CONFIG['page_size']}"
    )

    logger.info(startup_msg)
    await notify_admin(startup_msg)

    while True:
        try:
            schedule.run_pending()
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Erro no loop: {str(e)}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        asyncio.run(loop_principal())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
    except Exception as e:
        logger.critical(f"Falha crítica: {str(e)}")
        raise
