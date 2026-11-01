import { useState } from 'react'
import CryptoEventsCard from '../components/CryptoEventsCard'
import GeoRiskCard from '../components/GeoRiskCard'
import MacroTrendsBoard from '../components/MacroTrendsBoard'
import SectorMovesPanel from '../components/SectorMovesPanel'
import SentimentFeed from '../components/SentimentFeed'
import { useContagion, useCryptoEvents, useGeoRisk, useMacroTrends, useNewsFeed, useSectorMoves } from '../hooks/useNews'

// 2026-10-31: the old 'Macro Sentiment' gauge, sector bars (score x 0.7/0.45/1.15) and the 7-day sentiment chart
// (same value repeated for 7 days) were synthetic and are no longer displayed - see git history for the old code.
export default function Sentiment() {
  const [includeCrypto, setIncludeCrypto] = useState(false)
  const news = useNewsFeed(includeCrypto)
  const macro = useMacroTrends()
  const sectors = useSectorMoves()
  const crypto = useCryptoEvents()
  const geo = useGeoRisk()
  const contagion = useContagion()
  return <div className="space-y-6"><div><h2 className="text-2xl font-semibold text-white">ข่าวและอารมณ์ตลาด</h2><p className="mt-1 text-sm text-slate-500">News and sentiment intelligence</p></div>
    <GeoRiskCard data={geo.data} loading={geo.loading} error={geo.error} retry={geo.refetch} contagion={contagion.data} />
    <MacroTrendsBoard data={macro.data} loading={macro.loading} error={macro.error} retry={macro.refetch} />
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-6">
        <SectorMovesPanel data={sectors.data} loading={sectors.loading} error={sectors.error} retry={sectors.refetch} digest={news.data?.digest} />
        <CryptoEventsCard data={crypto.data} loading={crypto.loading} error={crypto.error} retry={crypto.refetch} contagion={contagion.data} />
      </div>
      <SentimentFeed payload={news.data} loading={news.loading} error={news.error} retry={news.refetch} includeCrypto={includeCrypto} setIncludeCrypto={setIncludeCrypto} />
    </div>
  </div>
}
