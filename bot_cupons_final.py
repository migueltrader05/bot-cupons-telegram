import os
import time
import asyncio
import logging
import requests
from bs4 import BeautifulSoup
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# Configurações
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
INVITE_LINK = os.getenv("INVITE_LINK", "https://t.me/seugrupo")
INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 60))

bot = Bot(token=TELEGRAM_TOKEN)
logging.basicConfig(level=logging.INFO)

# Função de scraping da Flash Sale Shopee
def buscar_flash_sale_shopee():
    url = "https://shopee.com.br/flash_sale"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")

    produtos = []
    for card in soup.select(".flash-sale-item-card")[:5]:
        nome = card.select_one(".FSI-product-name")
        preco = card.select_one(".FSI-current-price")
        imagem = card.select_one("img")
        link_tag = card.find_parent("a")

        if not (nome and preco and imagem and link_tag):
            continue

        nome_texto = nome.text.strip()
        preco_texto = preco.text.strip()
        imagem_url = imagem["src"]
        link = "https://shopee.com.br" + link_tag["href"]

        produtos.append({
            "nome": nome_texto,
            "preco": preco_texto,
            "imagem": imagem_url,
            "link": link
        })

    return produtos

# Função para envio de mensagem
async def enviar_produto_telegram(produto):
    legenda = (
        f"🎯 <b>{produto['nome']}</b>\n"
        f"💰 <b>{produto['preco']}</b>\n\n"
        f"🔗 <a href='{produto['link']}'>Ver oferta agora</a>\n\n"
        f"🚀 Convide amigos para o grupo: <a href='{INVITE_LINK}'>Clique aqui</a>"
    )

    try:
        await bot.send_photo(
            chat_id=GROUP_ID,
            photo=produto['imagem'],
            caption=legenda,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛍️ Comprar", url=produto['link'])]
            ])
        )
    except Exception as e:
        logging.error(f"Erro ao enviar produto: {str(e)}")

# Função principal
async def enviar_ofertas():
    produtos = buscar_flash_sale_shopee()
    if not produtos:
        await bot.send_message(chat_id=GROUP_ID, text="⚠️ Nenhuma oferta encontrada na Flash Sale da Shopee.")
        return

    await bot.send_message(chat_id=GROUP_ID, text="🛒 Buscando as melhores ofertas da Shopee Flash Sale!")

    for produto in produtos:
        await enviar_produto_telegram(produto)
        await asyncio.sleep(2)

# Agendamento
async def agendar_loop():
    while True:
        hora = time.localtime().tm_hour
        if 8 <= hora <= 23:
            await enviar_ofertas()
        await asyncio.sleep(INTERVALO_MINUTOS * 60)

if __name__ == "__main__":
    asyncio.run(agendar_loop())

