import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const here = path.dirname(fileURLToPath(import.meta.url))
const dir = path.join(here, '.auth')
const sessionFile = path.join(dir, 'session.txt')
const stateFile = path.join(dir, 'state.json')

// Wait for backend.sh to seed + mint the session, then write a Playwright
// storageState carrying the session cookie so API calls are authenticated.
export default async function globalSetup() {
  for (let i = 0; i < 120; i++) {
    if (fs.existsSync(sessionFile) && fs.readFileSync(sessionFile, 'utf8').trim()) break
    await new Promise((r) => setTimeout(r, 1000))
  }
  const key = fs.readFileSync(sessionFile, 'utf8').trim()
  if (!key) throw new Error('no session key minted by backend seed')
  const state = {
    cookies: [{
      name: 'sessionid', value: key, domain: 'localhost', path: '/',
      expires: Math.floor(Date.now() / 1000) + 86400,
      httpOnly: true, secure: false, sameSite: 'Lax' as const,
    }],
    origins: [],
  }
  fs.writeFileSync(stateFile, JSON.stringify(state))
}
