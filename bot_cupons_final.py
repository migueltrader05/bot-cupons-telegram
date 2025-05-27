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
from zoneinfo import ZoneInfo # Usando zoneinfo (Python 3.9+) para lidar com fuso horário
from bs4 import BeautifulSoup
from urllib.parse import urljoin # Para resolver URLs relativas de imagens
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError

# --- Configuração do Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Carregamento e Validação das Variáveis de Ambiente ---
def get_env_variable(var_name, default=None, required=True):
    """Busca uma variável de ambiente e opcionalmente exige sua presença."""
    value = os.getenv(var_name, default)
    if required and value is None:
        logger.error(f"Erro Crítico: Variável de ambiente obrigatória \'{var_name}\' não definida.")
        raise ValueError(f"Variável de ambiente obrigatória \'{var_name}\' não definida.")
    if value is None and default is not None:
        # Corrigido: Adicionado aspas faltantes no log warning
        logger.warning(f"Variável de ambiente \'{var_name}\' não definida, usando valor padrão: \'{default}\'")
    return value

try:
    TELEGRAM_TOKEN = get_env_variable("TELEGRAM_TOKEN")
    GROUP_ID = int(get_env_variable("GROUP_ID"))
    # IDs ou Nomes de Afiliado (Ajuste conforme necessário)
    SHOPEE_AFILIADO_ID = get_env_variable("SHOPEE_AFILIADO_ID", required=False) # ID/Nome de afiliado Shopee
    ML_AFILIADO_ID = get_env_variable("ML_AFILIADO_ID", required=False) # ID/Nome de afiliado Mercado Livre
    AMAZON_AFILIADO_ID = get_env_variable("AMAZON_AFILIADO_ID", default="maxx0448-20")
    SCHEDULE_INTERVAL_MINUTES = int(get_env_variable("SCHEDULE_INTERVAL_MINUTES", default=10))
    # Usando as variáveis de ambiente para horário, como no código anterior completo
    HORARIO_INICIO_ENVIO = int(get_env_variable("HORARIO_INICIO_ENVIO", default=7))
    HORARIO_FIM_ENVIO = int(get_env_variable("HORARIO_FIM_ENVIO", default=23))
    MAX_CACHE_SIZE = int(get_env_variable("MAX_CACHE_SIZE", default=200))
    FUSO_HORARIO_BRASILIA = ZoneInfo(get_env_variable("FUSO_HORARIO", default="America/Sao_Paulo"))
except ValueError as e:
    # Erro já logado na função get_env_variable
    exit(1) # Encerra o script se variáveis obrigatórias faltarem
except Exception as e:
    logger.error(f"Erro inesperado ao carregar configurações: {e}")
    exit(1)

# --- Inicialização do Bot e Cache ---
try:
    bot = Bot(token=TELEGRAM_TOKEN)
except Exception as e:
    logger.error(f"Erro ao inicializar o bot do Telegram: {e}")
    exit(1)

ENVIADOS_CACHE = set()

