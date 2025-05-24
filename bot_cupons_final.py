import time
import hmac
import hashlib
import json
import requests
import schedule
import os
import asyncio
from telegram import Bot

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
base_url = "https://partner.shopeemobile.com"
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
    palavras_chave = ["sofá", "oferta", "promoção"]
    timestamp = int(time.time())
    sign = gerar_assinatura(path, timestamp)
    url = f"{base_url}{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"
    headers = {"Content-Type": "application/json"}

    for palavra in palavras_chave:
        payload = {"keyword": palavra, "page_size": 3}
        response = requests.post(url, headers=headers, json=payload)
        print("Shopee API response:", response.text)

        if response.status_code != 200:
            continue

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
                    "link": link,
                    "preco_de": "R$ 999,00",
                    "preco_por": "R$ 599,00"
                })

        if mensagens:
            return mensagens

    return []

async def enviar_produto_estilizado(nome, link, imagem=None, preco_de="R$ ???", preco_por="R$ ???"):
    legenda = (
        f"🎁 <b>{nome}</b>\n\n"
        f"💰 De: <s>{preco_de}</s>\n"
        f"👉 Por: <b>{preco_por}</b>\n\n"
        f"🔗 <a href='{link}'>Link p/ comprar</a>\n\n"
        f"🚀👀 Para mais ofertas e cupons, acesse:\n"
        f"<a href='https://linktr.ee/grupocupons'>linktr.ee/grupocupons</a>"
    )

    if imagem:
        await bot.send_photo(
            chat_id=GROUP_ID,
            photo=imagem,
            caption=legenda,
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=GROUP_ID,
            text=legenda,
            parse_mode="HTML"
        )

async def enviar_cupons():
    await enviar_produto_estilizado(
        nome="Oferta Mercado Livre",
        link="https://www.mercadolivre.com.br/ofertas?matt_tool=afiliados&tag=migu",
        imagem="https://http2.mlstatic.com/frontend-assets/ml-web-navigation/ui-navigation/5.19.1/mercado-libre-logo__large_plus.png",
        preco_de="R$ 299,00",
        preco_por="R$ 199,00"
    )

    try:
        produtos = buscar_produtos_shopee()
        if not produtos:
            await bot.send_message(chat_id=GROUP_ID, text="⚠️ Nenhum produto foi encontrado na Shopee.")
        for prod in produtos:
            await enviar_produto_estilizado(
                nome=prod["nome"],
                link=prod["link"],
                imagem=prod["imagem"],
                preco_de=prod.get("preco_de"),
                preco_por=prod.get("preco_por")
            )
    except Exception as e:
        await bot.send_message(chat_id=GROUP_ID, text=f"⚠️ Erro ao buscar Shopee: {str(e)}")

def agendar():
    schedule.every(15).minutes.do(lambda: asyncio.run(enviar_cupons()))
    print("Bot de cupons rodando...")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    agendar()
