import socket
import threading
import logging
import time
import chess
import select

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global state for matching ---
# A lock to ensure thread-safe access to the waiting_player
matchmaking_lock = threading.Lock()
waiting_player = None

class GameSession:
    """Represents a single chess game between two players."""
    def __init__(self, player1_thread, player2_thread):
        self.game_state = chess.Game()
        self.players = {
            chess.WHITE: player1_thread,
            chess.BLACK: player2_thread
        }
        player1_thread.game_session = self
        player1_thread.color = chess.WHITE
        
        player2_thread.game_session = self
        player2_thread.color = chess.BLACK

    def get_opponent(self, player_color):
        return self.players[chess.opposing_color(player_color)]


class ProcessTheClient(threading.Thread):
    def __init__(self, connection, address):
        self.connection = connection
        self.address = address
        self.game_session = None
        self.color = None
        threading.Thread.__init__(self)

    def send_message(self, message):
        """Safely sends a message to this client."""
        try:
            self.connection.sendall((message + '\r\n').encode())
        except (socket.error, BrokenPipeError) as e:
            logging.warning(f"Could not send to {self.address}: {e}. Client likely disconnected.")
            self.cleanup()

    def run(self):
        try:
            rcv = ""
            while True:
                data = self.connection.recv(1024)
                if not data:
                    break  # Connection closed by client
                
                d = data.decode()
                rcv += d
                if rcv.endswith('\r\n'):
                    command_str = rcv.strip()
                    logging.info(f"Received from {self.address}: {command_str}")
                    self.process_command(command_str)
                    rcv = ""
        except (ConnectionResetError, socket.timeout):
            logging.info(f"Client {self.address} disconnected forcefully.")
        finally:
            self.cleanup()
            
    def process_command(self, command_str):
        parts = command_str.split(' ')
        command = parts[0].upper()

        if command == "MOVE":
            if not self.game_session:
                self.send_message("ERROR Not in a game.")
                return

            if self.game_session.game_state.to_move != self.color:
                self.send_message("ERROR Not your turn.")
                return

            move_uci = parts[1]
            logging.info(f"--- DEBUG: Received move UCI: {move_uci} from {self.address} ---")

            try:
                leaving_square_str = move_uci[:2]
                arriving_square_str = move_uci[2:]
                player_move_tuple = (chess.str2bb(leaving_square_str), chess.str2bb(arriving_square_str))
                logging.info(f"--- DEBUG: Parsed to move tuple: {player_move_tuple} ---")

                is_legal = False
                for legal_move in chess.legal_moves(self.game_session.game_state, self.color):
                    if legal_move == player_move_tuple:
                        is_legal = True
                        break
                
                logging.info(f"--- DEBUG: Is the move legal? {is_legal} ---")
                if not is_legal:
                    self.send_message(f"ERROR Invalid or illegal move: {move_uci}")
                    return

                # --- THE FIX IS HERE ---
                
                # 1. Apply the legal move
                self.game_session.game_state = chess.make_move(self.game_session.game_state, player_move_tuple)
                
                # 2. Get the new state
                new_fen = self.game_session.game_state.to_FEN()
                logging.info(f"--- DEBUG: Sending new FEN: {new_fen} ---")

                # 3. ALWAYS send the new board state to both players
                self.send_message(f"STATE {new_fen}")
                self.game_session.get_opponent(self.color).send_message(f"STATE {new_fen}")

                # 4. NOW, check if the game has ended
                if chess.game_ended(self.game_session.game_state):
                    outcome = chess.get_outcome(self.game_session.game_state)
                    logging.info(f"--- DEBUG: Game ended. Outcome: {outcome} ---")
                    
                    # Send the final outcome message to both players
                    self.send_message(f"GAME_END {outcome}")
                    self.game_session.get_opponent(self.color).send_message(f"GAME_END {outcome}")

            except Exception as e:
                logging.error(f"Error processing move: {e}")
                self.send_message(f"ERROR Could not process move {move_uci}")
        else:
            self.send_message("ERROR Unknown command.")
            
    def cleanup(self):
        """Handles client disconnection."""
        global waiting_player
        logging.info(f"Cleaning up connection for {self.address}")
        
        with matchmaking_lock:
            if waiting_player is self:
                waiting_player = None
                logging.info("Removed a waiting player from the lobby.")
        
        if self.game_session:
            try:
                opponent = self.game_session.get_opponent(self.color)
                opponent.send_message("GAME_END Your opponent has disconnected.")
                opponent.game_session = None # Clear opponent's session too
            except (AttributeError, KeyError):
                # Opponent might have already disconnected or game not fully set up
                pass
            self.game_session = None

        self.connection.close()


class Server(threading.Thread):
    def __init__(self, port=8889):
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.port = port
        threading.Thread.__init__(self)
        self.daemon = True
        self.shutdown_flag = threading.Event()

    def run(self):
        global waiting_player
        self.my_socket.bind(('0.0.0.0', self.port))
        self.my_socket.listen(2)
        logging.info(f"PvP Chess Server started on port {self.port}. Waiting for players...")
        
        while not self.shutdown_flag.is_set():
            readable, _, _ = select.select([self.my_socket], [], [], 1.0) # 1.0 second timeout

            if self.my_socket in readable:
                connection, address = self.my_socket.accept()
                logging.info(f"Connection from {address}")
                
                client_thread = ProcessTheClient(connection, address)
                client_thread.start()
                
                with matchmaking_lock:
                    if waiting_player is None:
                        waiting_player = client_thread
                        client_thread.send_message("INFO Waiting for an opponent...")
                    else:
                        player1 = waiting_player
                        player2 = client_thread
                        waiting_player = None
                        logging.info(f"Matching {player1.address} (White) with {player2.address} (Black).")
                        game_session = GameSession(player1, player2)
                        initial_fen = game_session.game_state.to_FEN()
                        player1.send_message(f"START white {initial_fen}")
                        player2.send_message(f"START black {initial_fen}")
        
        self.my_socket.close()
        logging.info("Server socket closed.")

def main():
    svr = Server()
    svr.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        svr.shutdown_flag.set()
        svr.join()
        print("Server has shut down.")

if __name__ == "__main__":
    main()