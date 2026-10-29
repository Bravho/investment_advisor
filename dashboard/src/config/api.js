import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, '')

// In local development, use Vite's same-origin proxies. This avoids browser
// restrictions on direct localhost cross-port requests.
export const PORTFOLIO_API = API_BASE ? `${API_BASE}:8996` : '/api/portfolio'
export const ADVISOR_API = API_BASE ? `${API_BASE}:8991` : '/api/advisor'
export const ENGINE_API = API_BASE ? `${API_BASE}:8997` : '/api/engine'
export const COUNCIL_API = API_BASE ? `${API_BASE}:8993` : '/api/council'

export const portfolioClient = axios.create({ baseURL: PORTFOLIO_API, timeout: 30000 })
export const advisorClient = axios.create({ baseURL: ADVISOR_API, timeout: 120000 })
export const engineClient = axios.create({ baseURL: ENGINE_API, timeout: 10000 })
// Discovery runs the full council pipeline over many ideas — allow a long timeout.
export const councilClient = axios.create({ baseURL: COUNCIL_API, timeout: 600000 })
