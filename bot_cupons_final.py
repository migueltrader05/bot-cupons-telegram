import os
import time
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
import schedule

# --- Configurações ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
SHOPEE_AFILIADO = "https://s.shopee.com.br/30bjw3P88I"
ML_AFILIADO = "https://mercadolivre.com/sec/1XMEDg1"
INTERVALO_MINUTOS = 10

bot = Bot(token=TELEGRAM_TOKEN)
logging.basicConfig(level=logging.INFO)
ENVIADOS_CACHE = set()

# --- Scraping do site ---
def buscar_links_ofertas():
    url = "https://www.divulgadorinteligente.com/pachecoofertas"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        blocos = soup.select(".post")

        produtos = []
        for post in blocos:
            a_tag = post.find("a", href=True)
            img_tag = post.find("img", src=True)

            if not a_tag or not img_tag:
                continue

            link = a_tag['href']
            titulo = a_tag.get_text(strip=True)
            imagem = img_tag['src']

            # Shopee ou Mercado Livre
            if "shopee" in link:
                link_final = SHOPEE_AFILIADO
            elif "mercadolivre" in link or "mlb" in link:
                link_final = ML_AFILIADO
            else:
                continue

            if link_final in ENVIADOS_CACHE:
                continue

            produtos.append({
                "nome": titulo,
                "link": link_final,
                "imagem": imagem,
                "origem": "Shopee" if "shopee" in link else "Mercado Livre"
            })
            ENVIADOS_CACHE.add(link_final)

        return produtos

    except Exception as e:
        logging.error(f"Erro ao buscar produtos: {e}")
        return []

# --- Enviar produto com estilo ---
def enviar_produto(produto):
    legenda = (
        f"🎁 <b>{produto['nome']}</b>\n\n"
        f"🛍️ Origem: {produto['origem']}\n"
        f"🔗 <a href='{produto['link']}'>Clique para comprar</a>\n\n"
        f"🚀 Para mais cupons, acesse:\n"
        f"<a href='https://t.me/promoalerte'>Nosso grupo no Telegram</a>"
    )

    bot.send_photo(
        chat_id=GROUP_ID,
        photo=produto["imagem"],
        caption=legenda,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🛒 Comprar", url=produto["link"]),
            InlineKeyboardButton("📢 Convidar amigos", url="https://t.me/promoalerte")
        ]])
    )

# --- Loop principal ---
def executar_bot():
    logging.info("🔍 Buscando ofertas...")
    produtos = buscar_links_ofertas()
    for produto in produtos:
        try:
            enviar_produto(produto)
            time.sleep(2)
        except Exception as e:
            logging.error(f"Erro ao enviar produto: {e}")

# --- Agendamento ---
schedule.every(INTERVALO_MINUTOS).minutes.do(executar_bot)

logging.info("🤖 Bot iniciado e agendado para rodar a cada %d minutos", INTERVALO_MINUTOS)
executar_bot()  # Executa uma vez ao iniciar

while True:
    schedule.run_pending()
    time.sleep(1)
