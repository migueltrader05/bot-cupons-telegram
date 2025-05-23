#!/bin/bash

echo "✅ Iniciando instalação das dependências..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Iniciando o bot..."
python bot_cupons_final.py


