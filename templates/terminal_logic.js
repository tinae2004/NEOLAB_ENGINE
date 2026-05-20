let term = null; let fitAddon = null;

function initAethonTerminal() {
    if (term) return;
    term = new Terminal({ theme: { background: '#000', foreground: '#0f0', cursor: '#0f0' } });
    fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('terminal-container'));
    fitAddon.fit();

    const ws = new WebSocket((window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws/terminal");
    let currentCommand = "";
    
    term.onData(e => {
        if (e === '\r') { ws.send(currentCommand); currentCommand = ""; term.write('\r\n'); }
        else if (e === '\u007F') { if (currentCommand.length > 0) { term.write('\b \b'); currentCommand = currentCommand.slice(0, -1); } }
        else { currentCommand += e; term.write(e); }
    });
    
    ws.onmessage = (event) => { term.write(event.data.replace(/\n/g, '\r\n') + '\r\n$ '); };
}
