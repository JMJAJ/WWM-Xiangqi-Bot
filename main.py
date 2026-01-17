"""
WWM Xiangqi Bot - Powered by Fairy-Stockfish
Clean optimized version with proper UCI coordinate handling
Version: 2.1 (Stability Patch)
"""
import cv2
import numpy as np
import pyautogui
import pydirectinput
import time
import os
import keyboard
import tkinter as tk
import threading
import sys
import pygetwindow as gw
import pyscreeze
import shutil
import subprocess
import re

# === CONFIGURATION ===
GAME_WINDOW_TITLE = "Where Winds Meet"
IMAGE_FOLDER = 'images'
CONFIDENCE = 0.55  # Confidence for template matching
AUTO_PLAY_DELAY = 0.8
SCAN_INTERVAL = 0.5
WAIT_FOR_OPPONENT = 1.5
DIFF_THRESHOLD = 18 # Pixel difference to detect a move
MAX_REPETITIONS = 2
ENGINE_THINK_TIME = 2500  # Increased for much better endgame quality

# Piece mapping for internal tracking
PIECE_MAP = {
    'general_red': 'K', 'bodyguard_red': 'A', 'elephan_red': 'B', 
    'horse_red': 'N', 'rook_red': 'R', 'cannon_red': 'C', 'pawn_red': 'P',
    'general_black': 'k', 'bodyguard_black': 'a', 'elephan_black': 'b',
    'horse_black': 'n', 'rook_black': 'r', 'cannon_black': 'c', 'pawn_black': 'p'
}

# Piece symbols for GUI display
PIECE_SYMBOLS = {
    'K': '帥', 'A': '仕', 'B': '相', 'N': '傌', 'R': '俥', 'C': '炮', 'P': '兵',
    'k': '將', 'a': '士', 'b': '象', 'n': '馬', 'r': '車', 'c': '砲', 'p': '卒'
}

# FEN piece mapping for engine (Standard UCI)
FEN_PIECES = {
    'general_red': 'K', 'bodyguard_red': 'A', 'elephan_red': 'B', 
    'horse_red': 'N', 'rook_red': 'R', 'cannon_red': 'C', 'pawn_red': 'P',
    'general_black': 'k', 'bodyguard_black': 'a', 'elephan_black': 'b',
    'horse_black': 'n', 'rook_black': 'r', 'cannon_black': 'c', 'pawn_black': 'p'
}

bot_running = False
bot_paused = False

def focus_game_window():
    """Focus the game window"""
    try:
        windows = gw.getWindowsWithTitle(GAME_WINDOW_TITLE)
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            time.sleep(0.3)
            return True
        print(f"Window '{GAME_WINDOW_TITLE}' not found!")
        return False
    except Exception as e:
        print(f"Focus error: {e}")
        return False

def game_click(x, y):
    """Low-level click to bypass game protection"""
    pydirectinput.moveTo(x, y)
    time.sleep(0.08)
    pydirectinput.mouseDown()
    time.sleep(0.05)
    pydirectinput.mouseUp()
    time.sleep(0.05)

