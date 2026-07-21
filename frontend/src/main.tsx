import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { registerPwa } from './pwa/registerPwa'

registerPwa()

createRoot(document.getElementById('root')!).render(<App />)
