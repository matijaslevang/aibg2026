"""Defensive strategy bot.
Usage: python bot_defensive.py <server_url> <game_id> <bot_name>

Heavily values HP and staying safe from the collapsing zone. Prioritises
mobility and loot collection over aggression — waits for the opponent to
make mistakes rather than forcing fights.
"""
from index import run
if __name__ == '__main__':
    run('defensive')
