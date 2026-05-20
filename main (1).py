# =========================================================
# AETHON LOCAL LINUX TERMINAL (WEB UI & WEBSOCKET)
# =========================================================
from fastapi.responses import HTMLResponse

# The slick, browser-based terminal interface using xterm.js
TERMINAL_HTML = """
<!DOCTYPE html>
<html>
  <head>
    <title>Neo Lab Local Terminal</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" />
    <script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script>
    <style>
      body { background-color: #000; margin: 0; padding: 20px; font-family: monospace; }
      h2 { color: #00ff00; margin-bottom: 10px; }
      #terminal-container { padding: 10px; border: 1px solid #333; border-radius: 5px; }
    </style>
  </head>
  <body>
    <h2>⚡ NEO LAB // Local Render Terminal</h2>
    <div id="terminal-container"></div>
    <script>
      var term = new Terminal({ 
          cursorBlink: true, 
          theme: { background: '#000000', foreground: '#00ff00' }
      });
      term.open(document.getElementById('terminal-container'));
      term.write('Welcome to the Aethon Local Command Engine.\\r\\n');
      term.write('Type commands to interact directly with the Render Linux container.\\r\\n\\n$ ');
      
      var protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
      var ws = new WebSocket(protocol + window.location.host + "/ws/terminal");
      
      var currentCommand = "";
      
      term.onData(e => {
        if (e === '\\r') { // Enter key pressed
          term.write('\\r\\n');
          ws.send(currentCommand);
          currentCommand = "";
        } else if (e === '\\u007F') { // Backspace pressed
          if (currentCommand.length > 0) {
            term.write('\\b \\b');
            currentCommand = currentCommand.slice(0, -1);
          }
        } else {
          currentCommand += e;
          term.write(e);
        }
      });

      ws.onmessage = function(event) {
        // Print the output from the server, then print a new prompt
        term.write(event.data.replace(/\\n/g, '\\r\\n'));
        if (event.data !== "") term.write('\\r\\n');
        term.write('$ ');
      };
    </script>
  </body>
</html>
"""

@app.get("/terminal", response_class=HTMLResponse)
async def get_local_terminal():
    """Opens the live command line in your browser."""
    return TERMINAL_HTML

@app.websocket("/ws/terminal")
async def websocket_local_terminal(websocket: WebSocket):
    """The engine that executes your typed commands in Render's Linux environment."""
    await websocket.accept()
    try:
        while True:
            command = await websocket.receive_text()
            if command.strip() == "":
                await websocket.send_text("")
                continue
            
            # Execute the command physically on the Render server
            try:
                result = subprocess.run(
                    command, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    timeout=30
                )
                # Send the result back to the web terminal
                output = result.stdout if result.returncode == 0 else result.stderr
                await websocket.send_text(output.strip())
            except subprocess.TimeoutExpired:
                await websocket.send_text("[!] Command timed out.")
            except Exception as e:
                await websocket.send_text(f"[!] System Error: {str(e)}")
    except WebSocketDisconnect:
        print("[-] Terminal UI Disconnected.")# --- PASTE THIS AT THE VERY BOTTOM OF main (1).py ---

import pty
import os
import asyncio
import selectors

@app.websocket("/ws/terminal")
async def websocket_local_terminal(websocket: WebSocket):
    await websocket.accept()
    master_fd, slave_fd = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.setsid()
        os.dup2(slave_fd, 0); os.dup2(slave_fd, 1); os.dup2(slave_fd, 2)
        os.close(master_fd)
        os.execlp("bash", "bash")
    else:
        os.close(slave_fd)
        sel = selectors.DefaultSelector()
        sel.register(master_fd, selectors.EVENT_READ)
        try:
            while True:
                events = sel.select(timeout=0.1)
                for key, _ in events:
                    output = os.read(master_fd, 1024).decode('utf-8', errors='ignore')
                    await websocket.send_text(output)
                try:
                    user_input = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                    os.write(master_fd, user_input.encode('utf-8') + b"\n")
                except asyncio.TimeoutError: pass
        except WebSocketDisconnect:
            os.kill(pid, 9); os.close(master_fd)
