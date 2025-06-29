import pygame
import chess
import requests
import sys
import uuid
import time
from random import choice

pygame.init()

SERVER_URL = 'http://localhost:8889'
SQUARE_SIDE = 60
APP_TITLE = "Network PvP Chess"

BOARD_THEMES = [
    ("Lichess Green", {'light': (238, 238, 210), 'dark': (118, 150, 86)}),
    ("Lichess Blue", {'light': (222, 227, 230), 'dark': (140, 162, 173)}),
    ("Lichess Brown", {'light': (240, 217, 181), 'dark': (181, 136, 99)}),
    ("Wood", {'light': (234, 209, 168), 'dark': (180, 135, 100)}),
    ("Ocean", {'light': (200, 220, 240), 'dark': (80, 125, 180)}),
    ("Walnut", {'light': (235, 215, 180), 'dark': (160, 110, 75)})
]
CURRENT_THEME_INDEX = 0
BOARD_COLOR = BOARD_THEMES[CURRENT_THEME_INDEX][1]

RED_CHECK = (240, 150, 150)
HIGHLIGHT_MOVE_COLOR = (20, 80, 120, 100)
HIGHLIGHT_CAPTURE_COLOR = (170, 0, 0, 120)

PIECE_IMAGES = {}

def get_display_indices(file_idx, rank_idx, pov_color):
    if pov_color == chess.WHITE:
        return file_idx, 7 - rank_idx
    else:
        return 7 - file_idx, rank_idx

def coord2str(position, pov_color):
    col = int(position[0] / SQUARE_SIDE)
    row = int(position[1] / SQUARE_SIDE)
    if pov_color == chess.WHITE:
        file_idx = col
        rank_idx = 7 - row
    else:
        file_idx = 7 - col
        rank_idx = row
    if 0 <= file_idx < 8 and 0 <= rank_idx < 8:
        return chess.FILES[file_idx] + chess.RANKS[rank_idx]
    return None

