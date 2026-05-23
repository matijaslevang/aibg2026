"""
Minimax with alpha-beta pruning adapted for Monster Hunt.
Real game: 32x16 board, Players/Map JSON from server.

Entry point: decide(raw_state, my_id, depth=3)
Returns an action dict:
  {'type': 'move',     'x': int, 'y': int}
  {'type': 'attack',   'target_kind': 'player'|'summon', 'target_id': id}
  {'type': 'use_item', 'item_id': id, '_item': dict}
  {'type': 'summon',   'card_id': id, '_card': dict, 'x': int, 'y': int}
  {'type': 'skip'}
"""

# items block movement, so they must be picked up to move onto that cell
# summons block movement and can be attacked like players, but have no inventory or cards and don't

from helper_fun import convert_to_grid

BOARD_W = 32
BOARD_H = 16


def _none(v):
    return v is None or v == 'None'


# ─────────────────────────── Parsing helpers ────────────────────────────────

def _parse_item(raw):
    if not isinstance(raw, dict):
        return {'id': raw, 'name': str(raw), 'effect': '', 'power': 0, 'duration': 0}
    return {
        'id':       raw.get('Id'),
        'name':     raw.get('Name', ''),
        'type':     raw.get('ItemType', ''),
        'effect':   raw.get('Effect', ''),
        'power':    int(raw.get('Power', 0) or 0),
        'duration': int(raw.get('Duration', 0) or 0),
    }


def _parse_card(raw):
    if not isinstance(raw, dict):
        return None
    monster = raw.get('Monster') or {}
    return {
        'id':               raw.get('Id'),
        'name':             raw.get('Name', ''),
        'cooldown':         int(raw.get('Cooldown', 5) or 5),
        'cooldown_counter': int(raw.get('CooldownCounter', 0) or 0),
        'monster_hp':       int(monster.get('Health', 30)) if isinstance(monster, dict) else 30,
        'monster_atk':      int(monster.get('AttackPower', 20)) if isinstance(monster, dict) else 20,
    }


# ─────────────────────────── Game state ─────────────────────────────────────

