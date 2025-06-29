import sys
import os
import os.path
import uuid
import json
import base64
import time
import threading
from datetime import datetime
from urllib.parse import parse_qs, unquote
import chess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

waiting_player = None
waiting_lock = threading.Lock()
PLAYER_TIMEOUT_SECONDS = 60

class HttpServer:
    def __init__(self):
        self.sessions = {}
        self.types = {'.pdf':'application/pdf','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.txt':'text/plain','.html':'text/html'}
        self.upload_dir = 'public'
        if not os.path.exists(self.upload_dir): os.makedirs(self.upload_dir)

    def response(self, kode=404, message='Not Found', messagebody=b'', headers={}):
        if not isinstance(messagebody, bytes): messagebody = messagebody.encode('utf-8')
        tanggal = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        resp = [f"HTTP/1.1 {kode} {message}\r\n", f"Date: {tanggal}\r\n", "Connection: close\r\n", "Server: ChessServerMP/1.0\r\n", f"Content-Length: {len(messagebody)}\r\n"]
        for kk, vv in headers.items(): resp.append(f"{kk}: {vv}\r\n")
        resp.append("\r\n")
        return "".join(resp).encode('utf-8') + messagebody

    def proses(self, data):
        requests = data.split("\r\n")
        if not requests or not requests[0]: return self.response(400, 'Bad Request', b'Malformed request')
        baris = requests[0]
        try:
            method, path, _ = baris.split(" ", 2)
            if method.upper() == 'GET': return self.http_get(path.strip())
            return self.response(405, 'Method Not Allowed', b'Method not allowed')
        except ValueError: return self.response(400, 'Bad Request', b'Malformed request line')

    def http_get(self, path):
        parts = path.split('?'); object_address = unquote(parts[0]); params = parse_qs(parts[1]) if len(parts) > 1 else {}
        if object_address.startswith('/api/'):
            if object_address == '/api/join_game': return self.handle_join_game(params)
            if object_address == '/api/get_update': return self.handle_get_update(params)
            if object_address == '/api/move': return self.handle_move(params)
        file_path = os.path.join(self.upload_dir, object_address.lstrip('/'))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as fp: isi = fp.read()
            fext = os.path.splitext(file_path)[1].lower()
            return self.response(200, 'OK', isi, {'Content-Type': self.types.get(fext, 'application/octet-stream')})
        return self.response(404, 'Not Found', b'Endpoint or file not found')

    def handle_join_game(self, params):
        global waiting_player
        player_id = params.get('player_id', [None])[0]
        if not player_id: return self.response(400, 'Bad Request', b'player_id is required')
        with waiting_lock:
            if waiting_player is None:
                game_id = str(uuid.uuid4())
                game = chess.Game()
                self.sessions[game_id] = {'game': game, 'players': {'white': player_id, 'black': None}, 'last_update': time.time()}
                waiting_player = {'game_id': game_id, 'player_id': player_id}
                return self.response(200, 'OK', json.dumps({'status': 'waiting', 'game_id': game_id, 'color': 'white'}), {'Content-type': 'application/json'})
            else:
                if waiting_player['player_id'] == player_id: return self.response(200, 'OK', json.dumps({'status': 'waiting', 'game_id': waiting_player['game_id'], 'color': 'white'}), {'Content-type': 'application/json'})
                game_id = waiting_player['game_id']
                if game_id in self.sessions:
                    self.sessions[game_id]['players']['black'] = player_id
                    self.sessions[game_id]['last_update'] = time.time()
                    waiting_player = None
                    return self.response(200, 'OK', json.dumps({'status': 'started', 'game_id': game_id, 'color': 'black', 'fen': self.sessions[game_id]['game'].to_FEN()}), {'Content-type': 'application/json'})
                else:
                    waiting_player = None; return self.response(404, 'Not Found', b'Waiting game not found, rejoin')

    def handle_get_update(self, params):
        game_id = params.get('game_id', [None])[0]
        requesting_player_id = params.get('player_id', [None])[0]
        if not game_id or game_id not in self.sessions: return self.response(404, 'Not Found', b'Game not found')
        
        last_known_fen = params.get('fen', [None])[0]
        game_session = self.sessions[game_id]
        
        if requesting_player_id:
            game_session['last_poll'] = game_session.get('last_poll', {})
            game_session['last_poll'][requesting_player_id] = time.time()

        end_time = time.time() + 25
        while time.time() < end_time:
            game_obj = game_session['game']
            fair_outcome = chess.get_outcome(game_obj) if chess.game_ended(game_obj) else None
            if fair_outcome: return self.response(200, 'OK', json.dumps({'status': 'update', 'fen': game_obj.to_FEN(), 'outcome': fair_outcome}), {'Content-Type': 'application/json'})
            
            if requesting_player_id and game_session['players']['black'] is not None:
                my_color, opponent_id, opponent_color = None, None, None
                for color, pid in game_session['players'].items():
                    if pid == requesting_player_id: my_color = color
                if my_color:
                    opponent_color = 'black' if my_color == 'white' else 'white'
                    opponent_id = game_session['players'][opponent_color]
                if opponent_id:
                    last_seen_opponent = game_session.get('last_poll', {}).get(opponent_id, game_session['last_update'])
                    if time.time() - last_seen_opponent > PLAYER_TIMEOUT_SECONDS:
                        timeout_outcome = f"Opponent ({opponent_color}) timed out. You win!"
                        return self.response(200, 'OK', json.dumps({'status':'update', 'fen':game_obj.to_FEN(), 'outcome':timeout_outcome}), {'Content-Type':'application/json'})
            
            player_black_joined = game_session['players']['black'] is not None and last_known_fen is None
            board_changed = last_known_fen is not None and game_obj.to_FEN() != last_known_fen
            if player_black_joined or board_changed: break
            time.sleep(0.2)
        
        game_obj = game_session['game']
        outcome = chess.get_outcome(game_obj) if chess.game_ended(game_obj) else None
        return self.response(200, 'OK', json.dumps({'status':'update', 'fen':game_obj.to_FEN(), 'turn':'white' if game_obj.to_move == chess.WHITE else 'black', 'outcome':outcome}), {'Content-Type':'application/json'})

    def handle_move(self, params):
        game_id, player_id, move_str = params.get('game_id', [None])[0], params.get('player_id', [None])[0], params.get('move', [None])[0]
        if not all([game_id, player_id, move_str]) or game_id not in self.sessions: return self.response(400, 'Bad Request', b'Missing/invalid params')
        
        session = self.sessions[game_id]
        game = session['game']
        current_color_str = 'white' if game.to_move == chess.WHITE else 'black'
        if session['players'].get(current_color_str) != player_id:
            return self.response(403, 'Forbidden', json.dumps({'error': 'Not your turn', 'fen': game.to_FEN()}), {'Content-Type': 'application/json'})
        
        try:
            move = chess.str2bb(move_str[:2]), chess.str2bb(move_str[2:])
            if move not in list(chess.legal_moves(game, game.to_move)): raise ValueError
        except (ValueError, IndexError):
            return self.response(400, 'Bad Request', json.dumps({'error': 'Illegal move', 'fen': game.to_FEN()}), {'Content-Type': 'application/json'})
        
        logging.info(f"[Game: {game_id}] Player {player_id} makes valid move: {move_str}")
        session['game'] = chess.make_move(game, move)
        session['last_update'] = time.time()
        
        outcome = chess.get_outcome(session['game']) if chess.game_ended(session['game']) else None
        return self.response(200, 'OK', json.dumps({'status':'update', 'fen':session['game'].to_FEN(), 'turn':'white' if session['game'].to_move == chess.WHITE else 'black', 'outcome':outcome}), {'Content-Type':'application/json'})