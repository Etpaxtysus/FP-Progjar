import pygame
import chess
import socket
import sys
from random import choice
from copy import deepcopy

SERVER_HOST = 'localhost'
SERVER_PORT = 8889
sock = None

pygame.init()

SQUARE_SIDE = 60
RED_CHECK          = (240, 150, 150)
WHITE              = (255, 255, 255)
BLUE_LIGHT         = (140, 184, 219)
BLUE_DARK          = (91,  131, 159)
GRAY_LIGHT         = (240, 240, 240)
GRAY_DARK          = (200, 200, 200)
CHESSWEBSITE_LIGHT = (212, 202, 190)
CHESSWEBSITE_DARK  = (100,  92,  89)
LICHESS_LIGHT      = (240, 217, 181)
LICHESS_DARK       = (181, 136,  99)
LICHESS_GRAY_LIGHT = (164, 164, 164)
LICHESS_GRAY_DARK  = (136, 136, 136)

BOARD_COLORS = [(GRAY_LIGHT, GRAY_DARK), (BLUE_LIGHT, BLUE_DARK), (WHITE, BLUE_LIGHT),
                (CHESSWEBSITE_LIGHT, CHESSWEBSITE_DARK), (LICHESS_LIGHT, LICHESS_DARK),
                (LICHESS_GRAY_LIGHT, LICHESS_GRAY_DARK)]
BOARD_COLOR = choice(BOARD_COLORS)

try:
    BLACK_KING   = pygame.image.load('images/black_king.png')
    BLACK_QUEEN  = pygame.image.load('images/black_queen.png')
    BLACK_ROOK   = pygame.image.load('images/black_rook.png')
    BLACK_BISHOP = pygame.image.load('images/black_bishop.png')
    BLACK_KNIGHT = pygame.image.load('images/black_knight.png')
    BLACK_PAWN   = pygame.image.load('images/black_pawn.png')
    BLACK_JOKER  = pygame.image.load('images/black_joker.png')
    WHITE_KING   = pygame.image.load('images/white_king.png')
    WHITE_QUEEN  = pygame.image.load('images/white_queen.png')
    WHITE_ROOK   = pygame.image.load('images/white_rook.png')
    WHITE_BISHOP = pygame.image.load('images/white_bishop.png')
    WHITE_KNIGHT = pygame.image.load('images/white_knight.png')
    WHITE_PAWN   = pygame.image.load('images/white_pawn.png')
    WHITE_JOKER  = pygame.image.load('images/white_joker.png')
except pygame.error as e:
    print(f"Error loading images: {e}\nEnsure the 'images' folder is present.")
    sys.exit()

CLOCK = pygame.time.Clock()
CLOCK_TICK = 30
SCREEN = pygame.display.set_mode((8 * SQUARE_SIDE, 8 * SQUARE_SIDE), pygame.RESIZABLE)
SCREEN_TITLE = 'Network PvP Chess'
pygame.display.set_icon(pygame.image.load('images/chess_icon.ico'))
pygame.display.set_caption(SCREEN_TITLE)

def resize_screen(square_side_len):
    global SQUARE_SIDE, SCREEN
    SQUARE_SIDE = square_side_len
    SCREEN = pygame.display.set_mode((8 * SQUARE_SIDE, 8 * SQUARE_SIDE), pygame.RESIZABLE)

def print_empty_board():
    SCREEN.fill(BOARD_COLOR[0])
    for position in chess.single_gen(chess.DARK_SQUARES):
        paint_square(chess.bb2str(position), BOARD_COLOR[1])

def paint_square(square, square_color):
    col = chess.FILES.index(square[0])
    row = 7 - chess.RANKS.index(square[1])
    pygame.draw.rect(SCREEN, square_color, (SQUARE_SIDE * col, SQUARE_SIDE * row, SQUARE_SIDE, SQUARE_SIDE), 0)

def get_square_rect(square):
    col = chess.FILES.index(square[0])
    row = 7 - chess.RANKS.index(square[1])
    return pygame.Rect((col * SQUARE_SIDE, row * SQUARE_SIDE), (SQUARE_SIDE, SQUARE_SIDE))

