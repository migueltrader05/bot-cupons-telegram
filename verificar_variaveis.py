import os

def get_env_var(name):
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"❌ Variável de ambiente obrigatória '{name}' não está definida.")
    return value

def verificar_todas():
    print("✅ Iniciando verificação das variáveis de ambiente...")

    TELEGRAM_TOKEN = get_env_var("TELEGRAM_TOKEN")
    print(f"✅ TELEGRAM_TOKEN encontrado: {TELEGRAM_TOKEN[:10]}...")

    GROUP_ID = get_env_var("GROUP_ID")
    print(f"✅ GROUP_ID encontrado: {GROUP_ID}")

    SHOPEE_PARTNER_ID = get_env_var("SHOPEE_PARTNER_ID")
    print(f"✅ SHOPEE_PARTNER_ID encontrado: {SHOPEE_PARTNER_ID}")

    SHOPEE_PARTNER_KEY = get_env_var("SHOPEE_PARTNER_KEY")
    print(f"✅ SHOPEE_PARTNER_KEY encontrado: {SHOPEE_PARTNER_KEY[:10]}...")

    print("🎉 Todas as variáveis estão OK!")

if __name__ == "__main__":
    verificar_todas()
