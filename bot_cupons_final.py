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
        logger.error(f"Erro Crítico: Variável de ambiente obrigatória '{var_name}' não definida.")
        raise ValueError(f"Variável de ambiente obrigatória '{var_name}' não definida.")
    if value is None and default is not None:
        logger.warning(f"Variável de ambiente '{var_name}' não definida, usando valor padrão: '{default}'.")
    return value

try:
    TELEGRAM_TOKEN = get_env_variable("TELEGRAM_TOKEN")
    GROUP_ID = int(get_env_variable("GROUP_ID"))
    # TODO: Verifique se estas URLs são a forma correta de gerar links de afiliado ou se são apenas a base.
    # A lógica de geração de links abaixo pode precisar ser ajustada.
    SHOPEE_AFILIADO_URL_BASE = get_env_variable("SHOPEE_AFILIADO_URL", required=False) # Tornando opcional por enquanto
    ML_AFILIADO_URL_BASE = get_env_variable("ML_AFILIADO_URL", required=False) # Tornando opcional por enquanto
    AMAZON_AFILIADO_ID = get_env_variable("AMAZON_AFILIADO_ID", default="maxx0448-20")
    SCHEDULE_INTERVAL_MINUTES = int(get_env_variable("SCHEDULE_INTERVAL_MINUTES", default=10))
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
URLS_FONTE = [
    "https://www.divulgadorinteligente.com/pachecoofertas",
    "https://promohub.com.br"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
REQUEST_TIMEOUT = 15 # Aumentando um pouco o timeout

# --- Funções Auxiliares --- 
def converter_link_afiliado(link_original):
    """Converte um link original para um link de afiliado baseado na origem."""
    if not link_original:
        return None

    try:
        if "amazon.com.br" in link_original:
            # Lógica para Amazon: Adiciona a tag de afiliado
            if "tag=" in link_original:
                # Se já tiver uma tag, verificar se é a nossa? Por enquanto, vamos apenas retornar.
                # Poderia substituir a tag existente se necessário.
                return link_original
            separador = "&" if "?" in link_original else "?"
            return f"{link_original}{separador}tag={AMAZON_AFILIADO_ID}"

        elif "shopee.com.br" in link_original or "shopee.com" in link_original:
            # TODO: Implementar a lógica CORRETA de afiliação da Shopee.
            # Geralmente envolve pegar o link original e adicionar parâmetros ou usar uma API específica.
            # A linha abaixo é um placeholder e PROVAVELMENTE INCORRETA.
            # return SHOPEE_AFILIADO_URL_BASE # Exemplo INCORRETO
            logger.warning(f"Lógica de afiliação Shopee não implementada. Usando link original: {link_original}")
            return link_original # Retornando original por enquanto

        elif "mercadolivre.com.br" in link_original or "mercadolivre.com" in link_original:
            # TODO: Implementar a lógica CORRETA de afiliação do Mercado Livre.
            # Pode envolver redirecionamento ou adição de parâmetros.
            # A linha abaixo é um placeholder e PROVAVELMENTE INCORRETA.
            # return ML_AFILIADO_URL_BASE # Exemplo INCORRETO
            logger.warning(f"Lógica de afiliação Mercado Livre não implementada. Usando link original: {link_original}")
            return link_original # Retornando original por enquanto

        else:
            # Se não for de nenhuma loja conhecida, retorna o link original
            return link_original
    except Exception as e:
        logger.error(f"Erro ao tentar converter link de afiliado para '{link_original}': {e}")
        return link_original # Retorna o original em caso de erro

def identificar_origem(link):
    """Identifica a loja de origem baseado no link."""
    if not link: return "Desconhecida"
    if "shopee.com" in link: return "Shopee"
    if "mercadolivre.com" in link: return "Mercado Livre"
    if "amazon.com" in link: return "Amazon"
    # TODO: Adicionar outras lojas se necessário (Magalu, Americanas, etc.)
    return "Outra"

# --- Função Principal de Busca --- 
def buscar_produtos():
    """Busca produtos nos sites de origem e extrai informações."""
    produtos_encontrados = []
    logger.info(f"Iniciando busca em {len(URLS_FONTE)} fontes...")

    for site_url in URLS_FONTE:
        logger.info(f"Acessando {site_url}...")
        try:
            response = requests.get(site_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status() # Levanta erro para status HTTP 4xx ou 5xx
            soup = BeautifulSoup(response.text, 'html.parser')

            # TODO: INSPECIONAR O HTML DOS SITES E AJUSTAR OS SELETORES ABAIXO!
            # A lógica a seguir é um EXEMPLO GENÉRICO e PRECISA SER ADAPTADA.
            # Você precisa encontrar os elementos que contêm CADA oferta individualmente.
            # Exemplo: Se cada oferta está numa <div class="produto">:
            # itens_oferta = soup.select("div.produto")
            # Se estiverem em <li> dentro de uma <ul id="lista-ofertas">:
            # itens_oferta = soup.select("ul#lista-ofertas > li")

            # Placeholder - Iterando sobre todos os links como no código original, MAS ISSO NÃO É O IDEAL.
            # SUBSTITUA PELA LÓGICA COM SELETORES ESPECiFICOS ACIMA.
            links_encontrados = soup.find_all("a", href=True)
            logger.info(f"Encontrados {len(links_encontrados)} links em {site_url}. Processando...")

            for link_tag in links_encontrados: # Substitua 'links_encontrados' por 'itens_oferta' após ajustar seletores
                link_original = link_tag.get("href")
                if not link_original or not link_original.startswith(('http://', 'https://')):
                    continue # Ignora links inválidos ou relativos

                # TODO: Extrair dados REAIS do produto a partir do 'link_tag' ou do 'item_oferta'
                # Você precisará encontrar os elementos HTML dentro de cada oferta que contêm:
                # - Nome do produto (ex: link_tag.find('h2', class_='nome-produto').text)
                # - Preço original (ex: link_tag.find('span', class_='preco-antigo').text)
                # - Preço com desconto (ex: link_tag.find('span', class_='preco-atual').text)
                # - URL da imagem (ex: link_tag.find('img')['src'])

                # Placeholder para os dados - SUBSTITUA PELA EXTRAÇÃO REAL
                nome_produto = link_tag.get_text(strip=True) or "Produto sem nome"
                preco_original_str = "N/D" # Exemplo: "R$ 149,90"
                preco_desconto_str = "N/D" # Exemplo: "R$ 99,90"
                imagem_url = None # Exemplo: "https://.../imagem.jpg"

                # Tenta converter o link para afiliado
                link_afiliado = converter_link_afiliado(link_original)
                if not link_afiliado:
                    logger.warning(f"Não foi possível gerar link de afiliado para: {link_original}")
                    continue # Pula se não conseguir gerar o link

                origem = identificar_origem(link_afiliado) # Identifica a origem pelo link já convertido (ou original)

                # Verifica se o link já foi enviado
                if link_afiliado in ENVIADOS_CACHE:
                    # logger.debug(f"Link já enviado, pulando: {link_afiliado}")
                    continue

                produto = {
                    "nome": nome_produto,
                    "imagem": imagem_url,
                    "link": link_afiliado,
                    "preco_original": preco_original_str,
                    "preco_desconto": preco_desconto_str,
                    "origem": origem,
                    "link_original": link_original # Guarda o original para referência, se necessário
                }
                produtos_encontrados.append(produto)
                logger.debug(f"Produto adicionado: {produto['nome']} ({produto['origem']}) - {produto['link']}")

        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao acessar {site_url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Erro de requisição ao acessar {site_url}: {e}")
        except Exception as e:
            logger.error(f"Erro inesperado ao processar {site_url}: {e}", exc_info=True) # Adiciona traceback ao log

    logger.info(f"Busca concluída. {len(produtos_encontrados)} novas ofertas encontradas.")
    return produtos_encontrados

# --- Funções de Envio para o Telegram --- 
async def enviar_produto_telegram(produto):
    """Formata e envia uma única oferta para o Telegram."""
    # TODO: Ajustar o texto da legenda conforme desejado.
    legenda = f"""
🔥 <b>{produto['nome']}</b>

🏬 Loja: <i>{produto['origem']}</i>
💸 De: <s>{produto['preco_original']}</s>
👉 Por: <b>{produto['preco_desconto']}</b>

🔗 <a href='{produto['link']}'>Clique aqui para comprar</a>

📢 Compartilhe com amigos!
👉 <a href='https://t.me/seugrupo'>Seu Grupo VIP</a>
""" # TODO: Substitua 'seugrupo' pelo nome real do seu grupo/canal

    try:
        if produto.get('imagem'): # Usa .get() para segurança caso a chave não exista
            logger.info(f"Enviando produto com imagem: {produto['nome']}")
            await bot.send_photo(
                chat_id=GROUP_ID,
                photo=produto['imagem'],
                caption=legenda,
                parse_mode=ParseMode.HTML
            )
        else:
            logger.info(f"Enviando produto sem imagem: {produto['nome']}")
            await bot.send_message(
                chat_id=GROUP_ID,
                text=legenda,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False # Habilita preview do link
            )
        return True # Indica sucesso no envio
    except TelegramError as e:
        logger.error(f"Erro do Telegram ao enviar '{produto['nome']}': {e}")
        if "Forbidden: bot was blocked by the user" in str(e):
             logger.error("O bot foi bloqueado ou removido do grupo/canal. Verifique as permissões.")
             # Considerar parar o script ou notificar administrador
        elif "chat not found" in str(e):
             logger.error(f"Chat ID {GROUP_ID} não encontrado. Verifique o ID do grupo/canal.")
        # TODO: Adicionar tratamento para outros erros comuns (ex: URL de imagem inválida)
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar '{produto['nome']}' para o Telegram: {e}", exc_info=True)

    return False # Indica falha no envio

async def verificar_e_enviar_ofertas():
    """Verifica o horário, busca ofertas e envia as novas para o Telegram."""
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
        if produto['link'] in ENVIADOS_CACHE:
            logger.warning(f"Link {produto['link']} encontrado novamente, mas já está no cache. Pulando.") # Não deveria acontecer se buscar_produtos já filtra
            continue

        sucesso = await enviar_produto_telegram(produto)
        if sucesso:
            ENVIADOS_CACHE.add(produto['link'])
            enviados_nesta_rodada += 1
            # Limpeza simples do cache para evitar crescimento indefinido
            if len(ENVIADOS_CACHE) > MAX_CACHE_SIZE:
                logger.info(f"Cache atingiu o tamanho máximo ({MAX_CACHE_SIZE}). Limpando os mais antigos...")
                # Converte para lista, remove os mais antigos, converte de volta para set
                cache_list = list(ENVIADOS_CACHE)
                ENVIADOS_CACHE = set(cache_list[len(cache_list)-MAX_CACHE_SIZE:])
                # Uma alternativa seria usar uma estrutura de dados mais adequada como collections.OrderedDict ou um cache LRU

            await asyncio.sleep(2) # Pausa entre envios para evitar flood
        else:
            logger.error(f"Falha ao enviar produto: {produto['nome']}. Link não será adicionado ao cache.")
            await asyncio.sleep(5) # Pausa maior em caso de erro

    logger.info(f"Envio concluído. {enviados_nesta_rodada} ofertas enviadas nesta execução.")

# --- Loop Principal Assíncrono com Agendador --- 
async def loop_principal():
    """Configura o agendamento e mantém o loop de verificação rodando."""
    logger.info("Configurando agendamento da tarefa...")
    # Agenda a função assíncrona corretamente usando asyncio.create_task
    schedule.every(SCHEDULE_INTERVAL_MINUTES).minutes.do(
        lambda: asyncio.create_task(verificar_e_enviar_ofertas())
    )

    logger.info(f"🤖 Bot iniciado. Verificando ofertas a cada {SCHEDULE_INTERVAL_MINUTES} minutos entre {HORARIO_INICIO_ENVIO:02d}h e {HORARIO_FIM_ENVIO:02d}h ({FUSO_HORARIO_BRASILIA.key}).")

    # Executa a primeira verificação imediatamente ao iniciar
    logger.info("Executando a primeira verificação de ofertas...")
    await verificar_e_enviar_ofertas()
    logger.info("Primeira verificação concluída. Entrando no loop de agendamento.")

    while True:
        schedule.run_pending()
        await asyncio.sleep(1) # Espera 1 segundo antes de verificar o agendador novamente

# --- Ponto de Entrada do Script ---
if __name__ == "__main__":
    try:
        asyncio.run(loop_principal())
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo usuário (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Erro fatal no loop principal: {e}", exc_info=True)
        exit(1)
    finally:
        logger.info("Bot encerrado.")

