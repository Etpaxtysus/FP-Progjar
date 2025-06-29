import sys
import os.path
import uuid
import json
import time
import threading
from datetime import datetime
from urllib.parse import parse_qs
import chess
import logging 


waiting_player = None
waiting_lock = threading.Lock()

class HttpServer:
    def __init__(self):
        self.sessions = {}
        self.types = {
            '.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.txt': 'text/plain', '.html': 'text/html',
            '.css': 'text/css', '.js': 'application/javascript'
        }

    def response(self, kode=404, message='Not Found', messagebody=b'', headers={}):
        tanggal = datetime.now().strftime('%a, %d %b %Y %H:%M:%S GMT')
        resp = [
            f"HTTP/1.1 {kode} {message}\r\n",
            f"Date: {tanggal}\r\n",
            "Connection: close\r\n",
            "Server: ChessServerMP/1.0\r\n",
            f"Content-Length: {len(messagebody)}\r\n"
        ]
        for kk, vv in headers.items():
            resp.append(f"{kk}: {vv}\r\n")
        resp.append("\r\n")
        return "".join(resp).encode() + messagebody

    def proses(self, data):
        requests = data.split("\r\n")
        if not requests or not requests[0]:
            return self.response(400, 'Bad Request', b'Malformed request')

        baris = requests[0]
        j = baris.split(" ")
        try:
            method = j[0].upper().strip()
            path = j[1].strip()
            if method == 'GET':
                return self.http_get(path)
            else:
                return self.response(405, 'Method Not Allowed', b'Method not allowed')
        except IndexError:
            return self.response(400, 'Bad Request', b'Malformed request line')

    def http_get(self, path):
        parts = path.split('?')
        object_address = parts[0]
        params = parse_qs(parts[1]) if len(parts) > 1 else {}
        
        if object_address == '/api/join_game':
            return self.handle_join_game(params)
        if object_address == '/api/get_update':
            return self.handle_get_update(params)
        if object_address == '/api/move':
            return self.handle_move(params)

        return self.response(404, 'Not Found', b'Endpoint not found')

    def handle_join_game(self, params):
        global waiting_player
        player_id = params.get('player_id', [None])[0]
        if not player_id:
            return self.response(400, 'Bad Request', b'player_id is required')

        with waiting_lock:
            if waiting_player is None:
                game_id = str(uuid.uuid4())
                game = chess.Game()
                self.sessions[game_id] = {
                    'game': game,
                    'players': {'white': player_id, 'black': None},
                    'last_update': time.time()
                }
                waiting_player = {'game_id': game_id, 'player_id': player_id}
                response_data = {'status': 'waiting', 'game_id': game_id, 'color': 'white'}
                return self.response(200, 'OK', json.dumps(response_data).encode(), {'Content-type': 'application/json'})
            else:
                game_id = waiting_player['game_id']
                if game_id in self.sessions:
                    self.sessions[game_id]['players']['black'] = player_id
                    game_fen = self.sessions[game_id]['game'].to_FEN()
                    waiting_player = None
                    response_data = {'status': 'started', 'game_id': game_id, 'color': 'black', 'fen': game_fen}
                    return self.response(200, 'OK', json.dumps(response_data).encode(), {'Content-type': 'application/json'})
                else:
                    waiting_player = None
                    return self.response(404, 'Not Found', b'Waiting game not found, try again')

    def handle_get_update(self, params):
        game_id = params.get('game_id', [None])[0]
        if not game_id or game_id not in self.sessions:
            return self.response(404, 'Not Found', b'Game not found')

        game_session = self.sessions[game_id]
        game_obj = game_session['game']
        
        if game_session['players']['black'] is None:
            response_data = {'status': 'waiting'}
        else:
            outcome = chess.get_outcome(game_obj) if chess.game_ended(game_obj) else None
            response_data = {
                'status': 'update',
                'fen': game_obj.to_FEN(),
                'turn': 'white' if game_obj.to_move == chess.WHITE else 'black',
                'outcome': outcome
            }
        return self.response(200, 'OK', json.dumps(response_data).encode(), {'Content-type': 'application/json'})

    def handle_move(self, params):
        game_id = params.get('game_id', [None])[0]
        player_id = params.get('player_id', [None])[0]
        move_str = params.get('move', [None])[0]

        if not all([game_id, player_id, move_str]) or game_id not in self.sessions:
            return self.response(400, 'Bad Request', b'Missing or invalid parameters')
        
        logging.info(f"[Game: {game_id}] Player {player_id} melakukan gerakan: {move_str}")
        
        session = self.sessions[game_id]
        game = session['game']
        players = session['players']
        
        current_turn_color = 'white' if game.to_move == chess.WHITE else 'black'
        
        if players.get(current_turn_color) != player_id:
            logging.warning(f"[Game: {game_id}] Gerakan ditolak. Bukan giliran Player {player_id}.")
            return self.response(403, 'Forbidden', b'Not your turn')
        
        source_sq = chess.str2bb(move_str[:2])
        target_sq = chess.str2bb(move_str[2:])
        player_move = (source_sq, target_sq)

        if player_move not in list(chess.legal_moves(game, game.to_move)):
            logging.warning(f"[Game: {game_id}] Gerakan ilegal dari Player {player_id}: {move_str}")
            return self.response(400, 'Bad Request', b'Illegal move')

        game = chess.make_move(game, player_move)
        session['game'] = game
        session['last_update'] = time.time()
        
        return self.handle_get_update(params)