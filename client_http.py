import pygame
import chess
import requests
import sys
import uuid
import time
import threading
import queue
from random import choice

pygame.init()

SERVER_URL = 'http://20.222.90.1:8889'
SQUARE_SIDE = 60
APP_TITLE = "Network PvP Chess (Threaded Client)"
BOARD_THEMES = [
    ("Lichess Green", {'light': (238, 238, 210), 'dark': (118, 150, 86)}),
    ("Lichess Blue", {'light': (222, 227, 230), 'dark': (140, 162, 173)}),
    ("Lichess Brown", {'light': (240, 217, 181), 'dark': (181, 136, 99)}),
    ("Wood", {'light': (234, 209, 168), 'dark': (180, 135, 100)})
]
CURRENT_THEME_INDEX = 0
BOARD_COLOR = BOARD_THEMES[CURRENT_THEME_INDEX][1]
HIGHLIGHT_MOVE_COLOR, HIGHLIGHT_CAPTURE_COLOR = (20, 80, 120, 100), (170, 0, 0, 120)

def get_display_indices(f_idx, r_idx, pov): return (f_idx, 7 - r_idx) if pov == chess.WHITE else (7 - f_idx, r_idx)
def coord2str(pos, pov):
    col, row = int(pos[0]/SQUARE_SIDE), int(pos[1]/SQUARE_SIDE); f, r = (col, 7-row) if pov==chess.WHITE else (7-col, row)
    return chess.FILES[f] + chess.RANKS[r] if 0<=f<8 and 0<=r<8 else None
