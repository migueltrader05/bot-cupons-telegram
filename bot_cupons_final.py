import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

# --- Verificação de variáveis obrigatórias ---
def get_env_var(name):
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variável de ambiente obrigatória '{name}' não está definida.")
    return value

# --- Configurações do Telegram via variáveis de ambiente ---
TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN")
GROUP_ID = int(get_env_var("GROUP_ID"))
bot = Bot(token=TELEGRAM_TOKEN)

# --- Configurações da Shopee Partners ---
partner_id = get_env_var("SHOPEE_PARTNER_ID")
partner_key = get_env_var("SHOPEE_PARTNER_KEY")
base_url = "https://partner.shopee.com.br"
path = "/api/v2/product/search"

def gerar_assinatura(path, timestamp):
    base_string = f"{partner_id}{path}{timestamp}"
    return hmac.new(
        partner_key.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()

def encurtar_link(url):
    try:
        response = requests.get(f"http://tinyurl.com/api-create.php?url={url}")
        if response.status_code == 200:
            return response.text
    except:
        pass
    return url

def buscar_produtos_shopee():
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)

    url = f"{base_url}{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"
    payload = {
        "keyword": "oferta",
        "page_size": 3
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(url, headers=headers, json=payload)
    data = response.json()

    mensagens = []
    if "result_list" in data and "item_list" in data["result_list"]:
        for item in data["result_list"]["item_list"]:
            nome = item.get("item_basic", {}).get("name", "Produto")
            itemid = item.get("item_basic", {}).get("itemid")
            imagem = item.get("item_basic", {}).get("image")
            link = encurtar_link(f"https://shope.ee/{itemid}")
            imagem_url = f"https://cf.shopee.com.br/file/{imagem}" if imagem else None

            mensagens.append({
                "nome": nome,
                "imagem": imagem_url,
                "link": link
            })

    return mensagens

async def enviar_produto_com_botao(nome, link, imagem=None):
    botao = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Ver oferta", url=link)]
    ])

    if imagem:
        await bot.send_photo(
            chat_id=GROUP_ID,
            photo=imagem,
            caption=f"🛍️ {nome}",
            reply_markup=botao
        )
    else:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=f"🛍️ {nome}",
            reply_markup=botao
        )

async def enviar_cupons():
    await enviar_produto_com_botao("Oferta Mercado Livre", "https://www.mercadolivre.com.br/ofertas?matt_tool=afiliados&tag=migu")

    try:
        produtos = buscar_produtos_shopee()
        for prod in produtos:
            await enviar_produto_com_botao(prod["nome"], prod["link"], prod["imagem"])
    except Exception as e:
        await bot.send_message(chat_id=GROUP_ID, text=f"⚠️ Erro ao buscar Shopee: {str(e)}")

    await enviar_produto_com_botao("Promo Amazon", "https://amazon.com.br/exemplo")
    await enviar_produto_com_botao("Oferta AliExpress", "https://aliexpress.com/exemplo")

def agendar_tarefa():
    schedule.every(15).minutes.do(lambda: asyncio.create_task(enviar_cupons()))

    print("Bot de cupons rodando...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    asyncio.run(enviar_cupons())
    agendar_tarefa()
