"""Monster Hunt Bot - Python Template
Usage: python bot_template.py <server_url> <game_id> <bot_name>
See README.md for full API documentation
"""
import requests
import sys
import time
import random
from search import a_star_search
from helper_fun import convert_to_grid

class BotTemplate:
    def __init__(self, server_url, game_id, bot_name):
        self.server_url = server_url.rstrip('/')
        self.game_id = game_id
        self.bot_name = bot_name
        self.player_id = None
    
    def get_game_state(self):
        url = f"{self.server_url}/game/state/{self.game_id}"
        response = requests.get(url, timeout=5)
        return response.json() if response.status_code == 200 else None
    
    def find_my_player_id(self, game_state):
        players = game_state.get('Players', {})
        for player_id, player in players.items():
            if player.get('Name') == self.bot_name:
                self.player_id = player.get('Id')
                return True
        return False
    
    def is_my_turn(self, game_state):
        if not game_state or not self.player_id:
            return False
        players = game_state.get('Players', {})
        my_player = players.get(str(self.player_id)) or players.get(self.player_id)
        if not my_player:
            return False
        is_first = my_player.get('First', False)
        game_state_str = game_state.get('GameState', '')
        return (is_first and game_state_str == 'Player1Turn') or (not is_first and game_state_str == 'Player2Turn')
    
    def is_game_over(self, game_state):
        """Check if game has ended"""
        if not game_state:
            return False
        return game_state.get('GameState', '') == 'Ending'

    def submit_move(self, x, y):
        url = f"{self.server_url}/player/move/gameId/{self.game_id}"
        body = {"playerId": self.player_id, "newPosition": {"X": x, "Y": y}}
        response = requests.put(url, json=body, timeout=5)
        return response.json() if response.status_code == 200 else None

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python bot_template.py <server_url> <game_id> <bot_name>")
        sys.exit(1)
    
    bot = BotTemplate(sys.argv[1], sys.argv[2], sys.argv[3])
    
    while not (state := bot.get_game_state()) or not bot.find_my_player_id(state):
        time.sleep(0.5)
    
    print(f"Connected as Player {bot.player_id}\n")
    
    state = bot.get_game_state()
    try:
        while state and not bot.is_game_over(state):
            if bot.is_my_turn(state):
                print("My turn!")
                grid = convert_to_grid(state['Map'])

                poz_raw = state['Players'][str(bot.player_id)]['Position']
                if isinstance(poz_raw, dict):
                    poz = (poz_raw['Y'], poz_raw['X'])  # grid is grid[row=Y][col=X]
                else:
                    poz = (poz_raw[1], poz_raw[0])

                walkable = [
                    (r, c)
                    for r, row in enumerate(grid)
                    for c, cell in enumerate(row)
                    if cell == 1 and (r, c) != poz
                    and abs(r - poz[0]) + abs(c - poz[1]) <= 4
                ]
                dest = random.choice(walkable) if walkable else poz

                a_star_search(grid, poz, dest)
                new_state = bot.submit_move(dest[1], dest[0])  # API wants (X, Y)
                state = new_state if new_state else bot.get_game_state()
            else:
                time.sleep(0.5)
                state = bot.get_game_state()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