# --- Fontes de Ofertas e Configurações de Requisição ---
URLS_FONTE = {
    "divulgadorinteligente": "https://www.divulgadorinteligente.com/pachecoofertas",
    "promohub": "https://promohub.com.br"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
REQUEST_TIMEOUT = 20 # Mantendo o timeout aumentado

# --- Funções Auxiliares --- 
# Função de conversão de link de afiliado (do código completo anterior)
def converter_link_afiliado(link_original, origem):
    """Converte um link original para um link de afiliado baseado na origem."""
    global AMAZON_AFILIADO_ID, SHOPEE_AFILIADO_ID, ML_AFILIADO_ID
    if not link_original:
        return None

    try:
        if origem == "Amazon":
            if not AMAZON_AFILIADO_ID:
                logger.warning(f"AMAZON_AFILIADO_ID não definido. Usando link original: {link_original}")
                return link_original
            if "tag=" in link_original:
                logger.debug(f"Link já possui tag Amazon: {link_original}")
                return link_original
            separador = "&" if "?" in link_original else "?"
            return f"{link_original}{separador}tag={AMAZON_AFILIADO_ID}"

        elif origem == "Shopee":
            if not SHOPEE_AFILIADO_ID:
                logger.warning(f"SHOPEE_AFILIADO_ID não definido. Usando link original: {link_original}")
                return link_original
            separador = "&" if "?" in link_original else "?"
            logger.info(f"Aplicando ID de afiliado Shopee ({SHOPEE_AFILIADO_ID}) ao link: {link_original}")
            # ** ATENÇÃO: Verifique se af_sub_siteid é o parâmetro correto para você **
            return f"{link_original}{separador}af_sub_siteid={SHOPEE_AFILIADO_ID}"

        elif origem == "Mercado Livre":
            if not ML_AFILIADO_ID:
                 logger.warning(f"ML_AFILIADO_ID não definido. Usando link original: {link_original}")
            else:
                 logger.warning(f"Lógica de afiliação Mercado Livre não implementada/verificada. Usando link original: {link_original}")
            return link_original

        else:
            return link_original
    except Exception as e:
        logger.error(f"Erro ao tentar converter link de afiliado para \'{link_original}\' (Origem: {origem}): {e}")
        return link_original

# Função de identificação de origem (do código completo anterior)
def identificar_origem(link):
    """Identifica a loja de origem baseado no link."""
    if not link: return "Desconhecida"
    link_lower = link.lower()
    if "shopee.com" in link_lower: return "Shopee"
    if "mercadolivre.com" in link_lower: return "Mercado Livre"
    if "amazon.com" in link_lower: return "Amazon"
    return "Outra"

# --- Funções de Extração (Integrando as do último código do usuário) ---
def extrair_dados_divulgadorinteligente(soup, base_url):
    """Extrai dados do site divulgadorinteligente.com/pachecoofertas (versão do usuário)."""
    produtos = []
    # Usando o seletor do usuário
    offer_links = soup.select("a[href*='amazon.com.br'], a[href*='shopee.com.br'], a[href*='mercadolivre.com.br']")
    logger.info(f"[divulgadorinteligente] Encontrados {len(offer_links)} links candidatos a ofertas (lógica do usuário).")
    for link_tag in offer_links:
        link_original = link_tag.get("href") # Renomeado para link_original
        if not link_original:
            continue

        nome_tag = link_tag.select_one("h4") or link_tag
        nome = nome_tag.get_text(strip=True) if nome_tag else "Produto sem nome"
        # Tenta limpar o nome se o preço estiver junto
        nome = nome.split("R$")[0].strip()

        # Identifica a origem ANTES de converter o link
        origem = identificar_origem(link_original)

        preco_desconto = "N/D" # Padrão N/D
        preco_tag = link_tag.select_one("h4 > span") or link_tag.find("span")
        if preco_tag:
            preco_desconto = preco_tag.get_text(strip=True)

        # Tentativa de pegar preço original (se existir tag <s>)
        preco_original_tag = link_tag.select_one("h4 > s")
        preco_original = preco_original_tag.get_text(strip=True) if preco_original_tag else "N/D"

        imagem_tag = link_tag.select_one("img")
        imagem = urljoin(base_url, imagem_tag.get("src") or imagem_tag.get("data-src")) if imagem_tag else None

        # Converte para link de afiliado DEPOIS de extrair dados e identificar origem
        link_afiliado = converter_link_afiliado(link_original, origem)
        if not link_afiliado:
            logger.warning(f"[divulgadorinteligente] Não foi possível gerar link de afiliado para: {link_original}")
            continue # Pula se não conseguir gerar o link

        # Verifica cache usando o link de afiliado
        if link_afiliado in ENVIADOS_CACHE:
            continue

        produtos.append({
            "nome": nome,
            "link": link_afiliado, # Usa o link de afiliado
            "origem": origem,
            "imagem": imagem,
            "preco_original": preco_original, # Adicionado preço original
            "preco_desconto": preco_desconto,
            "link_original": link_original # Guarda o original para referência
        })
        logger.debug(f"[divulgadorinteligente] Produto adicionado: {nome}")
    return produtos

def extrair_dados_promohub(soup, base_url):
    """Extrai dados do site promohub.com.br (versão do usuário)."""
    produtos = []
    # Usando o seletor do usuário
    offer_cards = soup.select("div.card, article.shadow-sm")
    logger.info(f"[promohub] Encontrados {len(offer_cards)} cards candidatos a ofertas (lógica do usuário).")
    for card in offer_cards:
        # Tentando pegar o link principal do card primeiro
        link_tag = card.select_one("a[href*='/p/'], a[href*='/l/']")
        # Se não achar, tenta o botão 'Pegar promoção'
        if not link_tag:
            link_tag = card.select_one("a:contains('Pegar promoção')")
        # Se ainda não achar, tenta um link genérico dentro do card
        if not link_tag:
             link_tag = card.find("a", href=True)

        if not link_tag:
            continue

        link_original = link_tag.get("href") # Renomeado para link_original
        if not link_original:
            continue

        # Resolve link interno do PromoHub
        if link_original.startswith('/'):
            link_original = urljoin(base_url, link_original)
            # Idealmente, visitaríamos este link para pegar o link externo real e a origem correta.
            # Por ora, a origem será incerta ou baseada em análise futura do link.
            logger.warning(f"[promohub] Link interno encontrado: {link_original}. A origem pode ser imprecisa.")

        nome_tag = card.select_one("h2, h3, p.title, p.font-semibold")
        nome = nome_tag.get_text(strip=True) if nome_tag else "Produto sem nome"

        preco_tag = card.select_one("span.price, div.price, p.text-xl, p.text-lg") # Seletores do código anterior
        preco = preco_tag.get_text(strip=True) if preco_tag else "N/D"
        # Limpa o preço
        preco = preco.split("R$")[-1].strip()
        if preco and not preco.startswith("R$"):
             preco = "R$ " + preco

        # Tenta pegar preço original
        preco_original_tag = card.select_one("span.original-price, s, del")
        preco_original = preco_original_tag.get_text(strip=True) if preco_original_tag else "N/D"

        imagem_tag = card.select_one("img")
        imagem = urljoin(base_url, imagem_tag.get("src") or imagem_tag.get("data-src")) if imagem_tag else None

        # Identifica a origem ANTES de converter
        origem = identificar_origem(link_original)
        # Se for link interno, a origem pode ser 'Outra' ou 'Desconhecida'

        # Converte para link de afiliado DEPOIS
        link_afiliado = converter_link_afiliado(link_original, origem)
        if not link_afiliado:
            logger.warning(f"[promohub] Não foi possível gerar link de afiliado para: {link_original}")
            continue

        # Verifica cache usando o link de afiliado
        if link_afiliado in ENVIADOS_CACHE:
            continue

        produtos.append({
            "nome": nome,
            "link": link_afiliado, # Usa o link de afiliado
            "origem": origem,
            "imagem": imagem,
            "preco_original": preco_original, # Adicionado preço original
            "preco_desconto": preco,
            "link_original": link_original # Guarda o original
        })
        logger.debug(f"[promohub] Produto adicionado: {nome}")
    return produtos

# --- Função Principal de Busca (Estrutura do código completo anterior) ---
def buscar_produtos():
    """Busca produtos nos sites de origem e extrai informações."""
    global ENVIADOS_CACHE # Acesso à variável global para leitura no filtro final
    produtos_encontrados_total = []
    logger.info(f"Iniciando busca em {len(URLS_FONTE)} fontes...")

    for site_key, site_url in URLS_FONTE.items():
        logger.info(f"Acessando {site_url} ({site_key})...")
        try:
            response = requests.get(site_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            produtos_site = []
            if site_key == "divulgadorinteligente":
                # Chama a função de extração integrada (versão do usuário)
                produtos_site = extrair_dados_divulgadorinteligente(soup, site_url)
            elif site_key == "promohub":
                # Chama a função de extração integrada (versão do usuário)
                produtos_site = extrair_dados_promohub(soup, site_url)
            else:
                logger.warning(f"Nenhuma função de extração definida para a chave de site: {site_key}")

            logger.info(f"Encontradas {len(produtos_site)} novas ofertas em {site_key} (antes do filtro final).")
            produtos_encontrados_total.extend(produtos_site)

        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao acessar {site_url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de requisição ao acessar {site_url}: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao processar {site_url}: {e}", exc_info=True)

    logger.info(f"Busca concluída. Total de {len(produtos_encontrados_total)} ofertas encontradas antes do filtro final.")
    # Filtra novamente por cache aqui para garantir
    produtos_filtrados = [p for p in produtos_encontrados_total if p["link"] not in ENVIADOS_CACHE]
    logger.info(f"{len(produtos_filtrados)} ofertas após filtro final de cache.")

    return produtos_filtrados

# --- Funções de Envio para o Telegram (Integrando a do último código do usuário) ---
# Renomeada para manter consistência com o resto do script
async def enviar_produto_telegram(produto):
    """Formata e envia uma única oferta para o Telegram (versão do usuário)."""
    global bot, GROUP_ID # Acesso às variáveis globais
    try:
        # Formatando a legenda como na função do usuário
        legenda = (
            f"🔥 <b>{produto.get('nome', 'Oferta Imperdível!')}</b>\n\n"
            f"🏬 Loja: <i>{produto.get('origem', 'Desconhecida')}</i>\n"
        )
        preco_original_fmt = produto.get("preco_original", "N/D").strip()
        preco_desconto_fmt = produto.get("preco_desconto", "N/D").strip()

        if preco_original_fmt != "N/D" and preco_original_fmt != preco_desconto_fmt:
             legenda += f"💸 De: <s>{preco_original_fmt}</s>\n"
        if preco_desconto_fmt != "N/D":
             legenda += f"👉 Por: <b>{preco_desconto_fmt}</b>\n\n"
        else:
             legenda += "\n"

        legenda += f"🔗 <a href='{produto['link']}'>Clique aqui para comprar</a>\n\n"
        # TODO: Substitua 'seugrupo' pelo nome real do seu grupo/canal ou remova/ajuste a linha
        legenda += f"📢 Compartilhe com amigos!\n👉 <a href='https://t.me/seugrupo'>Seu Grupo VIP</a>"

        imagem = produto.get('imagem')
        if imagem:
            logger.info(f"Enviando produto com imagem: {produto['nome']}")
            await bot.send_photo(
                chat_id=GROUP_ID,
                photo=imagem,
                caption=legenda,
                parse_mode=ParseMode.HTML
            )
        else:
            logger.info(f"Enviando produto sem imagem: {produto['nome']}")
            await bot.send_message(
                chat_id=GROUP_ID,
                text=legenda,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
        # Removido log duplicado, o log principal está em verificar_e_enviar_ofertas
        return True # Indica sucesso no envio
    except TelegramError as e:
        logger.error(f"Erro do Telegram ao enviar '{produto['nome']}': {e}")
        # Adicionando tratamentos de erro do código completo anterior
        if "Forbidden: bot was blocked by the user" in str(e):
             logger.error("O bot foi bloqueado ou removido do grupo/canal. Verifique as permissões.")
        elif "chat not found" in str(e):
             logger.error(f"Chat ID {GROUP_ID} não encontrado. Verifique o ID do grupo/canal.")
        elif "wrong file identifier/HTTP URL specified" in str(e) and imagem:
             logger.error(f"URL da imagem inválida ou inacessível: {imagem}")
             logger.info(f"Tentando enviar '{produto['nome']}' sem a imagem...")
             try:
                 await bot.send_message(chat_id=GROUP_ID, text=legenda, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                 return True # Sucesso no fallback
             except Exception as fallback_e:
                 logger.error(f"Erro ao tentar enviar sem imagem: {fallback_e}")
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar '{produto['nome']}' para o Telegram: {e}", exc_info=True)

    return False # Indica falha no envio

# --- Função de Verificação e Envio (Estrutura do código completo anterior) ---
async def verificar_e_enviar_ofertas():
    """Verifica o horário, busca ofertas e envia as novas para o Telegram."""
    global ENVIADOS_CACHE, FUSO_HORARIO_BRASILIA, HORARIO_INICIO_ENVIO, HORARIO_FIM_ENVIO, SCHEDULE_INTERVAL_MINUTES, MAX_CACHE_SIZE # Declarando acesso às globais

    agora_brasilia = datetime.now(FUSO_HORARIO_BRASILIA)
    logger.info(f"Verificando horário: {agora_brasilia.strftime('%H:%M:%S')} (Brasília)")

    if not (HORARIO_INICIO_ENVIO <= agora_brasilia.hour < HORARIO_FIM_ENVIO):
        logger.info(f"Fora do horário de envio ({HORARIO_INICIO_ENVIO:02d}h - {HORARIO_FIM_ENVIO:02d}h). Próxima verificação em {SCHEDULE_INTERVAL_MINUTES} min.")
        return

    logger.info("Dentro do horário de envio. Iniciando busca de ofertas...")
    novos_produtos = buscar_produtos()

    if not novos_produtos:
        logger.info("Nenhuma nova oferta encontrada nesta verificação.")
        return

    logger.info(f"Enviando {len(novos_produtos)} novas ofertas para o Telegram...")
    enviados_nesta_rodada = 0
    for produto in novos_produtos:
        sucesso = await enviar_produto_telegram(produto)
        if sucesso:
            ENVIADOS_CACHE.add(produto['link']) # Adiciona o link de afiliado ao cache
            enviados_nesta_rodada += 1
            # Limpeza simples do cache
            if len(ENVIADOS_CACHE) > MAX_CACHE_SIZE:
                logger.info(f"Cache atingiu o tamanho máximo ({MAX_CACHE_SIZE}). Limpando os mais antigos...")
                cache_list = list(ENVIADOS_CACHE)
                ENVIADOS_CACHE = set(cache_list[len(cache_list)-MAX_CACHE_SIZE:])

            await asyncio.sleep(3) # Pausa entre envios
        else:
            logger.error(f"Falha ao enviar produto: {produto['nome']}. Link não será adicionado ao cache.")
            await asyncio.sleep(5) # Pausa maior em caso de erro

    logger.info(f"Envio concluído. {enviados_nesta_rodada} ofertas enviadas nesta execução.")

# --- Loop Principal Assíncrono com Agendador (Estrutura do código completo anterior) ---
async def loop_principal():
    """Configura o agendamento e mantém o loop de verificação rodando."""
    global SCHEDULE_INTERVAL_MINUTES, HORARIO_INICIO_ENVIO, HORARIO_FIM_ENVIO, FUSO_HORARIO_BRASILIA # Acesso às globais
    logger.info("Configurando agendamento da tarefa...")
    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(
        lambda: asyncio.create_task(verificar_e_enviar_ofertas())
    )

    logger.info(f"🤖 Bot iniciado. Verificando ofertas a cada {SCHEDULE_INTERVAL_MINUTES} minutos entre {HORARIO_INICIO_ENVIO:02d}h e {HORARIO_FIM_ENVIO:02d}h ({FUSO_HORARIO_BRASILIA.key}).")

    logger.info("Executando a primeira verificação de ofertas...")
    await verificar_e_enviar_ofertas()
    logger.info("Primeira verificação concluída. Entrando no loop de agendamento.")

    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

# --- Ponto de Entrada do Script ---
if __name__ == "__main__":
    # Adicionado aviso sobre desativação de tarefas agendadas (conforme Knowledge)
    logger.warning("Aviso: A execução contínua e agendada pode ser instável ou interrompida devido a limitações de recursos do ambiente.")
    try:
        asyncio.run(loop_principal())
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Erro fatal no loop principal: {e}", exc_info=True)
        exit(1)
    finally:
        logger.info("Bot encerrado.")

