import { portfolioClient } from '../config/api'
import { useApi } from './useApi'

// 2026-10-31: de-duplicated, Thai-summarised news feed (portfolio engine /news/feed)
export const useNewsFeed = (includeCrypto = false, refreshMs = 300000) =>
  useApi(() => portfolioClient.get('/news/feed', { params: { hours: 72, limit: 80, include_crypto: includeCrypto } }), [includeCrypto], refreshMs)

// 2026-10-31: key macro indicator trends board (portfolio engine /macro/trends)
export const useMacroTrends = (refreshMs = 900000) =>
  useApi(() => portfolioClient.get('/macro/trends', { timeout: 120000 }), [], refreshMs)

// 2026-10-31: plain 1-month moves of Tho's holding sectors (portfolio engine /sectors/moves)
export const useSectorMoves = (refreshMs = 900000) =>
  useApi(() => portfolioClient.get('/sectors/moves', { timeout: 60000 }), [], refreshMs)

// 2026-10-31: Thai fund watch list - tax-deductible (ThaiESG/ThaiESGX/RMF/SSF) vs general funds (portfolio engine /funds/watchlist)
export const useFundWatchlist = (refreshMs = 900000) =>
  useApi(() => portfolioClient.get('/funds/watchlist', { timeout: 60000 }), [], refreshMs)

// 2026-11-01: high-impact crypto events card (display-only; not in market mood or signals)
export const useCryptoEvents = (refreshMs = 900000) =>
  useApi(() => portfolioClient.get('/crypto/events', { timeout: 60000 }), [], refreshMs)

// 2026-11-01: single market-mood verdict = price regime; news tone (crypto excluded) is secondary
export const useMarketMood = (refreshMs = 300000) =>
  useApi(() => portfolioClient.get('/market/mood'), [], refreshMs)

// 2026-11-01: geopolitical / war-risk monitor (context/display only; probabilities are judgment)
export const useGeoRisk = (refreshMs = 1800000) =>
  useApi(() => portfolioClient.get('/geo/risk', { timeout: 180000 }), [], refreshMs)
