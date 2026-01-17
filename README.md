# WWM-Xiangqi-Bot

An automated, high-performance Chinese Chess (Xiangqi) bot designed specifically for the Where Winds Meet (WWM) minigame. This application leverages computer vision for board state detection and the Fairy-Stockfish engine for optimal move generation.


https://github.com/user-attachments/assets/8820a67a-c153-452e-9d93-10e1f04ff4e4


## Acknowledgments

This project is powered by the Fairy-Stockfish engine. Special thanks to the developers of the Fairy-Stockfish project for providing a powerful, open-source engine capable of handling Xiangqi variants.

Engine Repository: https://github.com/fairy-stockfish/Fairy-Stockfish

## Project Overview

This project provides a complete automation loop for the Xiangqi minigame. It captures the game screen, identifies piece positions using template matching, converts the board state into Forsyth-Edwards Notation (FEN), and executes moves through simulated mouse input.

## Features

*   **Fairy-Stockfish Integration**: Utilizes the world's leading multi-variant chess engine to calculate the highest probability winning moves.
*   **Computer Vision Engine**: Employs OpenCV template matching with circular masking for robust piece identification regardless of board background variations.
*   **Smart Scan Logic**: Uses pixel-difference analysis between frames to detect opponent moves, significantly reducing CPU overhead compared to constant full-board scanning.
*   **UCI Coordinate Mapping**: Accurately translates engine-standard UCI strings into precise screen coordinates, including full support for 10-row grid indexing.
*   **Repetition Prevention**: Implements Multi-Path Variation (MultiPV) analysis to detect and avoid repetitive move cycles that lead to stalemates.
*   **Always-on-Top GUI**: A dedicated control panel with a toggle to keep the interface visible above the game client during play.
*   **Automated Game State Monitoring**: Real-time detection of win, loss, or stalemate conditions with automated program cessation.

## System Architecture

The application is built on a modular Python architecture:
1.  **Vision Layer**: Screen capture via PyAutoGUI and image processing via OpenCV.
2.  **Logic Layer**: Coordinate transformation and FEN generation.
3.  **Engine Layer**: Subprocess-based UCI communication with fairy-stockfish.exe.
4.  **Interaction Layer**: Direct mouse control using Pydirectinput to bypass traditional input hooks.
5.  **GUI Layer**: Tkinter-based dashboard for visualization and calibration.

## Installation

### Prerequisites
*   Python 3.10 or higher.
*   Fairy-Stockfish binary ([fairy-stockfish.exe](https://github.com/fairy-stockfish/Fairy-Stockfish/releases/tag/fairy_sf_14)) placed in the root directory. (I use fairy-stockfish-largeboard_x86-64.exe but shortened the name to just fairy-stockfish.exe)
*   A folder named 'images' containing PNG templates for all 14 piece types.

### Required Dependencies
```bash
pip install opencv-python numpy pyautogui pydirectinput keyboard pygetwindow pyscreeze
```

## Configuration

The following parameters can be adjusted within the source code to match specific hardware capabilities:

*   **CONFIDENCE**: Set to 0.55 by default. Adjust based on screen resolution and graphics settings.
*   **ENGINE_THINK_TIME**: Set to 2500ms. Increase this value for higher-level play in complex endgames.
*   **DIFF_THRESHOLD**: Controls sensitivity to move detection.

## Usage Instructions

1.  **Launch**: Run the game client and the bot script.
2.  **Calibration**: 
    *   Press '1' while hovering over the center of the top-left piece position.
    *   Press '2' while hovering over the center of the bottom-right piece position.
3.  **Operation**:
    *   **F5 (Scan)**: Performs a full refresh of the piece positions. Shows "SCANNING BOARD" status during operation.
    *   **F9 (Auto)**: Starts the automated play loop. If no pieces are detected, an initial scan is triggered automatically.
    *   **F10 (Stop)**: Ceases all bot activity and releases input control.
4.  **Always on Top**: Use the toggle button in the GUI to keep the bot interface visible over the game window.

## Technical Implementation Notes

### Coordinate Transformation
The bot maps the Fairy-Stockfish UCI 1-10 rank system to a 0-9 array index. This is critical for Xiangqi as the board consists of 10 horizontal lines and 9 vertical lines.

### Game End Logic
Victory or defeat is determined through two parallel checks:
1.  **Physical Presence**: Scanning for the existence of the Red and Black General templates.
2.  **Legal Move Validation**: Interpreting engine feedback. If the engine returns no legal moves (Stalemate or Checkmate), the bot identifies the game as over.

## Disclaimer

This software is intended for educational purposes and personal use within minigame environments. Users should be aware of the terms of service of the games they interact with. The developers assume no liability for misuse.