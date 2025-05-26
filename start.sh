#!/bin/bash
pip install -r requirements.txt
python bot_cupons_final.py
git add requirements.txt start.sh
git commit -m "Corrige dependência do telegram-bot"
git push
