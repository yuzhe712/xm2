import { contextBridge } from 'electron'
import { electronAPI } from '@electron-toolkit/preload'

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('electron', electronAPI)
} else {
  // @ts-expect-error electronAPI is intentionally assigned for non-isolated dev fallback.
  window.electron = electronAPI
}