class GameState:
    """
    Lightweight game state for minimax simulation.

    _base   - shared static 2D grid (walls/obstacles only, never mutated)
    occupied - set of (x,y) blocked by entities (players + summons)
    players  - {int_id: player_dict}
    summons  - [summon_dict]
    """

    def __init__(self):
        self.board_w  = BOARD_W
        self.board_h  = BOARD_H
        self.turn     = 0
        self._base      = None   # List[List[int]], shared
        self.occupied   = set()
        self.players    = {}
        self.summons    = []
        self.floor_items = {}   # {(x,y): raw_field_dict}
        self.floor_cards = {}   # {(x,y): card_dict}

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def from_json(cls, raw, turn=0):
        s = cls()
        s.turn = turn

        map_data = raw.get('Map', {})
        grid_fields = map_data.get('Grid', []) if isinstance(map_data, dict) else []

        # Build base grid (walls/obstacles); mark entity positions as walkable
        raw_grid = convert_to_grid(map_data)
        entity_xy = set()
        for field in grid_fields:
            if not isinstance(field, dict):
                continue
            if not _none(field.get('Entity')) or not _none(field.get('MonsterCard')):
                pos = field.get('Position', {})
                if isinstance(pos, dict):
                    ex, ey = pos.get('X'), pos.get('Y')
                    if ex is not None and ey is not None:
                        entity_xy.add((int(ex), int(ey)))

        if raw_grid:
            s._base = [row[:] for row in raw_grid]
            for (ex, ey) in entity_xy:
                if 0 <= ey < len(s._base) and 0 <= ex < len(s._base[ey]):
                    s._base[ey][ex] = 1  # structurally walkable, just occupied

        # Parse players
        for pid_str, p in raw.get('Players', {}).items():
            pos = p.get('Position', {})
            pid = int(p.get('Id', pid_str))
            px = int(pos.get('X', 0)) if isinstance(pos, dict) else int(pos[0])
            py = int(pos.get('Y', 0)) if isinstance(pos, dict) else int(pos[1])
            s.occupied.add((px, py))
            s.players[pid] = {
                'id':        pid,
                'hp':        int(p.get('Health', 100)),
                'max_hp':    int(p.get('MaxHealth', 100)),
                'atk':       int(p.get('AttackPower', 30)),
                'atk_range': int(p.get('AttackRange', 1)),
                'move_dist': int(p.get('MaxMoveDistance', 4)),
                'x': px, 'y': py,
                'inventory': [_parse_item(i) for i in (p.get('Inventory') or []) if not _none(i)],
                'cards':     [_parse_card(c) for c in (p.get('Cards') or []) if not _none(c)],
                'statuses':  dict(p.get('ActiveStatuses') or {}),
                'is_first':  bool(p.get('First', False)),
            }

        # Parse floor items from grid
        for field in grid_fields:
            if not isinstance(field, dict):
                continue
            raw_item = field.get('Item')
            if _none(raw_item) or not isinstance(raw_item, dict):
                continue
            pos = field.get('Position', {})
            ix = int(pos.get('X', 0)) if isinstance(pos, dict) else 0
            iy = int(pos.get('Y', 0)) if isinstance(pos, dict) else 0
            s.floor_items[(ix, iy)] = field

        # Parse floor monster cards from grid
        for field in grid_fields:
            if not isinstance(field, dict):
                continue
            raw_card = field.get('MonsterCard')
            if _none(raw_card) or not isinstance(raw_card, dict):
                continue
            pos = field.get('Position', {})
            cx = int(pos.get('X', 0)) if isinstance(pos, dict) else 0
            cy = int(pos.get('Y', 0)) if isinstance(pos, dict) else 0
            parsed = _parse_card(raw_card)
            if parsed:
                s.floor_cards[(cx, cy)] = (parsed, field)

        # Parse summoned monsters from grid entity fields
        for field in grid_fields:
            if not isinstance(field, dict):
                continue
            entity = field.get('Entity')
            if _none(entity) or not isinstance(entity, dict):
                continue
            owner = entity.get('SummonedByPlayerId')
            if _none(owner):
                continue
            pos = field.get('Position', {})
            ex = int(pos.get('X', 0)) if isinstance(pos, dict) else 0
            ey = int(pos.get('Y', 0)) if isinstance(pos, dict) else 0
            s.summons.append({
                'id':       entity.get('Id'),
                'owner_id': int(owner),
                'x': ex, 'y': ey,
                'hp':  int(entity.get('Health', 20)),
                'atk': int(entity.get('AttackPower', 20)),
            })

        return s

    # ── Cloning (cheap: _base is shared) ─────────────────────────────────────

    def clone(self):
        s = GameState.__new__(GameState)
        s.board_w  = self.board_w
        s.board_h  = self.board_h
        s.turn     = self.turn
        s._base    = self._base       # shared reference, never modified
        s.occupied = set(self.occupied)
        # Deep-copy only the mutable per-player dicts
        s.players = {}
        for pid, p in self.players.items():
            cp = dict(p)
            cp['inventory'] = [dict(i) for i in p['inventory']]
            cp['cards']     = [dict(c) if c else None for c in p['cards']]
            cp['statuses']  = dict(p['statuses'])
            s.players[pid]  = cp
        s.summons      = [dict(sm) for sm in self.summons]
        s.floor_items  = dict(self.floor_items)
        s.floor_cards  = dict(self.floor_cards)
        return s

    # ── Grid helpers ──────────────────────────────────────────────────────────

    def _structurally_walkable(self, x, y):
        if x < 0 or y < 0 or x >= self.board_w or y >= self.board_h:
            return False
        if self._base is None:
            return True
        if y >= len(self._base) or x >= len(self._base[y]):
            return False
        return self._base[y][x] in (1, 2)

    def walkable(self, x, y):
        return self._structurally_walkable(x, y) and (x, y) not in self.occupied

    # ── Action generation ─────────────────────────────────────────────────────

    def move_options(self, player_id):
        """Up to 4 straight-line destinations (one per cardinal direction). Snow tiles cost 2."""
        me = self.players[player_id]
        px, py, max_d = me['x'], me['y'], me['move_dist']
        options = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            last = None
            remaining = max_d
            cx, cy = px, py
            while remaining > 0:
                nx, ny = cx + dx, cy + dy
                if not self._structurally_walkable(nx, ny):
                    break
                if (nx, ny) in self.occupied:
                    break
                cost = 2 if self._base[ny][nx] == 2 else 1
                if cost > remaining:
                    break
                remaining -= cost
                cx, cy = nx, ny
                last = (nx, ny)
            if last:
                options.append(last)
        return options

    def attack_targets(self, player_id):
        """Entities within attack range (excluding self and own summons)."""
        me = self.players[player_id]
        px, py, rng = me['x'], me['y'], me['atk_range']
        targets = []
        for pid, p in self.players.items():
            if pid != player_id and abs(p['x'] - px) + abs(p['y'] - py) <= rng:
                targets.append(('player', pid))
        for sm in self.summons:
            if sm['owner_id'] != player_id and abs(sm['x'] - px) + abs(sm['y'] - py) <= rng:
                targets.append(('summon', sm['id']))
        return targets

    def generate_actions(self, player_id):
        me = self.players[player_id]
        if me['statuses'].get('Frozen'):
            return [{'type': 'skip'}]

        actions = []

        # Attacks (evaluated first for better alpha-beta cutoffs)
        for kind, tid in self.attack_targets(player_id):
            actions.append({'type': 'attack', 'target_kind': kind, 'target_id': tid})

        # Use item
        for item in me['inventory']:
            actions.append({'type': 'use_item', 'item_id': item['id'], '_item': item})

        # Summon (card with cooldown_counter == 0, on any free adjacent cell)
        adj = [(me['x'] + dx, me['y'] + dy)
               for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]
               if self.walkable(me['x'] + dx, me['y'] + dy)]
        for card in me['cards']:
            if card and card['cooldown_counter'] == 0:
                for sx, sy in adj:
                    actions.append({'type': 'summon', 'card_id': card['id'], '_card': card,
                                    'x': sx, 'y': sy})

        # Pick up items and monster cards on current cell or adjacent cells
        for dx, dy in [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]:
            tx, ty = me['x'] + dx, me['y'] + dy
            if (tx, ty) in self.floor_items:
                actions.append({'type': 'pick_up_item', 'x': tx, 'y': ty, '_field': self.floor_items[(tx, ty)]})
            if (tx, ty) in self.floor_cards:
                card, raw_field = self.floor_cards[(tx, ty)]
                actions.append({'type': 'pick_up_card', 'x': tx, 'y': ty, '_card': card, '_field': raw_field})

        # Move
        for nx, ny in self.move_options(player_id):
            actions.append({'type': 'move', 'x': nx, 'y': ny})

        return actions or [{'type': 'skip'}]

    # ── State transition ──────────────────────────────────────────────────────

    def apply_action(self, player_id, action):
        s = self.clone()
        s.turn += 1
        me = s.players[player_id]
        t  = action['type']

        if t == 'move':
            s.occupied.discard((me['x'], me['y']))
            me['x'], me['y'] = action['x'], action['y']
            s.occupied.add((me['x'], me['y']))

        elif t == 'attack':
            dmg = me['atk']
            if action['target_kind'] == 'player':
                tid = action['target_id']
                if tid in s.players:
                    s.players[tid]['hp'] -= dmg
                    if s.players[tid]['hp'] <= 0:
                        s.occupied.discard((s.players[tid]['x'], s.players[tid]['y']))
            else:
                sid = action['target_id']
                new_summons = []
                for sm in s.summons:
                    if sm['id'] == sid:
                        sm = dict(sm)
                        sm['hp'] -= dmg
                        if sm['hp'] > 0:
                            new_summons.append(sm)
                        else:
                            s.occupied.discard((sm['x'], sm['y']))
                    else:
                        new_summons.append(sm)
                s.summons = new_summons

        elif t == 'use_item':
            item = action.get('_item', {})
            me['inventory'] = [i for i in me['inventory'] if i['id'] != action['item_id']]
            name   = (item.get('name')   or '').lower()
            effect = (item.get('effect') or '').lower()
            power  = item.get('power', 0) or 0
            if 'heal' in name or 'heal' in effect or 'life' in name:
                # Power is typically a percentage of max HP
                heal = int(me['max_hp'] * power / 100) if 0 < power <= 100 else (power or 50)
                me['hp'] = min(me['max_hp'], me['hp'] + heal)
            if 'freeze' in name or 'freeze' in effect:
                opp_ids = [pid for pid in s.players if pid != player_id]
                if opp_ids:
                    s.players[opp_ids[0]]['statuses']['Frozen'] = item.get('duration', 1)

        elif t == 'pick_up_item':
            pos = (action['x'], action['y'])
            if pos in s.floor_items:
                raw_field = s.floor_items.pop(pos)
                me['inventory'].append(_parse_item(raw_field.get('Item', {})))

        elif t == 'pick_up_card':
            pos = (action['x'], action['y'])
            if pos in s.floor_cards:
                card, _ = s.floor_cards.pop(pos)
                me['cards'].append(card)

        elif t == 'summon':
            card = action.get('_card', {})
            sx, sy = action['x'], action['y']
            s.summons.append({
                'id':       f"s{player_id}_{s.turn}",
                'owner_id': player_id,
                'x': sx, 'y': sy,
                'hp':  card.get('monster_hp', 30),
                'atk': card.get('monster_atk', 20),
            })
            s.occupied.add((sx, sy))
            for c in me['cards']:
                if c and c['id'] == action['card_id']:
                    c['cooldown_counter'] = c['cooldown']

        return s

    # ── Terminal check ────────────────────────────────────────────────────────

    def is_game_over(self):
        for p in self.players.values():
            if p['hp'] <= 0 or zone_danger(p['x'], p['y'], self.turn, 0, self.board_w):
                return True
        return self.turn >= 100


