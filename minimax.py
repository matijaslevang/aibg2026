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


def _item_value(item, holder_hp=None, holder_max_hp=None, inventory_size=0, max_inventory=3):
    """Strategic value of a single item, optionally scaled by holder context."""
    n = (item.get('name') or '').lower()
    e = (item.get('effect') or '').lower()

    # Items lose value when inventory is full (can't pick up more)
    inv_factor = max(0.1, 1.0 - max(0, inventory_size - max_inventory + 1) * 0.5)

    if 'freeze' in n or 'freeze' in e:
        return 150 * inv_factor
    if 'heal' in n or 'life' in n or 'potion' in n:
        # Scale heal value by how injured the holder is
        if holder_hp is not None and holder_max_hp and holder_max_hp > 0:
            missing_hp_ratio = 1.0 - holder_hp / holder_max_hp
            base = 60 + 120 * missing_hp_ratio  # 60 when full HP, 180 when near death
        else:
            base = 100
        return base * inv_factor
    if 'confus' in n or 'confus' in e:
        return 55 * inv_factor
    return 45 * inv_factor


def _summon_threatened_cells(sm):
    """Return the set of (x, y) cells this summon can attack based on its known stats."""
    sx, sy = sm['x'], sm['y']
    atk = sm.get('atk', 20)
    if atk >= 35:
        # Blue Warrior (ATK~40): extended cross, range 2 in cardinal directions
        offsets = [(0, 1), (0, 2), (0, -1), (0, -2), (1, 0), (2, 0), (-1, 0), (-2, 0)]
    elif atk >= 23:
        # Ice Golem (ATK~25): asymmetric 6-cell pattern (diagonals + flanks)
        offsets = [(-1, -1), (0, -1), (-1, 0), (1, 0), (0, 1), (1, 1)]
    else:
        # Ice Cube (ATK~20): standard adjacent cross
        offsets = [(0, 1), (0, -1), (1, 0), (-1, 0)]
    return {(sx + dx, sy + dy) for dx, dy in offsets}


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
        self.spike_tiles = {}   # {(x,y): damage}

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
            # Items, monster cards, and entities all block movement but are tracked separately;
            # mark their cells as structurally walkable so pickup simulation can re-open them.
            if (not _none(field.get('Entity')) or not _none(field.get('MonsterCard'))
                    or not _none(field.get('Item'))):
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

        # Parse spike tiles from grid
        for field in grid_fields:
            if not isinstance(field, dict):
                continue
            obstacle = field.get('Obstacle')
            if not isinstance(obstacle, dict):
                continue
            dmg = int(obstacle.get('Damage', 0) or 0)
            if dmg <= 0:
                continue
            pos = field.get('Position', {})
            sx = int(pos.get('X', 0)) if isinstance(pos, dict) else 0
            sy = int(pos.get('Y', 0)) if isinstance(pos, dict) else 0
            s.spike_tiles[(sx, sy)] = dmg

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
                'inventory': [_parse_item(i) for i in (entity.get('Inventory') or []) if not _none(i)],
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
        s.summons      = [{**sm, 'inventory': list(sm.get('inventory', []))} for sm in self.summons]
        s.floor_items  = dict(self.floor_items)
        s.floor_cards  = dict(self.floor_cards)
        s.spike_tiles  = self.spike_tiles  # shared, never mutated
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
        if not self._structurally_walkable(x, y):
            return False
        if (x, y) in self.occupied:
            return False
        if (x, y) in self.floor_items or (x, y) in self.floor_cards:
            return False
        return True

    # ── Action generation ─────────────────────────────────────────────────────

    def move_options(self, player_id):
        """All reachable destinations in each cardinal direction. Snow tiles cost 2 (including the starting tile)."""
        me = self.players[player_id]
        px, py, max_d = me['x'], me['y'], me['move_dist']
        # Standing on a snow tile burns 1 MP before you take your first step
        if self._base is not None and 0 <= py < len(self._base) and 0 <= px < len(self._base[py]):
            if self._base[py][px] == 2:
                max_d -= 1
        options = []
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            remaining = max_d
            cx, cy = px, py
            while remaining > 0:
                nx, ny = cx + dx, cy + dy
                if not self._structurally_walkable(nx, ny):
                    break
                if (nx, ny) in self.occupied:
                    break
                if (nx, ny) in self.floor_items or (nx, ny) in self.floor_cards:
                    break
                cost = 2 if self._base[ny][nx] == 2 else 1
                if cost > remaining:
                    break
                remaining -= cost
                cx, cy = nx, ny
                # Never stop on a spike tile — keep walking to clear it or skip this stop
                if (cx, cy) not in self.spike_tiles:
                    options.append((cx, cy))
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
        # Item layout resets every 20 turns; new positions are unknown so clear them
        if s.turn % 20 == 0:
            s.floor_items.clear()
            s.floor_cards.clear()
        me = s.players[player_id]
        t  = action['type']

        if t == 'move':
            ox, oy = me['x'], me['y']
            tx, ty = action['x'], action['y']
            dx = 0 if tx == ox else (1 if tx > ox else -1)
            dy = 0 if ty == oy else (1 if ty > oy else -1)
            cx, cy = ox + dx, oy + dy
            while True:
                me['hp'] -= s.spike_tiles.get((cx, cy), 0)
                if cx == tx and cy == ty:
                    break
                cx += dx
                cy += dy
            s.occupied.discard((ox, oy))
            me['x'], me['y'] = tx, ty
            s.occupied.add((tx, ty))

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


