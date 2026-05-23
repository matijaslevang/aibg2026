"""Summoner strategy bot.
Usage: python bot_summoner.py <server_url> <game_id> <bot_name>

Builds a summon army as the primary win condition. Cards are highly valued
and deployed eagerly — the bot keeps summons on the board to threaten the
opponent's movement and chip HP. Less focused on direct item collection.
"""
from index import run
run('summoner')
