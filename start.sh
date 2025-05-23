#!/bin/bash

pip install --upgrade --force-reinstall --no-cache-dir python-telegram-bot==13.7 schedule requests

echo "✅ Iniciando o bot de cupons..."
python bot_cupons_final.py

