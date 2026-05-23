import requests # type: ignore

SERVER_URL = "http://localhost:8080"

def move(game_id: int, player_id: int, new_x: int, new_y: int):
    url = f"{SERVER_URL}/player/move/gameId/{game_id}"
    body = {"playerId": player_id, "newPosition": {"X": new_x, "Y": new_y}}
    response = requests.put(url, json=body)
    return response.json() if response.status_code == 200 else None

def attack(game_id: int, attacker_id: int, attacked_id: int):
    url = f"{SERVER_URL}/player/{attacker_id}/attack/{attacked_id}/gameId/{game_id}"
    response = requests.put(url)
    return response.json() if response.status_code == 200 else None

def use_item(game_id: int, player_id: int, item_id: int):
    url = f"{SERVER_URL}/player/{player_id}/use-item/{item_id}/gameId/{game_id}"
    response = requests.put(url)
    return response.json() if response.status_code == 200 else None

def pick_up_monster_card(game_id: int, player_id: int, field_info):
    url = f"{SERVER_URL}/map/pickup/{player_id}/gameId/{game_id}"
    response = requests.put(url, json=field_info)
    return response.json() if response.status_code == 200 else None

def pick_up_item(game_id: int, player_id: int, field_info):
    url = f"{SERVER_URL}/player/pickup/{player_id}/gameId/{game_id}"
    response = requests.put(url, json=field_info)
    return response.json() if response.status_code == 200 else None

def summon(game_id: int, player_id: int, card_id: int, summoning_on_x: int, summoning_on_y: int):
    url = f"{SERVER_URL}/map/{player_id}/summon/{card_id}/gameId/{game_id}"
    body = {"X": summoning_on_x, "Y": summoning_on_y}
    response = requests.put(url, json=body)
    return response.json() if response.status_code == 200 else None
