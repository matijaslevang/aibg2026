OUTER_OUTER_TILES_FALL_ON_MOVE = 15
OUTER_INNER_TILES_FALL_ON_MOVE = 30
BRIDGES_FALL_ON_MOVE = 45

ITEMS_REFRESH_ON_MOVES = 20

def get_field_info(game_state, x, y):
    grid = game_state.get("Map", {}).get("Grid", {})
    field = next(
        item for item in grid
        if item["Position"]["X"] == x and item["Position"]["Y"] == y
    )
    field_type = field.get("FieldType", None)
    item_list = field.get("Item", None)
    monster_list = field.get("MonsterCard", None)
    entity_list = field.get("Entity", None)

    return [field_type, item_list, monster_list, entity_list]

def is_field_walkable(field_info):
    return field_info[0] != 6 and field_info[0] != 5 and not field_info[1] and not field_info[2] and not field_info[3]

def get_outer_outer_tiles():
    y_list = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    x_list = [0, 1, 2, 29, 30, 31]
    return [(x, y) for x in x_list for y in y_list]

def get_outer_inner_tiles():
    y_list = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    x_list = [3, 4, 5, 26, 27, 28]
    return [(x, y) for x in x_list for y in y_list]

def get_bridge_tiles():
    y_list = [0, 1, 2, 3, 12, 13, 14, 15]
    x_list = [6, 7, 8, 9, 10, 11, 12, 19, 20, 21, 22, 23, 24, 25]
    return [(x, y) for x in x_list for y in y_list]

def get_available_moves(game_state: dict, player_id: int):
    #               UP      DOWN    LEFT    RIGHT   
    directions = [[0, 1], [0, -1], [-1, 0], [1, 0]]
    current_position = game_state.get('Players', {}).get(player_id, {}).get('Position', {})
    current_x = current_position.get("X")
    current_y = current_position.get("Y")

    legal_positions = []

    for direction in directions:
        move_strength = 4
        temp_x = current_x
        temp_y = current_y
        while move_strength > 0:
            current_field_info = get_field_info(game_state, temp_x, temp_y)
            if current_field_info[0] == 2: # if current field is snow, move strength falls
                move_strength -= 1
            
            temp_x += direction[0]
            temp_y += direction[1]

            move_strength -= 1
            new_field_info = get_field_info(game_state, temp_x, temp_y)
            if new_field_info[0] == 2: # if new field is snow, move strength falls
                move_strength -= 1

            if is_field_walkable(new_field_info) and move_strength >= 0:
                legal_positions.append({"X":temp_x, "Y":temp_y})
            else:
                break
    return legal_positions

            


def get_when_items_refreshing(turn_counter: int):
    return ITEMS_REFRESH_ON_MOVES - (turn_counter % ITEMS_REFRESH_ON_MOVES)

def get_inventory(game_state: dict, player_id: int):
    players = game_state.get("Players", {})
    if players:
        player_info = players.get(player_id, {})
        if player_info:
            inventory = player_info.get('Inventory', {})
            if inventory:
                return inventory
    print("Error getting inventory")
    return None

def get_summons(game_state: dict, player_id: int):
    players = game_state.get("Players", {})
    if players:
        player_info = players.get(player_id, {})
        if player_info:
            inventory = player_info.get('Cards', {})
            if inventory:
                return inventory
    print("Error getting inventory")
    return None

