#!/bin/bash

pip uninstall -y python-telegram-bot
pip install python-telegram-bot==13.7 schedule requests
python bot_cupons_final.py
