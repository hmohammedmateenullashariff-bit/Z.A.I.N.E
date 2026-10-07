/**
 * Z.A.I.N.E — Native Windows 11 Acrylic Electron Shell
 * Wraps the local HUD server in a native, frameless acrylic window.
 */

const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

// 1. Resolve Target Port, URL, and Screenshot Flags from CLI Arguments
let targetUrl = 'http://127.0.0.1:7860/';
let screenshotPath = null;
for (const arg of process.argv) {
  if (arg.startsWith('--url=')) {
    targetUrl = arg.slice(6);
  } else if (arg.startsWith('--port=')) {
    const port = arg.slice(7);
    targetUrl = `http://127.0.0.1:${port}/`;
  } else if (arg.startsWith('--screenshot=')) {
    screenshotPath = arg.slice(13);
  }
}

let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    frame: false,
    backgroundMaterial: 'acrylic',
    backgroundColor: '#00000000',
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      sandbox: true,
    }
  });

  // Load the running HUD server
  mainWindow.loadURL(targetUrl);

  // Automated screenshot verification if flag supplied
  mainWindow.webContents.on('did-finish-load', () => {
    if (screenshotPath) {
      setTimeout(async () => {
        try {
          if (process.argv.includes('--unlock')) {
            await mainWindow.webContents.executeJavaScript(`
              const el = document.getElementById('lockScreenOverlay');
              if (el) { el.classList.add('unlocked'); el.style.display = 'none'; }
            `);
            await new Promise(r => setTimeout(r, 600));
          }
          const img = await mainWindow.webContents.capturePage();
          fs.writeFileSync(screenshotPath, img.toPNG());
          console.log(`[Z.A.I.N.E Electron]: Captured acrylic screenshot to ${screenshotPath}`);
        } catch (err) {
          console.error('[Z.A.I.N.E Electron Screenshot Error]:', err);
        } finally {
          app.quit();
        }
      }, 2500);
    }
  });

  // Smooth appearance once the first frame renders (no white flash)
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    console.log(`[Z.A.I.N.E Electron]: Native Acrylic Window loaded from ${targetUrl}`);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// 2. Custom Frameless Titlebar IPC Handlers
ipcMain.on('window-minimize', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.minimize();
  }
});

ipcMain.on('window-maximize', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.close();
  }
});

// 3. Application Lifecycle
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