def get_square_from_pos(pos, pov_color=chess.WHITE):
    file_idx = int(pos[0] / SQUARE_SIDE)
    rank_idx = 7 - int(pos[1] / SQUARE_SIDE)

    if pov_color == chess.BLACK:
        file_idx = 7 - file_idx
        rank_idx = 7 - rank_idx

    if 0 <= file_idx < 8 and 0 <= rank_idx < 8:
        return chess.FILES[file_idx] + chess.RANKS[rank_idx]
    return None

def get_pos_from_square(square_str, pov_color=chess.WHITE):
    file_idx = chess.FILES.index(square_str[0])
    rank_idx = chess.RANKS.index(square_str[1])

    if pov_color == chess.BLACK:
        file_idx = 7 - file_idx
        rank_idx = 7 - rank_idx
    
    return (file_idx * SQUARE_SIDE, (7 - rank_idx) * SQUARE_SIDE)

def print_board(board, pov_color=chess.WHITE):
    display_board = board if pov_color == chess.WHITE else chess.rotate_board(board)
    print_empty_board()

    if chess.is_check(board, chess.WHITE):
        king_pos_bb = chess.get_king(display_board, chess.WHITE)
        paint_square(chess.bb2str(king_pos_bb), RED_CHECK)
    if chess.is_check(board, chess.BLACK):
        king_pos_bb = chess.get_king(display_board, chess.BLACK)
        paint_square(chess.bb2str(king_pos_bb), RED_CHECK)

    piece_map = {
        chess.BLACK|chess.KING: BLACK_KING, chess.BLACK|chess.QUEEN: BLACK_QUEEN, chess.BLACK|chess.ROOK: BLACK_ROOK,
        chess.BLACK|chess.BISHOP: BLACK_BISHOP, chess.BLACK|chess.KNIGHT: BLACK_KNIGHT, chess.BLACK|chess.PAWN: BLACK_PAWN,
        chess.BLACK|chess.JOKER: BLACK_JOKER,
        chess.WHITE|chess.KING: WHITE_KING, chess.WHITE|chess.QUEEN: WHITE_QUEEN, chess.WHITE|chess.ROOK: WHITE_ROOK,
        chess.WHITE|chess.BISHOP: WHITE_BISHOP, chess.WHITE|chess.KNIGHT: WHITE_KNIGHT, chess.WHITE|chess.PAWN: WHITE_PAWN,
        chess.WHITE|chess.JOKER: WHITE_JOKER,
    }
    for i in range(64):
        piece_code = display_board[i]
        if piece_code != chess.EMPTY:
            SCREEN.blit(pygame.transform.scale(piece_map[piece_code], (SQUARE_SIDE, SQUARE_SIDE)), get_square_rect(chess.bb2str(1 << i)))
    pygame.display.flip()

def set_title(title):
    pygame.display.set_caption(title)

def listen_for_server_messages(sock, game, player_state):
    try:
        data = sock.recv(2048).decode().strip()
        if not data: return False
        
        parts = data.split(' ', 1)
        command = parts[0].upper()
        args = parts[1] if len(parts) > 1 else ""

        if command == "INFO":
            print(f"Server Info: {parts[1]}")
            set_title(SCREEN_TITLE + f" - {parts[1]}")
            return False
        elif command in ["START", "STATE"]:
            if command == "START":
                color_str, fen = args.split(' ', 1)
                player_state['color'] = chess.WHITE if color_str == 'white' else chess.BLACK
                player_state['ongoing'] = True
                game.load_FEN(fen)
            else:
                game.load_FEN(args)
            return True
        elif command == "GAME_END":
            player_state['ongoing'] = False
            set_title(SCREEN_TITLE + f" - {parts[1]}")
            print(f"Game Over: {parts[1]}")
            return True

    except BlockingIOError:
        return False
    except (ConnectionResetError, IndexError, ValueError):
        player_state['ongoing'] = False
        set_title(SCREEN_TITLE + " - Connection lost")
        print("Lost connection to the server.")
        return True
    return False

