"""Aggressive strategy bot.
Usage: python bot_aggressive.py <server_url> <game_id> <bot_name>

Prioritises chasing the opponent and dealing damage. Less concerned with
zone safety — will push fights even near the boundary. Strong summon army
amplifies attack pressure.
"""
from index import run
if __name__ == '__main__':
    run('aggressive')