# ─────────────────────────── Zone danger (map shrinks) ──────────────────────

def zone_danger(x, _y, turn, lookahead, board_w):
    """True if cell (x,y) will be in a destroyed zone at turn+lookahead."""
    t = turn + lookahead
    if t >= 15 and (x < 3 or x >= board_w - 3):
        return True
    if t >= 30 and (x < 6 or x >= board_w - 6):
        return True
    # Turn 45: bridges collapse — update these X coords from your actual map
    # if t >= 45 and x in (15, 16):
    #     return True
    return False


def zone_proximity(x, turn, lookahead, board_w, decay_tiles=8, decay_turns=10):
    """
    0.0–1.0 proximity score combining distance to the danger boundary
    and how soon the next zone phase activates.
    Both factors must be non-zero for the result to be non-zero.
    """
    t = turn + lookahead

    # Determine active boundary and turns until next phase
    if t >= 30:
        left, right = 6, board_w - 6
        turns_until = 0  # already active
    elif t >= 15:
        left, right = 3, board_w - 3
        turns_until = max(0, 30 - t)
    else:
        left, right = 3, board_w - 3
        turns_until = max(0, 15 - t)

    # Turn-based urgency: ramps up over `decay_turns` turns before activation
    turn_factor = max(0.0, 1.0 - turns_until / decay_turns)
    if turn_factor == 0.0:
        return 0.0

    if x < left or x >= right:
        return turn_factor  # inside zone, full turn factor

    dist = min(x - left, right - 1 - x)
    dist_factor = max(0.0, 1.0 - dist / decay_tiles)
    return turn_factor * dist_factor


