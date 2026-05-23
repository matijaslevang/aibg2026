def _is_none(value):
    return value is None or value == 'None'


def _to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_blocked_field(field):
    if not isinstance(field, dict):
        return False

    field_type = _to_int(field.get('FieldType'))
    obstacle = field.get('Obstacle')
    entity = field.get('Entity')
    monster_card = field.get('MonsterCard')

    if not _is_none(obstacle):
        return True
    if not _is_none(entity):
        return True
    if not _is_none(monster_card):
        return True
    if not _is_none(field.get('Item')):
        return True

    return field_type in (3, 5, 6)


def _field_position(field):
    if not isinstance(field, dict):
        return None, None

    pos = field.get('Position') or {}
    if isinstance(pos, dict):
        return _to_int(pos.get('X')), _to_int(pos.get('Y'))

    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return _to_int(pos[0]), _to_int(pos[1])

    return None, None


def convert_to_grid(board):
    """Convert a board/map payload into a 2D A* grid of 1 (walkable) and 0 (blocked)."""
    if board is None:
        return []

    if isinstance(board, dict):
        if 'Map' in board:
            return convert_to_grid(board['Map'])

        if 'Grid' in board and 'X' in board and 'Y' in board:
            return convert_to_grid(board['Grid'])

        if 'Grid' in board and isinstance(board['Grid'], list):
            return convert_to_grid(board['Grid'])

    if isinstance(board, list):
        if not board:
            return []

        first = board[0]
        if isinstance(first, list):
            return board

        if isinstance(first, dict) and 'Position' in first:
            width = 0
            height = 0
            for field in board:
                x, y = _field_position(field)
                if x is None or y is None:
                    continue
                width = max(width, x + 1)
                height = max(height, y + 1)

            if width == 0 or height == 0:
                return []

            grid = [[1 for _ in range(width)] for _ in range(height)]
            for field in board:
                x, y = _field_position(field)
                if x is None or y is None:
                    continue
                grid[y][x] = 0 if _is_blocked_field(field) else 1
            return grid

    return []
