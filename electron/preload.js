/**
 * Z.A.I.N.E — Electron Preload Bridge
 * Securely exposes window control APIs while keeping contextIsolation: true.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  isElectron: true
});