# ─────────────────────────── Evaluation function ────────────────────────────

def evaluate(state, my_id, lookahead):
    opp_ids = [pid for pid in state.players if pid != my_id]
    if not opp_ids:
        return 0.0
    opp_id = opp_ids[0]
    me  = state.players[my_id]
    opp = state.players[opp_id]

    # Terminal states
    if me['hp'] <= 0 or zone_danger(me['x'], me['y'], state.turn, 0, state.board_w):
        return -1e9
    if opp['hp'] <= 0 or zone_danger(opp['x'], opp['y'], state.turn, 0, state.board_w):
        return 1e9

    score = 0.0

    # HP advantage (weight 2)
    score += (me['hp'] - opp['hp']) * 2.0

    # Zone safety prediction (scaled by distance + turn proximity)
    me_prox  = zone_proximity(me['x'],  state.turn, lookahead, state.board_w)
    opp_prox = zone_proximity(opp['x'], state.turn, lookahead, state.board_w)
    if me_prox > 0:
        score -= 600 * me_prox
        if any('freeze' in (i.get('name') or '').lower() for i in opp['inventory']):
            score -= 1200 * me_prox  # opponent can freeze us while we're near the edge
    if opp_prox > 0:
        score += 400 * opp_prox
        if any('freeze' in (i.get('name') or '').lower() for i in me['inventory']):
            score += 2500 * opp_prox  # we can freeze them into the danger zone

    # Gravity toward safe center
    cx = state.board_w // 2
    score += (abs(opp['x'] - cx) - abs(me['x'] - cx)) * 1.5

    # Aggression: close in when ahead on HP, kite when behind
    dist = abs(me['x'] - opp['x']) + abs(me['y'] - opp['y'])
    score -= dist * (2.0 if me['hp'] >= opp['hp'] else -1.0)

    # Item values
    for item in me['inventory']:
        n = (item.get('name') or '').lower()
        score += 60 if ('heal' in n or 'life' in n) else 40
    for item in opp['inventory']:
        n = (item.get('name') or '').lower()
        if 'freeze' in n:
            score -= 80 if me_prox > 0 else 40

    # Summon army strength
    my_pow  = sum(sm['hp'] + sm['atk'] for sm in state.summons if sm['owner_id'] == my_id)
    opp_pow = sum(sm['hp'] + sm['atk'] for sm in state.summons if sm['owner_id'] == opp_id)
    score  += (my_pow - opp_pow) * 0.4

    return score