# === FAIRY-STOCKFISH ENGINE ===
class Engine:
    """Fairy-Stockfish engine wrapper with MultiPV support"""
    
    def __init__(self):
        self.engine_path = os.path.join(os.path.dirname(__file__), "fairy-stockfish.exe")
        self.process = None
        
    def start(self):
        """Start engine process"""
        if not os.path.exists(self.engine_path):
            print(f"[ERROR] Engine not found: {self.engine_path}")
            return False
        
        try:
            self.process = subprocess.Popen(
                [self.engine_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            self._send("uci")
            self._wait_for("uciok")
            self._send("setoption name UCI_Variant value xiangqi")
            self._send("setoption name Skill Level value 20")
            self._send("setoption name Threads value 2")
            self._send("setoption name Hash value 128")
            self._send("isready")
            self._wait_for("readyok")
            
            print("[OK] Fairy-Stockfish ready for Xiangqi")
            return True
        except Exception as e:
            print(f"[ERROR] Engine start failed: {e}")
            return False
    
    def _send(self, cmd):
        if self.process and self.process.stdin:
            self.process.stdin.write(cmd + "\n")
            self.process.stdin.flush()
    
    def _read(self):
        if self.process and self.process.stdout:
            try: return self.process.stdout.readline().strip()
            except: pass
        return None
    
    def _wait_for(self, token, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            line = self._read()
            if line and token in line: return line
        return None
    
    def get_best_move(self, fen, forbidden_moves=None):
        """Get best move, avoiding forbidden moves using MultiPV"""
        if not self.process or self.process.poll() is not None:
            self.start()
        
        # Reset game state and set position
        self._send("ucinewgame")
        self._send(f"position fen {fen}")
        
        # If we have forbidden moves, ask for multiple suggestions
        num_pv = 5 if forbidden_moves else 1
        self._send(f"setoption name MultiPV value {num_pv}")
        self._send(f"go movetime {ENGINE_THINK_TIME}")
        
        best_move = None
        pv_candidates = []
        
        start_time = time.time()
        while time.time() - start_time < 15:
            line = self._read()
            if not line: continue
            
            # Collect PV lines
            if " pv " in line:
                parts = line.split()
                try:
                    pv_idx = parts.index("pv")
                    move = parts[pv_idx + 1]
                    if move not in pv_candidates and move != "(none)":
                        pv_candidates.insert(0, move) # Higher PVs usually come later
                except: pass
            
            # Get result
            if line.startswith("bestmove"):
                best_move = line.split()[1]
                break
        
        # Check for repetition avoidance
        if forbidden_moves and best_move in forbidden_moves:
            for candidate in pv_candidates:
                if candidate not in forbidden_moves:
                    print(f"[ENGINE] Loop detected. Avoiding {best_move}, choosing {candidate}")
                    return candidate
                    
        return best_move if best_move != "(none)" else None

# === COORDINATE CONVERSION ===
def uci_to_coords(uci_move):
    """
    Robustly convert UCI move to board coordinates.
    Handles rows 1-10 correctly (especially the row '10' double digit).
    """
    if not uci_move: return None
    
    # Use Regex to split (e.g. 'e2e3' or 'e10e9' or 'a9b10')
    match = re.match(r'([a-i])(\d+)([a-i])(\d+)', uci_move.lower())
    if not match:
        print(f"[WARN] Failed to parse UCI move: {uci_move}")
        return None
        
    f_col_str, f_row_uci, t_col_str, t_row_uci = match.groups()
    
    try:
        from_col = ord(f_col_str) - ord('a')
        to_col = ord(t_col_str) - ord('a')
        
        # Engine: 1=Bottom (Red), 10=Top (Black)
        # Our Board: 9=Bottom, 0=Top
        from_row = 10 - int(f_row_uci)
        to_row = 10 - int(t_row_uci)
        
        # Validation
        if all(0 <= x <= 8 for x in [from_col, to_col]) and all(0 <= x <= 9 for x in [from_row, to_row]):
            return (from_col, from_row, to_col, to_row)
        return None
    except:
        return None

def board_to_fen(board, is_red_turn=True):
    """Convert 10x9 board array to FEN"""
    fen_rows = []
    for row in range(10):
        fen_row = ""
        empty = 0
        for col in range(9):
            piece = board[row][col]
            if piece is None:
                empty += 1
            else:
                if empty > 0:
                    fen_row += str(empty)
                    empty = 0
                fen_row += FEN_PIECES.get(piece, '?')
        if empty > 0:
            fen_row += str(empty)
        fen_rows.append(fen_row)
    
    fen = "/".join(fen_rows)
    fen += " w" if is_red_turn else " b"
    fen += " - - 0 1"
    return fen

# === BOT CORE ===
class XiangqiBot:
    def __init__(self):
        self.x1, self.y1 = 0, 0
        self.x2, self.y2 = 0, 0
        self.cell_w = 0
        self.cell_h = 0
        self.board = [[None for _ in range(9)] for _ in range(10)]
        self.templates = {}
        self.masks = {}
        self.scaled_cache = {}
        self.last_screenshot = None
        self.move_history = []
        self.engine = Engine()
        self.engine.start()
        self.load_templates()
    
    def load_templates(self):
        """Load piece templates and create circular masks"""
        if not os.path.exists(IMAGE_FOLDER):
            print(f"ERROR: '{IMAGE_FOLDER}' not found!")
            return
        
        count = 0
        for f in os.listdir(IMAGE_FOLDER):
            if f.endswith('.png') and f != 'overview.png':
                name = f.replace('.png', '')
                img = cv2.imread(os.path.join(IMAGE_FOLDER, f))
                if img is not None:
                    self.templates[name] = img
                    h, w = img.shape[:2]
                    mask = np.zeros((h, w), dtype=np.uint8)
                    cv2.circle(mask, (w//2, h//2), int(min(h,w)*0.45), 255, -1)
                    self.masks[name] = mask
                    count += 1
        print(f"[OK] {count} piece templates loaded")
    
    def calibrate(self):
        """Calibrate game board coordinates"""
        print("\n=== CALIBRATION ===")
        print("1. Hover TOP-LEFT Piece (Rook) -> Press '1'")
        keyboard.wait('1')
        self.x1, self.y1 = pyautogui.position()
        print(f"[OK] Top-Left: ({self.x1}, {self.y1})")
        time.sleep(0.3)
        
        print("2. Hover BOTTOM-RIGHT Piece (Rook) -> Press '2'")
        keyboard.wait('2')
        self.x2, self.y2 = pyautogui.position()
        print(f"[OK] Bottom-Right: ({self.x2}, {self.y2})")
        
        self.cell_w = (self.x2 - self.x1) / 8
        self.cell_h = (self.y2 - self.y1) / 9
        print(f"[OK] Cell size calculated: {self.cell_w:.1f}x{self.cell_h:.1f}px")
    
    def get_cell_center(self, col, row):
        x = self.x1 + col * self.cell_w
        y = self.y1 + row * self.cell_h
        return int(x), int(y)
    
    def scan_board(self, full=False):
        """Scan board using pixel-diff for speed and template matching for pieces"""
        pad = 100
        x1 = max(0, int(self.x1 - self.cell_w/2 - pad))
        y1 = max(0, int(self.y1 - self.cell_h/2 - pad))
        w = int((self.x2 - self.x1) + self.cell_w + pad*2)
        h = int((self.y2 - self.y1) + self.cell_h + pad*2)
        
        try:
            shot = pyautogui.screenshot(region=(x1, y1, w, h))
            screen = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
        except: return 0
        
        # Decide which cells to scan
        if full or self.last_screenshot is None:
            cells_to_check = [(r, c) for r in range(10) for c in range(9)]
        else:
            cells_to_check = self._detect_changed_cells(screen, x1, y1)
            if not cells_to_check: return 0

        # Scaling logic
        target = int(self.cell_w * 0.85)
        if target not in self.scaled_cache:
            self.scaled_cache[target] = {}
            for name, img in self.templates.items():
                s_img = cv2.resize(img, (target, target))
                s_mask = cv2.resize(self.masks[name], (target, target), interpolation=cv2.INTER_NEAREST)
                self.scaled_cache[target][name] = (s_img, s_mask)
        
        templates = self.scaled_cache[target]
        crop = int(self.cell_w)
        
        for row, col in cells_to_check:
            cx, cy = self.get_cell_center(col, row)
            rx, ry = cx - x1, cy - y1
            
            # Crop cell
            ty1, ty2 = int(ry - crop/2), int(ry + crop/2)
            tx1, tx2 = int(rx - crop/2), int(rx + crop/2)
            if ty1 < 0 or tx1 < 0 or ty2 > screen.shape[0] or tx2 > screen.shape[1]: continue
            
            cell = screen[ty1:ty2, tx1:tx2]
            best_score, best_piece = -1, None
            
            for name, (tmpl, mask) in templates.items():
                res = cv2.matchTemplate(cell, tmpl, cv2.TM_CCOEFF_NORMED, mask=mask)
                score = np.max(res)
                if score > best_score:
                    best_score, best_piece = score, name
            
            self.board[row][col] = best_piece if best_score > CONFIDENCE else None
        
        self.last_screenshot = screen
        return len(cells_to_check)
    
    def _detect_changed_cells(self, current_screen, region_x, region_y):
        changed = []
        curr_gray = cv2.cvtColor(current_screen, cv2.COLOR_BGR2GRAY)
        last_gray = cv2.cvtColor(self.last_screenshot, cv2.COLOR_BGR2GRAY)
        crop = int(self.cell_w)
        
        for row in range(10):
            for col in range(9):
                cx, cy = self.get_cell_center(col, row)
                rx, ry = cx - region_x, cy - region_y
                y1, y2, x1, x2 = int(ry-crop/2), int(ry+crop/2), int(rx-crop/2), int(rx+crop/2)
                
                if y1 < 0 or x1 < 0 or y2 > curr_gray.shape[0] or x2 > curr_gray.shape[1]: continue
                
                diff = cv2.absdiff(curr_gray[y1:y2, x1:x2], last_gray[y1:y2, x1:x2])
                if np.mean(diff) > DIFF_THRESHOLD:
                    changed.append((row, col))
        return changed
    
    def execute_move(self, from_col, from_row, to_col, to_row):
        """Update virtual board and perform physical click"""
        # Store for repetition detection
        uci_move = f"{chr(97+from_col)}{10-from_row}{chr(97+to_col)}{10-to_row}"
        self.move_history.append(uci_move)
        if len(self.move_history) > 12: self.move_history.pop(0)
        
        # Update board
        self.board[to_row][to_col] = self.board[from_row][from_col]
        self.board[from_row][from_col] = None
        
        # Physical action
        sx, sy = self.get_cell_center(from_col, from_row)
        ex, ey = self.get_cell_center(to_col, to_row)
        game_click(sx, sy)
        time.sleep(0.2)
        game_click(ex, ey)
    
    def find_best_move(self, is_red=True):
        """Get move from engine; returns 'MATE' if no legal moves exist"""
        fen = board_to_fen(self.board, is_red)
        
        forbidden = []
        if len(self.move_history) >= 4:
            if self.move_history[-1] == self.move_history[-3]:
                forbidden.append(self.move_history[-1])
        
        best_uci = self.engine.get_best_move(fen, forbidden_moves=forbidden)
        
        if best_uci is None or best_uci == "(none)":
            return "MATE" # Signal that we have no legal moves (Loss)
            
        return uci_to_coords(best_uci)
    
    def get_game_result(self):
        """Check if either king is missing from the board"""
        red_king_exists = any('general_red' in row for row in self.board)
        black_king_exists = any('general_black' in row for row in self.board)
        
        if not red_king_exists and black_king_exists:
            return "LOSE"
        if not black_king_exists and red_king_exists:
            return "WIN"
        return None

# === GUI ===
class GUI:
    def __init__(self, bot):
        self.bot = bot
        self.root = tk.Tk()
        self.root.title("WWM Xiangqi Bot - Fairy-Stockfish")
        self.root.geometry("560x820")
        self.root.configure(bg='#1e1e1e')

        self.is_topmost = False 
        
        self.status = tk.Label(self.root, text="READY", font=('Consolas', 14, 'bold'), bg='#1e1e1e', fg='#00ff00')
        self.status.pack(pady=10)
        
        self.canvas = tk.Canvas(self.root, width=540, height=600, bg='#d4a574', highlightthickness=2, highlightbackground='#333')
        self.canvas.pack(pady=10)
        
        btn_frame = tk.Frame(self.root, bg='#1e1e1e')
        btn_frame.pack(pady=10)

        self.top_btn = tk.Button(btn_frame, text="Stay on Top: OFF", command=self.toggle_topmost, width=15, bg='#444', fg='white')
        self.top_btn.pack(side=tk.TOP, pady=5)
        
        self.scan_btn = tk.Button(btn_frame, text="SCAN (F5)", command=self.do_scan, width=12, bg='#444', fg='white')
        self.scan_btn.pack(side=tk.LEFT, padx=5)
        
        self.play_btn = tk.Button(btn_frame, text="AUTO (F9)", command=self.toggle_auto, width=12, bg='#2e7d32', fg='white')
        self.play_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(btn_frame, text="STOP (F10)", command=self.stop_bot, width=12, bg='#c62828', fg='white', state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        keyboard.add_hotkey('f5', self.do_scan)
        keyboard.add_hotkey('f9', self.toggle_auto)
        keyboard.add_hotkey('f10', self.stop_bot)
        
        self.running = False
        self.draw_board()
    
    def draw_board(self):
        self.canvas.delete("all")
        cw, ch = 60, 60
        # Draw Lines
        for i in range(10): self.canvas.create_line(30, 30+i*ch, 510, 30+i*ch, fill='#2b1810')
        for i in range(9):
            self.canvas.create_line(30+i*cw, 30, 30+i*cw, 270, fill='#2b1810')
            self.canvas.create_line(30+i*cw, 330, 30+i*cw, 570, fill='#2b1810')
        # River
        self.canvas.create_text(150, 300, text="楚 河", font=('SimSun', 20, 'bold'), fill='#2b1810')
        self.canvas.create_text(390, 300, text="漢 界", font=('SimSun', 20, 'bold'), fill='#2b1810')
        
        # Palace X
        self.canvas.create_line(210, 30, 330, 150, fill='#2b1810')
        self.canvas.create_line(330, 30, 210, 150, fill='#2b1810')
        self.canvas.create_line(210, 570, 330, 450, fill='#2b1810')
        self.canvas.create_line(330, 570, 210, 450, fill='#2b1810')

        # Draw Pieces
        for r in range(10):
            for c in range(9):
                p = self.bot.board[r][c]
                if p:
                    sym = PIECE_MAP.get(p, '?')
                    disp = PIECE_SYMBOLS.get(sym, sym)
                    bg = '#e63946' if sym.isupper() else '#f8f0e3'
                    self.canvas.create_oval(30+c*cw-22, 30+r*ch-22, 30+c*cw+22, 30+r*ch+22, fill=bg, outline='#000')
                    self.canvas.create_text(30+c*cw, 30+r*ch, text=disp, font=('SimSun', 18, 'bold'), fill='#000')

    def do_scan(self):
        """Manual or forced full scan"""
        self.status.config(text="SCANNING BOARD...", fg='#ffff00')
        self.root.update()
        
        if focus_game_window():
            time.sleep(0.1)
            self.bot.scan_board(full=True)
            self.draw_board()
            self.status.config(text="SCAN COMPLETE", fg='#00ff00')
        else:
            self.status.config(text="WINDOW NOT FOUND", fg='#ff0000')

    def toggle_auto(self):
        if not self.running:
            pieces_on_board = sum(1 for row in self.bot.board for p in row if p)
            if pieces_on_board == 0:
                self.status.config(text="BOARD EMPTY! SCAN FIRST.", fg='#ff0000')
                self.do_scan()

            self.running = True
            self.play_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            threading.Thread(target=self.auto_loop, daemon=True).start()

    def stop_bot(self):
        self.running = False
        self.play_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status.config(text="STOPPED", fg='#ffff00')

    def toggle_topmost(self):
        """Toggle the window staying on top of others"""
        self.is_topmost = not self.is_topmost
        self.root.attributes("-topmost", self.is_topmost)
        if self.is_topmost:
            self.top_btn.config(text="Stay on Top: ON", bg='#5c5cff')
        else:
            self.top_btn.config(text="Stay on Top: OFF", bg='#444')

    def show_end_game(self, result):
        """Display win/loss message on canvas and stop bot"""
        color = "#00ff00" if result == "WIN" else "#ff0000"
        self.status.config(text=f"GAME OVER: {result}", fg=color)
        
        self.canvas.create_rectangle(120, 240, 420, 360, fill='#1e1e1e', outline=color, width=3)
        self.canvas.create_text(270, 300, text=result, font=('Consolas', 50, 'bold'), fill=color)
        self.root.update()
        
        time.sleep(2)
        self.stop_bot()
        self.draw_board()

    # smh
    def auto_loop(self):
        our_turn = True
        while self.running:
            try:
                # 1. Physical check: Is our King gone?
                result = self.bot.get_game_result()
                if result:
                    self.show_end_game(result)
                    break

                if not focus_game_window():
                    time.sleep(1)
                    continue
                
                if our_turn:
                    self.status.config(text="THINKING...", fg='#ffff00')
                    self.root.update()
                    
                    move = self.bot.find_best_move(is_red=True)
                    
                    if move == "MATE":
                        # Engine says we have no moves -> We lose
                        self.show_end_game("LOSE")
                        break
                    elif move:
                        self.bot.execute_move(*move)
                        self.draw_board()
                        our_turn = False
                        time.sleep(AUTO_PLAY_DELAY)
                    else:
                        self.status.config(text="NO MOVE FOUND", fg='#ff0000')
                        time.sleep(1)
                else:
                    self.status.config(text="WAITING FOR OPPONENT...", fg='#888888')
                    self.root.update()
                    time.sleep(WAIT_FOR_OPPONENT)
                    
                    self.status.config(text="SCANNING FOR MOVE...", fg='#aaaaff')
                    self.root.update()
                    
                    if self.bot.scan_board() > 0:
                        # If opponent moves, check if they just took our King
                        if not any('general_red' in row for row in self.bot.board):
                            self.show_end_game("LOSE")
                            break
                            
                        self.draw_board()
                        our_turn = True
            except Exception as e:
                print(f"Loop Error: {e}")
                time.sleep(1)

def main():
    bot = XiangqiBot()
    if focus_game_window():
        bot.calibrate()
        gui = GUI(bot)
        gui.root.mainloop()
    else:
        print("Could not find game window. Please open the game and try again.")

if __name__ == "__main__":
    main()