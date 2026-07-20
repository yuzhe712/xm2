const { spawn } = require('node:child_process')
const { join } = require('node:path')

const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE

const electronViteBin = join(__dirname, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')
const child = spawn(process.execPath, [electronViteBin, ...process.argv.slice(2)], {
  stdio: 'inherit',
  env,
  windowsHide: false,
})

child.on('exit', (code, signal) => {
  if (signal) {
    process.exit(1)
  }
  process.exit(code ?? 0)
})
