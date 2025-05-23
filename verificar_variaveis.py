import os
import sys

def verificar_variavel(nome):
    valor = os.getenv(nome)
    if not valor:
        print(f"❌ Variável não definida: {nome}")
        return False
    else:
        print(f"✅ {nome} = {valor[:5]}... (ocultado)")
        return True

print("🔍 Verificando variáveis de ambiente necessárias...\n")

variaveis = [
    "TELEGRAM_TOKEN",
    "GROUP_ID",
    "SHOPEE_PARTNER_ID",
    "SHOPEE_PARTNER_KEY"
]

sucesso = True
for var in variaveis:
    if not verificar_variavel(var):
        sucesso = False

if not sucesso:
    print("\n🚫 Corrija as variáveis acima antes de continuar.")
    sys.exit(1)

print("\n✅ Todas as variáveis estão corretamente definidas!")