def paint_highlight(screen, square_str, color, pov_color):
    file_idx = chess.FILES.index(square_str[0])
    rank_idx = chess.RANKS.index(square_str[1])
    disp_col, disp_row = get_display_indices(file_idx, rank_idx, pov_color)
    center_x = disp_col * SQUARE_SIDE + SQUARE_SIDE // 2
    center_y = disp_row * SQUARE_SIDE + SQUARE_SIDE // 2
    highlight_surface = pygame.Surface((SQUARE_SIDE, SQUARE_SIDE), pygame.SRCALPHA)
    pygame.draw.circle(highlight_surface, color, (SQUARE_SIDE // 2, SQUARE_SIDE // 2), SQUARE_SIDE // 4)
    screen.blit(highlight_surface, (disp_col * SQUARE_SIDE, disp_row * SQUARE_SIDE))

def draw_game_state(screen, game_obj, pov_color, highlighted_squares, dragged_piece_info, piece_images_dict):
    screen.fill(BOARD_COLOR['light'])
    for rank_idx in range(8):
        for file_idx in range(8):
            if (rank_idx + file_idx) % 2 == 0:
                disp_col, disp_row = get_display_indices(file_idx, rank_idx, pov_color)
                pygame.draw.rect(screen, BOARD_COLOR['dark'], (disp_col * SQUARE_SIDE, disp_row * SQUARE_SIDE, SQUARE_SIDE, SQUARE_SIDE))

    for square in highlighted_squares:
        is_capture = chess.get_piece(game_obj.board, chess.str2bb(square)) != chess.EMPTY
        color = HIGHLIGHT_CAPTURE_COLOR if is_capture else HIGHLIGHT_MOVE_COLOR
        paint_highlight(screen, square, color, pov_color)

    board_to_draw = list(game_obj.board)
    if dragged_piece_info and dragged_piece_info['leaving_square']:
         board_to_draw[chess.str2index(dragged_piece_info['leaving_square'])] = chess.EMPTY

    for i in range(64):
        piece_code = board_to_draw[i]
        if piece_code != chess.EMPTY and piece_code in piece_images_dict:
            square_str = chess.bb2str(1 << i)
            file_idx, rank_idx = chess.FILES.index(square_str[0]), chess.RANKS.index(square_str[1])
            disp_col, disp_row = get_display_indices(file_idx, rank_idx, pov_color)
            image = piece_images_dict[piece_code]
            screen.blit(pygame.transform.scale(image, (SQUARE_SIDE, SQUARE_SIDE)), (disp_col * SQUARE_SIDE, disp_row * SQUARE_SIDE))

    if dragged_piece_info and dragged_piece_info['image']:
        screen.blit(dragged_piece_info['image'], dragged_piece_info['rect'])

    pygame.display.flip()

def play_game():
    global SQUARE_SIDE, BOARD_COLOR, CURRENT_THEME_INDEX
    
    screen = pygame.display.set_mode((8 * SQUARE_SIDE, 8 * SQUARE_SIDE), pygame.RESIZABLE)
    pygame.display.set_caption(APP_TITLE)
    clock = pygame.time.Clock()

    try:
        b_k = pygame.image.load('images/black_king.png').convert_alpha()
        b_q = pygame.image.load('images/black_queen.png').convert_alpha()
        b_r = pygame.image.load('images/black_rook.png').convert_alpha()
        b_b = pygame.image.load('images/black_bishop.png').convert_alpha()
        b_n = pygame.image.load('images/black_knight.png').convert_alpha()
        b_p = pygame.image.load('images/black_pawn.png').convert_alpha()
        w_k = pygame.image.load('images/white_king.png').convert_alpha()
        w_q = pygame.image.load('images/white_queen.png').convert_alpha()
        w_r = pygame.image.load('images/white_rook.png').convert_alpha()
        w_b = pygame.image.load('images/white_bishop.png').convert_alpha()
        w_n = pygame.image.load('images/white_knight.png').convert_alpha()
        w_p = pygame.image.load('images/white_pawn.png').convert_alpha()

        piece_images_dict = {
            chess.BLACK|chess.KING: b_k, chess.BLACK|chess.QUEEN: b_q,
            chess.BLACK|chess.ROOK: b_r, chess.BLACK|chess.BISHOP: b_b,
            chess.BLACK|chess.KNIGHT: b_n, chess.BLACK|chess.PAWN: b_p,
            chess.WHITE|chess.KING: w_k, chess.WHITE|chess.QUEEN: w_q,
            chess.WHITE|chess.ROOK: w_r, chess.WHITE|chess.BISHOP: w_b,
            chess.WHITE|chess.KNIGHT: w_n, chess.WHITE|chess.PAWN: w_p,
        }
    except pygame.error as e:
        print(f"Error loading images: {e}")
        pygame.quit()
        sys.exit()

    player_id = str(uuid.uuid4())
    game_id = None
    game = chess.Game()
    my_color_str = None
    my_color = None
    is_my_turn = False
    is_waiting_for_opponent = False
    game_is_over = False
    status_text = "Menghubungkan..."

    POLL_EVENT = pygame.USEREVENT + 1
    
    is_dragging = False
    highlighted_squares = []
    dragged_piece_info = {'image': None, 'rect': None, 'leaving_square': None}

    try:
        res = requests.get(f"{SERVER_URL}/api/join_game?player_id={player_id}")
        data = res.json()
        game_id = data['game_id']
        my_color_str = data['color']
        my_color = chess.WHITE if my_color_str == 'white' else chess.BLACK
        if data['status'] == 'waiting':
            is_waiting_for_opponent = True
            pygame.time.set_timer(POLL_EVENT, 2000)
        else:
            game.load_FEN(data['fen'])
            is_my_turn = (my_color == game.to_move)
            if not is_my_turn:
                pygame.time.set_timer(POLL_EVENT, 2000)
    except requests.exceptions.RequestException:
        status_text = "Failed to connect to server"

    running = True
    while running:
        if not game_is_over:
            if is_waiting_for_opponent:
                status_text = "Waiting for opponent..."
            elif game_id:
                if is_my_turn:
                    status_text = "Your Turn"
                else:
                    status_text = "Opponent's Turn"
                if chess.is_check(game.board, my_color):
                     status_text += " - Check!"
        pygame.display.set_caption(f"{APP_TITLE} - {status_text}")

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == POLL_EVENT and not game_is_over:
                try:
                    res = requests.get(f"{SERVER_URL}/api/get_update?game_id={game_id}")
                    data = res.json()
                    
                    if data.get('outcome'):
                        game_is_over = True
                        is_my_turn = False
                        status_text = data['outcome']
                        pygame.time.set_timer(POLL_EVENT, 0)
                        game.load_FEN(data['fen'])

                    else:
                        game_just_started = is_waiting_for_opponent and data.get('status') == 'update'
                        board_has_changed = data.get('fen') and data.get('fen') != game.to_FEN()
                        if game_just_started or board_has_changed:
                            is_waiting_for_opponent = False
                            game.load_FEN(data['fen'])
                            is_my_turn = (my_color_str == data.get('turn'))
                            if is_my_turn:
                                pygame.time.set_timer(POLL_EVENT, 0)
                except requests.exceptions.RequestException: pass

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    CURRENT_THEME_INDEX = (CURRENT_THEME_INDEX + 1) % len(BOARD_THEMES)
                    BOARD_COLOR = BOARD_THEMES[CURRENT_THEME_INDEX][1]
                    print(f"Tema diubah menjadi: {BOARD_THEMES[CURRENT_THEME_INDEX][0]}")

            if is_my_turn and not game_is_over:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    clicked_square = coord2str(event.pos, my_color)
                    if clicked_square:
                        piece_code = chess.get_piece(game.board, chess.str2bb(clicked_square))
                        if piece_code != chess.EMPTY and (piece_code & chess.COLOR_MASK) == my_color:
                            is_dragging = True
                            dragged_piece_info['leaving_square'] = clicked_square
                            scaled_img = pygame.transform.scale(piece_images_dict[piece_code], (SQUARE_SIDE, SQUARE_SIDE))
                            dragged_piece_info['image'] = scaled_img
                            dragged_piece_info['rect'] = scaled_img.get_rect(center=event.pos)
                            piece_bb = chess.str2bb(clicked_square)
                            for move in chess.legal_moves(game, my_color):
                                if move[0] == piece_bb:
                                    highlighted_squares.append(chess.bb2str(move[1]))
                
                elif event.type == pygame.MOUSEMOTION and is_dragging:
                    dragged_piece_info['rect'].center = event.pos

                elif event.type == pygame.MOUSEBUTTONUP and is_dragging:
                    is_dragging = False
                    arriving_square = coord2str(event.pos, my_color)
                    if arriving_square and arriving_square in highlighted_squares:
                        move_str = dragged_piece_info['leaving_square'] + arriving_square
                        is_my_turn = False
                        try:
                            res = requests.get(f"{SERVER_URL}/api/move?game_id={game_id}&player_id={player_id}&move={move_str}")
                            data = res.json()
                            game.load_FEN(data['fen'])
                            
                            if data.get('outcome'):
                                game_is_over = True
                                is_my_turn = False
                                status_text = data['outcome']
                                pygame.time.set_timer(POLL_EVENT, 0)
                            else:
                                is_my_turn = (my_color_str == data.get('turn'))
                                if not is_my_turn:
                                    pygame.time.set_timer(POLL_EVENT, 2000)
                        except requests.exceptions.RequestException:
                            is_my_turn = True
                    highlighted_squares = []
                    dragged_piece_info = {'image': None, 'rect': None, 'leaving_square': None}

            if event.type == pygame.VIDEORESIZE:
                new_size = min(event.w, event.h)
                SQUARE_SIDE = new_size // 8
                screen = pygame.display.set_mode((8 * SQUARE_SIDE, 8 * SQUARE_SIDE), pygame.RESIZABLE)

        draw_game_state(screen, game, my_color, highlighted_squares, dragged_piece_info, piece_images_dict)
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    play_game()