# ─────────────────────────── Minimax ────────────────────────────────────────

def minimax(state, depth, alpha, beta, my_id, is_max):
    if depth == 0 or state.is_game_over():
        return evaluate(state, my_id, depth), None

    opp_id     = [pid for pid in state.players if pid != my_id][0]
    current_id = my_id if is_max else opp_id
    actions    = state.generate_actions(current_id)
    best_action = actions[0]

    if is_max:
        best_val = -float('inf')
        for action in actions:
            val, _ = minimax(state.apply_action(current_id, action),
                             depth - 1, alpha, beta, my_id, False)
            if val > best_val:
                best_val, best_action = val, action
            alpha = max(alpha, val)
            if beta <= alpha:
                break
        return best_val, best_action
    else:
        best_val = float('inf')
        for action in actions:
            val, _ = minimax(state.apply_action(current_id, action),
                             depth - 1, alpha, beta, my_id, True)
            if val < best_val:
                best_val, best_action = val, action
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best_val, best_action


# ─────────────────────────── Public entry point ─────────────────────────────

def decide(raw_state, my_id, depth=3, turn=0):
    """
    Call this on your turn with the raw server JSON and your player ID.
    `turn` is the current game turn counter (tracked externally).
    Returns the best action dict.
    """
    state = GameState.from_json(raw_state, turn=turn)
    val, action = minimax(state, depth, -float('inf'), float('inf'), my_id, is_max=True)
    print(f"[minimax] turn={turn} score={val:.1f} action={action}", flush=True)
    return action
