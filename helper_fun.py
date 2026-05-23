

def convert_to_grid(board):
    grid = []
    for row in board:
        grid.append([1 if cell == 0 else 0 for cell in row])
    return grid