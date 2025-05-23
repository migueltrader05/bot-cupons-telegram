import os
import sys

variaveis = [
    "TELEGRAM_TOKEN",
    "GROUP_ID",
    "SHOPEE_PARTNER_ID",
    "SHOPEE_PARTNER_KEY"
]

print("Verificando variáveis de ambiente:\n")

erro = False
for var in variaveis:
    valor = os.getenv(var)
    if valor:
        print(f"✅ {var}: OK")
    else:
        print(f"❌ {var}: NÃO DEFINIDA")
        erro = True

if erro:
    print("\nCorrija as variáveis acima no painel da Railway antes de continuar.")
    sys.exit(1)
else:
    print("\nTodas as variáveis estão corretamente definidas. Pronto para rodar o bot! 🚀")
