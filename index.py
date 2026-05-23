"""Monster Hunt Bot — Minimax strategy
Usage: python index.py <server_url> <game_id> <bot_name>
"""
import json
import requests
import sys
import time
from minimax import decide
import api_calls


def print_state(state):
    # Strip the Grid to keep output readable
    condensed = {k: v for k, v in state.items() if k != 'Map'}
    print(json.dumps(condensed, indent=2), flush=True)


class BotTemplate:
    def __init__(self, server_url, game_id, bot_name, preset='balanced'):
        self.server_url = server_url.rstrip('/')
        self.game_id    = game_id
        self.bot_name   = bot_name
        self.preset      = preset
        self.player_id       = None
        self.turn_count      = 0
        self.recent_positions = []   # last 4 positions for oscillation detection

    def get_game_state(self):
        url = f"{self.server_url}/game/state/{self.game_id}"
        try:
            response = requests.get(url, timeout=5)
            return response.json() if response.status_code == 200 else None
        except Exception:
            return None

    def find_my_player_id(self, game_state):
        for _, player in game_state.get('Players', {}).items():
            if player.get('Name') == self.bot_name:
                self.player_id = player.get('Id')
                return True
        return False

    def is_my_turn(self, game_state):
        if not game_state or not self.player_id:
            return False
        players   = game_state.get('Players', {})
        my_player = players.get(str(self.player_id)) or players.get(self.player_id)
        if not my_player:
            return False
        is_first = my_player.get('First', False)
        gs       = game_state.get('GameState', '')
        return (is_first and gs == 'Player1Turn') or (not is_first and gs == 'Player2Turn')

    def is_game_over(self, game_state):
        return not game_state or game_state.get('GameState', '') == 'Ending'

    def execute_action(self, action, is_confused=False, cur_pos=None):
        """Dispatch the minimax action to the correct API call."""
        if not action:
            return None
        gid, pid = self.game_id, self.player_id
        t = action.get('type')

        if t == 'move':
            tx, ty = action['x'], action['y']
            if is_confused and cur_pos:
                # Server reverses confused moves: send the mirror so we land where we intend
                px, py = cur_pos
                tx, ty = 2 * px - tx, 2 * py - ty
                print(f"[confused] flipping move to ({tx},{ty})", flush=True)
            return api_calls.move(gid, pid, tx, ty)
        elif t == 'attack':
            return api_calls.attack(gid, pid, action['target_id'])
        elif t == 'pick_up_item':
            return api_calls.pick_up_item(gid, pid, action['_field'])
        elif t == 'pick_up_card':
            return api_calls.pick_up_monster_card(gid, pid, action['_field'])
        elif t == 'use_item':
            return api_calls.use_item(gid, pid, action['item_id'])
        elif t == 'summon':
            return api_calls.summon(gid, pid, action['card_id'], action['x'], action['y'])
        else:
            print(f"[bot] skip / unknown action: {action}", flush=True)
            return None


def run(preset='balanced'):
    """Start the bot. Call with a preset name or run this file directly."""
    if len(sys.argv) < 4:
        print("Usage: python index.py <server_url> <game_id> <bot_name> [preset]")
        print("  preset: balanced (default) | aggressive | defensive | summoner")
        sys.exit(1)

    bot = BotTemplate(sys.argv[1], sys.argv[2], sys.argv[3], preset=preset)
    print(f"Strategy preset: {preset}", flush=True)

    while not (state := bot.get_game_state()) or not bot.find_my_player_id(state):
        time.sleep(0.5)

    print(f"Connected as Player {bot.player_id}\n", flush=True)

    state = bot.get_game_state()
    try:
        while state and not bot.is_game_over(state):
            if bot.is_my_turn(state):
                print(f"My turn! (turn {bot.turn_count})", flush=True)
                print_state(state)
                me  = state.get('Players', {}).get(str(bot.player_id), {})
                pos = me.get('Position', {})
                if isinstance(pos, dict) and 'X' in pos:
                    cur_xy = (int(pos['X']), int(pos['Y']))
                    bot.recent_positions.append(cur_xy)
                    if len(bot.recent_positions) > 4:
                        bot.recent_positions.pop(0)

                action = decide(state, bot.player_id, depth=4, turn=bot.turn_count,
                                recent_positions=bot.recent_positions, preset=bot.preset)

                me_raw   = state.get('Players', {}).get(str(bot.player_id), {})
                statuses = me_raw.get('ActiveStatuses') or {}
                confused = bool(statuses.get('Confused') or statuses.get('Confusion'))
                cur_xy   = (int(pos['X']), int(pos['Y'])) if isinstance(pos, dict) and 'X' in pos else None
                new_state = bot.execute_action(action, is_confused=confused, cur_pos=cur_xy)
                if isinstance(new_state, dict):
                    bot.turn_count += 1
                time.sleep(0.2)
                state = new_state if isinstance(new_state, dict) else bot.get_game_state()
            else:
                time.sleep(0.5)
                state = bot.get_game_state()
    except KeyboardInterrupt:
        print("\nBot stopped by user")


if __name__ == "__main__":
    preset = sys.argv[4] if len(sys.argv) > 4 else 'balanced'
    run(preset)
