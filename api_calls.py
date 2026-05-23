import requests # type: ignore

SERVER_URL = "http://localhost:8080"

def move(game_id: int, player_id: int, new_x: int, new_y: int):
    url = f"{SERVER_URL}/player/move/gameId/{game_id}"
    body = {"playerId": player_id, "newPosition": {"X": new_x, "Y": new_y}}
    print(f"Submitting move: x:{new_x}, y:{new_y}", flush=True)
    response = requests.put(url, json=body)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

def attack(game_id: int, attacker_id: int, attacked_id: int):
    url = f"{SERVER_URL}/player/{attacker_id}/attack/{attacked_id}/gameId/{game_id}"
    print(f"Submitting attack: attacker:{attacker_id} is attacking:{attacked_id}", flush=True)
    response = requests.put(url)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

def use_item(game_id: int, player_id: int, item_id: int):
    url = f"{SERVER_URL}/player/{player_id}/use-item/{item_id}/gameId/{game_id}"
    print(f"Submitting move: player:{player_id} is using item:{item_id}", flush=True)
    response = requests.put(url)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

def pick_up_monster_card(game_id: int, player_id: int, picking_up_x: int, picking_up_y: int):
    url = f"{SERVER_URL}/map/pickup/{player_id}/gameId/{game_id}"
    body = {"Position": {"X": picking_up_x, "Y": picking_up_y}}
    print(f"Submitting move: player:{player_id} is trying to pick up a monster card on x:{picking_up_x}, y:{picking_up_y}", flush=True)
    response = requests.put(url, json=body)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

def pick_up_item(game_id: int, player_id: int, field_info):
    url = f"{SERVER_URL}/player/pickup/{player_id}/gameId/{game_id}"
    body = {"FieldInfo": field_info }
    print(f"Submitting move: player:{player_id} is trying to pick up an item on field:{field_info}", flush=True)
    response = requests.put(url, json=body)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

def summon(game_id: int, player_id: int, card_id: int, summoning_on_x: int, summoning_on_y: int):
    url = f"{SERVER_URL}/map/{player_id}/summon/{card_id}/gameId/{game_id}"
    body = {"X": summoning_on_x, "Y": summoning_on_y}
    print(f"Submitting move: player{player_id} is summoning:{card_id} on x:{summoning_on_x}, y:{summoning_on_y}", flush=True)
    response = requests.put(url, json=body)
    print(f"Server response ({response.status_code}): {response.text}", flush=True)
    return response.json() if response.status_code == 200 else None

if __name__ == "__main__":
    url = f"http://localhost:8080/game/state/e86c1d33-e02f-41e5-bb11-a50baf6cbdaf"
    response = requests.get(url)
    print(response)