def paint_highlight(s, sq, c, pov):
    f,r = chess.FILES.index(sq[0]), chess.RANKS.index(sq[1]); dc,dr = get_display_indices(f,r,pov)
    hs=pygame.Surface((SQUARE_SIDE,SQUARE_SIDE), pygame.SRCALPHA); pygame.draw.circle(hs,c,(SQUARE_SIDE//2,SQUARE_SIDE//2),SQUARE_SIDE//4); s.blit(hs,(dc*SQUARE_SIDE,dr*SQUARE_SIDE))
def draw_game_state(s, g, pov, h_sq, d_p, p_img):
    s.fill(BOARD_COLOR['light'])
    for r_idx in range(8):
        for f_idx in range(8):
            if (r_idx + f_idx) % 2 == 0:
                dc,dr = get_display_indices(f_idx,r_idx,pov); pygame.draw.rect(s,BOARD_COLOR['dark'],(dc*SQUARE_SIDE,dr*SQUARE_SIDE,SQUARE_SIDE,SQUARE_SIDE))
    for sq in h_sq: paint_highlight(s, sq, HIGHLIGHT_CAPTURE_COLOR if chess.get_piece(g.board,chess.str2bb(sq))!=chess.EMPTY else HIGHLIGHT_MOVE_COLOR, pov)
    b_draw = list(g.board);
    if d_p and d_p['leaving_square']: b_draw[chess.str2index(d_p['leaving_square'])]=chess.EMPTY
    for i in range(64):
        p = b_draw[i];
        if p != chess.EMPTY and p in p_img:
            sq = chess.bb2str(1<<i); f,r = chess.FILES.index(sq[0]), chess.RANKS.index(sq[1]); dc,dr=get_display_indices(f,r,pov)
            s.blit(pygame.transform.scale(p_img[p],(SQUARE_SIDE,SQUARE_SIDE)),(dc*SQUARE_SIDE,dr*SQUARE_SIDE))
    if d_p and d_p['image']: s.blit(d_p['image'], d_p['rect'])
def draw_game_over_overlay(screen, message):
    overlay_color = (0, 0, 0, 150); overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA); overlay.fill(overlay_color); screen.blit(overlay, (0, 0))
    font = pygame.font.Font(None, 40); text_surface = font.render(message, True, (255, 255, 255)); text_rect = text_surface.get_rect(center=screen.get_rect().center); screen.blit(text_surface, text_rect)

def network_thread_func(requests_q, results_q, stop_event):
    while not stop_event.is_set():
        try:
            task = requests_q.get(timeout=1); action = task.get('action')
            try:
                if action == 'join': res = requests.get(f"{SERVER_URL}/api/join_game?player_id={task['player_id']}", timeout=10); results_q.put({'type': 'join_result', 'data': res.json()})
                elif action == 'poll':
                    url = f"{SERVER_URL}/api/get_update?game_id={task['game_id']}&player_id={task['player_id']}"
                    if task.get('fen'): url += f"&fen={task['fen']}";
                    res = requests.get(url, timeout=30); results_q.put({'type': 'poll_result', 'data': res.json()})
                elif action == 'move':
                    url = f"{SERVER_URL}/api/move?game_id={task['game_id']}&player_id={task['player_id']}&move={task['move']}";
                    res = requests.get(url, timeout=10); results_q.put({'type': 'move_result', 'data': res.json()})
            except requests.exceptions.RequestException as e: results_q.put({'type': 'error', 'data': e})
        except queue.Empty: continue

def play_game():
    global SQUARE_SIDE, BOARD_COLOR, CURRENT_THEME_INDEX
    screen = pygame.display.set_mode((8 * SQUARE_SIDE, 8 * SQUARE_SIDE), pygame.RESIZABLE); pygame.display.set_caption(APP_TITLE); clock = pygame.time.Clock()
    try:
        piece_images = {
            chess.BLACK|chess.KING:   pygame.image.load('images/black_king.png').convert_alpha(), chess.BLACK|chess.QUEEN:  pygame.image.load('images/black_queen.png').convert_alpha(),
            chess.BLACK|chess.ROOK:   pygame.image.load('images/black_rook.png').convert_alpha(), chess.BLACK|chess.BISHOP: pygame.image.load('images/black_bishop.png').convert_alpha(),
            chess.BLACK|chess.KNIGHT: pygame.image.load('images/black_knight.png').convert_alpha(), chess.BLACK|chess.PAWN:   pygame.image.load('images/black_pawn.png').convert_alpha(),
            chess.WHITE|chess.KING:   pygame.image.load('images/white_king.png').convert_alpha(), chess.WHITE|chess.QUEEN:  pygame.image.load('images/white_queen.png').convert_alpha(),
            chess.WHITE|chess.ROOK:   pygame.image.load('images/white_rook.png').convert_alpha(), chess.WHITE|chess.BISHOP: pygame.image.load('images/white_bishop.png').convert_alpha(),
            chess.WHITE|chess.KNIGHT: pygame.image.load('images/white_knight.png').convert_alpha(), chess.WHITE|chess.PAWN:   pygame.image.load('images/white_pawn.png').convert_alpha(),
        }
    except pygame.error as e: print(f"Error loading images: {e}"); pygame.quit(); sys.exit()

    player_id = str(uuid.uuid4())
    game_state = {'game_id':None,'my_color':None,'is_my_turn':False,'game_over':False,'is_waiting':False,'status':"Connecting...",'game_over_msg':"",'game_over_time':None}
    game = chess.Game(); dragged_piece = {'image':None,'rect':None,'leaving_square':None}; highlighted_squares = []
    
    requests_q = queue.Queue(); results_q = queue.Queue(); stop_event = threading.Event()
    net_thread = threading.Thread(target=network_thread_func, args=(requests_q, results_q, stop_event), daemon=True); net_thread.start()
    requests_q.put({'action': 'join', 'player_id': player_id})

    running = True
    while running:
        try:
            result = results_q.get_nowait()
            res_type, data = result.get('type'), result.get('data')
            def handle_game_over(outcome_message):
                if not game_state['game_over']: game_state.update({'game_over':True,'game_over_msg':outcome_message,'game_over_time':time.time()})
            if res_type == 'error': handle_game_over(f"Network Error: {type(data).__name__}")
            elif res_type == 'join_result':
                game_state.update({'game_id':data['game_id'],'my_color':chess.WHITE if data['color']=='white' else chess.BLACK})
                if data['status'] == 'waiting':
                    game_state.update({'is_waiting':True,'status':"Waiting for opponent..."}); requests_q.put({'action':'poll','game_id':game_state['game_id'], 'player_id':player_id})
                else:
                    game.load_FEN(data['fen']); game_state['is_my_turn'] = (game_state['my_color'] == game.to_move)
                    if not game_state['is_my_turn']: requests_q.put({'action':'poll','game_id':game_state['game_id'],'fen':game.to_FEN(), 'player_id':player_id})
            elif res_type in ['poll_result', 'move_result']:
                if data.get('fen') and data['fen'] != game.to_FEN(): game.load_FEN(data['fen'])
                game_state.update({'is_waiting':False,'is_my_turn':(game_state['my_color'] == game.to_move)})
                if data.get('outcome'): handle_game_over(data['outcome'])
                elif not game_state['is_my_turn'] and not game_state['game_over']: requests_q.put({'action':'poll','game_id':game_state['game_id'],'fen':game.to_FEN(), 'player_id':player_id})
        except queue.Empty: pass

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    CURRENT_THEME_INDEX = (CURRENT_THEME_INDEX + 1) % len(BOARD_THEMES); BOARD_COLOR = BOARD_THEMES[CURRENT_THEME_INDEX][1]
                    print(f"Theme changed to: {BOARD_THEMES[CURRENT_THEME_INDEX][0]}")
            if game_state['is_my_turn'] and not game_state['game_over']:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button==1:
                    sq = coord2str(event.pos, game_state['my_color'])
                    if sq:
                        p = chess.get_piece(game.board, chess.str2bb(sq));
                        if p!=chess.EMPTY and (p&chess.COLOR_MASK)==game_state['my_color']:
                            dragged_piece.update({'leaving_square':sq,'image':pygame.transform.scale(piece_images[p],(SQUARE_SIDE,SQUARE_SIDE))})
                            dragged_piece['rect'] = dragged_piece['image'].get_rect(center=event.pos)
                            for move in chess.legal_moves(game, game_state['my_color']):
                                if move[0] == chess.str2bb(sq): highlighted_squares.append(chess.bb2str(move[1]))
                elif event.type == pygame.MOUSEMOTION and dragged_piece['image']: dragged_piece['rect'].center=event.pos
                elif event.type == pygame.MOUSEBUTTONUP and event.button==1 and dragged_piece['leaving_square']:
                    arr_sq = coord2str(event.pos, game_state['my_color'])
                    if arr_sq and arr_sq in highlighted_squares:
                        game_state['is_my_turn']=False; requests_q.put({'action':'move','game_id':game_state['game_id'],'player_id':player_id,'move':dragged_piece['leaving_square']+arr_sq})
                    dragged_piece={'image':None,'rect':None,'leaving_square':None}; highlighted_squares=[]
            if event.type == pygame.VIDEORESIZE:
                SQUARE_SIDE = min(event.w,event.h)//8; screen=pygame.display.set_mode((8*SQUARE_SIDE,8*SQUARE_SIDE),pygame.RESIZABLE)
        
        status_to_display = game_state['status']
        if game_state['game_over']:
            remaining = 10 - (time.time() - game_state['game_over_time'])
            if remaining <= 0: running = False
            status_to_display = f"{game_state['game_over_msg']} Closing in {max(0, int(remaining))+1}s..."
        else:
            if not game_state['is_waiting'] and game_state['game_id']:
                status_to_display = "Your Turn" if game_state['is_my_turn'] else "Opponent's Turn"
                if game_state['my_color'] is not None and chess.is_check(game.board, game_state['my_color']): status_to_display += " - Check!"
        
        pygame.display.set_caption(f"{APP_TITLE} - {status_to_display}")
        draw_game_state(screen, game, game_state['my_color'], highlighted_squares, dragged_piece, piece_images)
        if game_state['game_over']: draw_game_over_overlay(screen, status_to_display)
        
        pygame.display.flip()
        clock.tick(60)

    stop_event.set(); net_thread.join(); pygame.quit(); sys.exit()

if __name__ == "__main__": 
    play_game()