const WebSocket = require('ws');
const { spawn } = require('node-pty');
const os = require('os');

const PORT = process.env.PORT || 8080;

const wss = new WebSocket.Server({ port: PORT });
console.log(`WebSocket PTY server running on port ${PORT}`);

wss.on('connection', (ws) => {
    console.log('New terminal client connected');

    // Spawn a real Linux shell (bash) – works on Render
    const shell = os.platform() === 'win32' ? 'powershell.exe' : 'bash';
    const ptyProcess = spawn(shell, [], {
        name: 'xterm-256color',
        cols: 80,
        rows: 30,
        cwd: process.env.HOME || '/root',
        env: process.env
    });

    // Send PTY output to WebSocket client
    ptyProcess.onData((data) => {
        ws.send(data);
    });

    // Receive commands from WebSocket and write to PTY
    ws.on('message', (message) => {
        ptyProcess.write(message);
    });

    // Cleanup when client disconnects
    ws.on('close', () => {
        console.log('Client disconnected');
        ptyProcess.kill();
    });

    // Welcome message
    ptyProcess.write('echo "Welcome to NEOX Real Linux Terminal (bash)"\r\n');
});
