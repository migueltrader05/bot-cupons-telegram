#!/bin/bash
pip uninstall -y python-telegram-bot telegram urllib3
pip install -r requirements.txt
python3 bot_cupons_final.py