def paint_dot_highlight(pov_color, square_str):
    color = (128, 128, 128, 150)
    top_left_pos = get_pos_from_square(square_str, pov_color)
    if top_left_pos is None: return

    center_x = top_left_pos[0] + SQUARE_SIDE // 2
    center_y = top_left_pos[1] + SQUARE_SIDE // 2
    radius = SQUARE_SIDE // 6

    target_rect = pygame.Rect(center_x - radius, center_y - radius, radius * 2, radius * 2)
    shape_surf = pygame.Surface(target_rect.size, pygame.SRCALPHA)
    pygame.draw.circle(shape_surf, color, (radius, radius), radius)
    SCREEN.blit(shape_surf, target_rect)

def paint_ring_highlight(pov_color, square_str):
    color = (180, 40, 40, 150)
    top_left_pos = get_pos_from_square(square_str, pov_color)
    if top_left_pos is None: return

    rect = pygame.Rect(top_left_pos[0], top_left_pos[1], SQUARE_SIDE, SQUARE_SIDE)
    shape_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    
    pygame.draw.circle(shape_surf, color, (SQUARE_SIDE // 2, SQUARE_SIDE // 2), SQUARE_SIDE // 2)
    pygame.draw.circle(shape_surf, (0, 0, 0, 0), (SQUARE_SIDE // 2, SQUARE_SIDE // 2), SQUARE_SIDE // 2 - (SQUARE_SIDE // 10))
    
    SCREEN.blit(shape_surf, rect)

def play_game():
    global sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
        sock.setblocking(False) # Use non-blocking sockets
        print("Connected to server. Waiting for game...")
    except ConnectionRefusedError:
        print("Connection failed. Is the PvP server running?")
        return

    game = chess.Game()
    player_state = {'color': None, 'ongoing': False}
    highlighted_squares = []
    redraw_needed = True

    run = True
    leaving_square = None

    print_empty_board()
    pygame.display.flip()

    while run:
        CLOCK.tick(CLOCK_TICK)

        if listen_for_server_messages(sock, game, player_state):
            redraw_needed = True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False

            is_my_turn = player_state['ongoing'] and (game.to_move == player_state['color'])

            if is_my_turn:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    highlighted_squares = []
                    clicked_square = get_square_from_pos(event.pos, player_state['color'])

                    if clicked_square:
                        leaving_square = clicked_square
                        piece_bb = chess.str2bb(leaving_square)
                        piece = chess.get_piece(game.board, piece_bb)
                        if piece != chess.EMPTY and (piece & chess.COLOR_MASK) == player_state['color']:
                            for move in chess.legal_moves(game, player_state['color']):
                                if move[0] == piece_bb:
                                    highlighted_squares.append(chess.bb2str(move[1]))
                        else:
                            leaving_square = None
                    redraw_needed = True

                elif event.type == pygame.MOUSEBUTTONUP and leaving_square:
                    arriving_square = get_square_from_pos(event.pos, player_state['color'])
                    
                    if arriving_square and arriving_square in highlighted_squares:
                        move_str = f"{leaving_square}{arriving_square}"
                        try: sock.sendall(f"MOVE {move_str}\r\n".encode())
                        except socket.error: run = False
                        
                    leaving_square = None
                    highlighted_squares = []
                    redraw_needed = True

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                run = False
            
            if event.type == pygame.VIDEORESIZE:
                new_size = min(event.w, event.h)
                resize_screen(int(new_size / 8.0))
                redraw_needed = True
        
        if redraw_needed:
            if player_state['ongoing']:
                my_color_name = "White" if player_state['color'] == chess.WHITE else "Black"
                if game.to_move == player_state['color']:
                    title = f"{SCREEN_TITLE} - Your Turn (Playing as {my_color_name})"
                else:
                    title = f"{SCREEN_TITLE} - Waiting for Opponent (Playing as {my_color_name})"
                if chess.is_check(game.board, game.to_move):
                    title += " - Check!"
                set_title(title)
            
            if player_state['color'] is not None:
                print_board(game.board, player_state['color'])
                
            for square in highlighted_squares:
                is_capture = chess.get_piece(game.board, chess.str2bb(square)) != chess.EMPTY
                
                if is_capture:
                    paint_ring_highlight(player_state['color'], square)
                else:
                    paint_dot_highlight(player_state['color'], square)
            
            pygame.display.flip()
            redraw_needed = False

    if sock:
        sock.close()
    pygame.quit()


if __name__ == "__main__":
    play_game()