def zone_proximity(x, turn, lookahead, board_w, decay_tiles=8):
    """
    0.0–1.0 danger score per phase: spatial proximity to that phase's boundary ×
    linear temporal ramp (0 at turn 0 → 1.0 at the turn tiles fall off).
    Returns the max across all phases.
    """
    t = turn + lookahead
    best = 0.0

    for phase_turn, boundary in ((15, 3), (30, 6)):
        # Scales from 0 at game start to 1.0 exactly when that phase activates
        turn_factor = min(1.0, t / phase_turn)
        if turn_factor == 0.0:
            continue

        left, right = boundary, board_w - boundary
        if x < left or x >= right:
            dist_factor = 1.0          # already inside the future danger zone
        else:
            dist = min(x - left, right - 1 - x)
            dist_factor = max(0.0, 1.0 - dist / decay_tiles)

        best = max(best, turn_factor * dist_factor)

    return best


# ─────────────────────────── Evaluation function ────────────────────────────

def evaluate(state, my_id, lookahead, avoid_xy=frozenset()):
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

    # HP advantage
    score += (me['hp'] - opp['hp']) * 2.0

    # Zone safety (linear ramp: 0 at turn 0 → 1.0 at phase turn)
    me_prox  = zone_proximity(me['x'],  state.turn, lookahead, state.board_w)
    opp_prox = zone_proximity(opp['x'], state.turn, lookahead, state.board_w)
    if me_prox > 0:
        score -= 600 * me_prox
        if any('freeze' in (i.get('name') or '').lower() for i in opp['inventory']):
            score -= 1200 * me_prox
    if opp_prox > 0:
        score += 400 * opp_prox
        if any('freeze' in (i.get('name') or '').lower() for i in me['inventory']):
            score += 2500 * opp_prox

    # Gravity toward safe center (both axes)
    cx = state.board_w // 2
    cy = state.board_h // 2
    score += (abs(opp['x'] - cx) - abs(me['x'] - cx)) * 1.5
    score += (abs(opp['y'] - cy) - abs(me['y'] - cy)) * 1.5

    # Aggression: weight scales up as the zone closes in on either player
    dist = abs(me['x'] - opp['x']) + abs(me['y'] - opp['y'])
    zone_pressure   = max(me_prox, opp_prox)
    aggr_weight     = 2.0 * (1.0 + zone_pressure)
    score -= dist * (aggr_weight if me['hp'] >= opp['hp'] else -1.0)

    # Mobility: more reachable tiles = more options = safer
    my_moves  = len(state.move_options(my_id))
    opp_moves = len(state.move_options(opp_id))
    score += (my_moves - opp_moves) * 12

    # Confusion penalty — confused movement is reversed and may be random
    if me['statuses'].get('Confused') or me['statuses'].get('Confusion'):
        score -= 150
    if opp['statuses'].get('Confused') or opp['statuses'].get('Confusion'):
        score += 100

    # Frozen is accounted for in generate_actions (only skip allowed), but penalise in eval too
    if opp['statuses'].get('Frozen'):
        score += 200

    # Inventory item values (context-aware)
    inv_sz_me  = len(me['inventory'])
    inv_sz_opp = len(opp['inventory'])
    for item in me['inventory']:
        score += _item_value(item, me['hp'], me['max_hp'], inv_sz_me)
    for item in opp['inventory']:
        score -= _item_value(item, opp['hp'], opp['max_hp'], inv_sz_opp) * 0.8

    # Confusion scroll wall bonus: each wall-adjacent direction the opponent has means
    # a reversed move hits a wall → random movement instead of controlled movement
    opp_wall_dirs = sum(1 for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]
                        if not state._structurally_walkable(opp['x']+dx, opp['y']+dy))
    me_wall_dirs  = sum(1 for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]
                        if not state._structurally_walkable(me['x']+dx, me['y']+dy))
    for item in me['inventory']:
        if 'confus' in (item.get('name') or '').lower() or 'confus' in (item.get('effect') or '').lower():
            score += opp_wall_dirs * 25
    for item in opp['inventory']:
        if 'confus' in (item.get('name') or '').lower() or 'confus' in (item.get('effect') or '').lower():
            score -= me_wall_dirs * 20

    # Monster card values: ready-to-summon cards are especially strong
    for card in (me['cards'] or []):
        if card:
            score += 100 if card['cooldown_counter'] == 0 else 35
    for card in (opp['cards'] or []):
        if card:
            score -= 75 if card['cooldown_counter'] == 0 else 25

    # Floor item/card proximity: only value loot reachable before the next reset
    turns_until_reset = 20 - (state.turn % 20) if state.turn % 20 != 0 else 20
    my_spd  = max(1, me['move_dist'])
    opp_spd = max(1, opp['move_dist'])

    for (ix, iy), field in state.floor_items.items():
        my_d  = abs(me['x'] - ix)  + abs(me['y'] - iy)
        opp_d = abs(opp['x'] - ix) + abs(opp['y'] - iy)
        my_reachable  = -(-my_d  // my_spd)  < turns_until_reset  # ceil div
        opp_reachable = -(-opp_d // opp_spd) < turns_until_reset
        if not my_reachable and not opp_reachable:
            continue
        v = _item_value(_parse_item(field.get('Item', {})),
                        me['hp'], me['max_hp'], len(me['inventory'])) * 0.4
        if my_reachable:
            score += v * max(0.0, 1.0 - my_d  / 10)
        if opp_reachable:
            score -= v * max(0.0, 1.0 - opp_d / 10) * 0.7

    for (cx_, cy_), _ in state.floor_cards.items():
        my_d  = abs(me['x'] - cx_)  + abs(me['y'] - cy_)
        opp_d = abs(opp['x'] - cx_) + abs(opp['y'] - cy_)
        my_reachable  = -(-my_d  // my_spd)  < turns_until_reset
        opp_reachable = -(-opp_d // opp_spd) < turns_until_reset
        if not my_reachable and not opp_reachable:
            continue
        v = 80 * 0.4
        if my_reachable:
            score += v * max(0.0, 1.0 - my_d  / 10)
        if opp_reachable:
            score -= v * max(0.0, 1.0 - opp_d / 10) * 0.7

    # Summon army strength
    my_pow  = sum(sm['hp'] + sm['atk'] for sm in state.summons if sm['owner_id'] == my_id)
    opp_pow = sum(sm['hp'] + sm['atk'] for sm in state.summons if sm['owner_id'] == opp_id)
    score  += (my_pow - opp_pow) * 0.4

    # Summon AoE danger: penalise standing in enemy summon attack zones
    my_pos  = (me['x'],  me['y'])
    opp_pos = (opp['x'], opp['y'])
    for sm in state.summons:
        threatened = _summon_threatened_cells(sm)
        if sm['owner_id'] == opp_id:
            if my_pos in threatened:
                score -= sm['atk'] * 4   # being in enemy summon AoE is very dangerous
            if opp_pos in threatened:
                score += sm['atk'] * 1   # friendly fire on opponent is a bonus
        else:
            if opp_pos in threatened:
                score += sm['atk'] * 3   # our summon threatens the opponent
            if my_pos in threatened:
                score -= sm['atk'] * 1   # our own summon hits us

    # Penalise standing on spike tiles
    my_spike  = state.spike_tiles.get((me['x'],  me['y']),  0)
    opp_spike = state.spike_tiles.get((opp['x'], opp['y']), 0)
    score -= my_spike  * 8
    score += opp_spike * 5

    # Penalise revisiting recent positions (breaks oscillation)
    if (me['x'], me['y']) in avoid_xy:
        score -= 250

    return score


# ─────────────────────────── Minimax ────────────────────────────────────────

def minimax(state, depth, alpha, beta, my_id, is_max, avoid_xy=frozenset()):
    if depth == 0 or state.is_game_over():
        return evaluate(state, my_id, depth, avoid_xy), None

    opp_id     = [pid for pid in state.players if pid != my_id][0]
    current_id = my_id if is_max else opp_id
    actions    = state.generate_actions(current_id)
    best_action = actions[0]

    if is_max:
        best_val = -float('inf')
        for action in actions:
            val, _ = minimax(state.apply_action(current_id, action),
                             depth - 1, alpha, beta, my_id, False, avoid_xy)
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
                             depth - 1, alpha, beta, my_id, True, avoid_xy)
            if val < best_val:
                best_val, best_action = val, action
            beta = min(beta, val)
            if beta <= alpha:
                break
        return best_val, best_action


# ─────────────────────────── Public entry point ─────────────────────────────

def decide(raw_state, my_id, depth=3, turn=0, recent_positions=None):
    """
    Call this on your turn with the raw server JSON and your player ID.
    `turn` is the current game turn counter (tracked externally).
    `recent_positions` is a list of (x,y) tuples visited in the last few turns.
    Returns the best action dict.
    """
    state = GameState.from_json(raw_state, turn=turn)
    avoid_xy = frozenset(recent_positions or [])
    val, action = minimax(state, depth, -float('inf'), float('inf'), my_id,
                          is_max=True, avoid_xy=avoid_xy)
    print(f"[minimax] turn={turn} score={val:.1f} action={action}", flush=True)
    return action
