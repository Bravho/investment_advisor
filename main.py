import os
import json
import re
import html
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import httpx

from context_builder import build_advisory_context
from db import DatabaseManager
from model_router import SmartModelRouter

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InvestmentAdvisor")

PORT = int(os.getenv("PORT", 8991))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_ADVISORY_MODEL", os.getenv("OLLAMA_MODEL", "hermes3:8b"))

db = DatabaseManager()
model_router = SmartModelRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    await db.connect()
    try:
        yield
    finally:
        await db.close()


app = FastAPI(title="Investment Advisor AI", version="2.0.0", lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory query log for the dashboard
query_logs: List[Dict[str, Any]] = []

# Mock Investment Portfolio for dashboard aesthetics
mock_portfolio = [
    {"asset": "Bitcoin (BTC)", "category": "Crypto", "allocation": "15%", "price": "$68,500.00", "change": "+3.4%", "trend": "up"},
    {"asset": "Ethereum (ETH)", "category": "Crypto", "allocation": "10%", "price": "$3,820.00", "change": "-1.2%", "trend": "down"},
    {"asset": "S&P 500 ETF (SPY)", "category": "Equities", "allocation": "40%", "price": "$525.50", "change": "+0.8%", "trend": "up"},
    {"asset": "Vanguard Total Bond (BND)", "category": "Bonds", "allocation": "25%", "price": "$72.10", "change": "+0.1%", "trend": "up"},
    {"asset": "Cash (USD)", "category": "Cash", "allocation": "10%", "price": "$1.00", "change": "0.0%", "trend": "neutral"}
]

def build_system_prompt(context: str = "") -> str:
    base = """You are the Investment Advisor AI, a professional financial
consultant integrated into the AI Secretary network via LINE messenger.
You have access to real-time portfolio data, news sentiment analysis,
and historical recommendations stored in a knowledge database.

Your expertise covers:
1. Portfolio analysis and rebalancing recommendations
2. Stock markets - SET (Thai), US equities, crypto, forex
3. News sentiment impact on specific holdings
4. Risk assessment and position sizing
5. Mutual funds - SSF/RMF (Thai tax-advantaged)
6. Macro environment interpretation

RESPONSE RULES:
- Lead with the most actionable insight
- Use bullet points and bold for readability
- Cite sentiment data if available in context
- Always end Thai responses with the disclaimer:
  "การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนการตัดสินใจลงทุน"
- Match language to user (Thai -> Thai, English -> English)
- Never recommend specific stocks as direct financial advice
"""
    if context:
        base += f"\n\n{context}"
    return base


SYSTEM_PROMPT = build_system_prompt()


def _messages(prompt: str, user_message: str, history: Optional[List[Dict[str, str]]]) -> list[dict]:
    messages = [{"role": "system", "content": prompt}]
    for item in (history or [])[-6:]:
        messages.append(
            {"role": item.get("role", "user"), "content": item.get("content", "")}
        )
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_llm_response(
    prompt: str,
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    route: Optional[dict] = None,
) -> tuple[str, str]:
    """Generate with the routed model, then OpenAI, then bilingual templates."""
    route = route or model_router.route_for_task("advisory")
    messages = _messages(prompt, user_message, history)

    if route.get("provider") == "anthropic":
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            completion = await client.messages.create(
                model=route["model"],
                system=prompt,
                messages=messages[1:],
                temperature=0.3,
                max_tokens=1000,
            )
            content = "".join(
                block.text for block in completion.content if hasattr(block, "text")
            ).strip()
            if content:
                return content, route["model"]
        except Exception as exc:
            logger.error("Anthropic generation failed: %s", exc)

    if route.get("provider") == "ollama":
        try:
            logger.info("Generating response using Ollama model %s", route["model"])
            async with httpx.AsyncClient(timeout=route.get("timeout", 60)) as client:
                response = await client.post(
                    f"{route['url'].rstrip('/')}/api/chat",
                    json={
                        "model": route["model"],
                        "messages": messages,
                        "stream": False,
                        "options": {"temperature": 0.3},
                    },
                )
                response.raise_for_status()
                content = response.json().get("message", {}).get("content", "").strip()
                if content:
                    return content, route["model"]
        except Exception as exc:
            logger.error("Ollama generation failed: %s", exc)

    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your_"):
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            completion = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.3,
                max_tokens=1000,
            )
            content = completion.choices[0].message.content
            if content:
                return content.strip(), "gpt-4o-mini"
        except Exception as exc:
            logger.error("OpenAI generation failed: %s", exc)

    logger.warning("Falling back to pre-defined response rules")
    return fallback_response(user_message), "fallback-template"


def fallback_response(user_message: str) -> str:
    msg_lower = user_message.lower()
    
    is_thai = any(c in user_message for c in "กขคฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮะัาำิีึืุูเแโใไ็่้๊๋์")
    
    if "dividend" in msg_lower or "ปันผล" in msg_lower:
        if is_thai:
            return (
                "📈 **คำแนะนำเกี่ยวกับหุ้นปันผล (Dividend Stocks):**\n\n"
                "ในการเลือกหุ้นปันผล ควรพิจารณาเกณฑ์ดังนี้ค่ะ:\n"
                "1. **Dividend Yield (อัตราส่วนเงินปันผลตอบแทน):** ควรอยู่ระหว่าง 4% - 7% ต่อปี\n"
                "2. **Payout Ratio (อัตราการจ่ายปันผล):** ไม่ควรเกิน 70%-80% เพื่อให้บริษัทมีเงินสดไปลงทุนต่อ\n"
                "3. **Free Cash Flow (กระแสเงินสดอิสระ):** ต้องเป็นบวกสม่ำเสมอ เพื่อค้ำจุนเงินปันผล\n\n"
                "คำเตือน: การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนการตัดสินใจลงทุน"
            )
        else:
            return (
                "📈 **Dividend Stocks Recommendation:**\n\n"
                "When selecting dividend stocks, consider the following metrics:\n"
                "1. **Dividend Yield:** Look for a stable yield between 4% and 7% per annum.\n"
                "2. **Payout Ratio:** Ensure it is under 70%-80% to verify dividend sustainability.\n"
                "3. **Free Cash Flow:** Must be consistently positive to support distributions.\n\n"
                "Disclaimer: Investment contains risk, investors should study information before making decisions."
            )
    
    if "portfolio" in msg_lower or "พอร์ต" in msg_lower:
        if is_thai:
            return (
                "💼 **การจัดพอร์ตการลงทุนที่แนะนำ (Asset Allocation):**\n\n"
                "- **ความเสี่ยงปานกลาง (Medium Risk):**\n"
                "  - หุ้น/ตราสารทุน: 50% (เพื่อสร้างการเติบโต)\n"
                "  - ตราสารหนี้/เงินฝากดอกเบี้ยสูง: 35% (เพื่อความมั่นคง)\n"
                "  - สินทรัพย์ทางเลือก (ทองคำ/REITs): 10% (เพื่อป้องกันเงินเฟ้อ)\n"
                "  - เงินสดสภาพคล่อง: 5%\n\n"
                "คำเตือน: การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนการตัดสินใจลงทุน"
            )
        else:
            return (
                "💼 **Recommended Portfolio Structure (Asset Allocation):**\n\n"
                "- **Moderate Risk Profile:**\n"
                "  - Equities / Stocks: 50% (for growth)\n"
                "  - Fixed Income / Bonds: 35% (for stability)\n"
                "  - Alternative Assets (Gold / Real Estate): 10% (inflation hedge)\n"
                "  - Cash/Liquidity: 5%\n\n"
                "Disclaimer: Investment contains risk, investors should study information before making decisions."
            )
            
    if is_thai:
        return (
            "สวัสดีค่ะ! ฉันคือผู้ช่วยด้านการลงทุน AI (Investment Advisor AI)\n\n"
            "คุณสามารถสอบถามฉันเกี่ยวกับการวิเคราะห์หุ้น การจัดพอร์ตการลงทุน กองทุนรวม (SSF/RMF) หรือตลาดคริปโตได้เลยค่ะ\n\n"
            "**ตัวอย่างคำถาม:**\n"
            "- 'แนะนำแนวทางการจัดพอร์ตสำหรับวัยทำงานหน่อย'\n"
            "- 'หุ้นปันผลที่ดีควรเลือกดูจากอะไรบ้าง'\n"
            "- 'กองทุนรวมความเสี่ยงต่ำมีประเภทไหนบ้าง'\n\n"
            "คำเตือน: การลงทุนมีความเสี่ยง ผู้ลงทุนควรศึกษาข้อมูลก่อนการตัดสินใจลงทุน"
        )
    else:
        return (
            "Hello! I am your AI Investment Advisor.\n\n"
            "You can ask me questions about stock analysis, portfolio allocation, mutual funds, or cryptocurrency markets.\n\n"
            "**Example questions:**\n"
            "- 'How should I structure a moderate-risk portfolio?'\n"
            "- 'What criteria should I use to select dividend stocks?'\n"
            "- 'What is the difference between stocks and mutual funds?'\n\n"
            "Disclaimer: Investment contains risk, investors should study information before making decisions."
        )


def extract_tickers(message: str) -> list[str]:
    explicit = re.findall(r"\b[A-Z]{2,6}(?:\.BK|-[A-Z]{2,6})?\b", message)
    crypto_names = {
        "BITCOIN": "BTC-USD",
        "BTC": "BTC-USD",
        "ETHEREUM": "ETH-USD",
        "ETH": "ETH-USD",
        "SOLANA": "SOL-USD",
        "SOL": "SOL-USD",
    }
    upper_message = message.upper()
    mapped = [ticker for name, ticker in crypto_names.items() if re.search(rf"\b{name}\b", upper_message)]
    ignored = {"AI", "THE", "AND", "BUY", "SELL", "HOLD", "USD", "LINE", "SSF", "RMF"}
    return list(dict.fromkeys(ticker for ticker in explicit + mapped if ticker not in ignored))


def detect_recommendation(response: str) -> Optional[str]:
    patterns = {
        "BUY": r"\bBUY\b|ซื้อ",
        "SELL": r"\bSELL\b|ขาย",
        "HOLD": r"\bHOLD\b|ถือ",
    }
    for action, pattern in patterns.items():
        if re.search(pattern, response, re.IGNORECASE):
            return action
    return None


async def _db_call(method_name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    if not db.available:
        return default
    try:
        return await getattr(db, method_name)(*args, **kwargs)
    except Exception as exc:
        logger.warning("Database call %s failed: %s", method_name, exc)
        return default


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Renders a beautiful premium dark-mode HTML dashboard"""
    system_prompt_html = SYSTEM_PROMPT.replace('\n', '<br>')
    db_holdings = await _db_call("get_portfolio_holdings", default=[])
    db_logs = await _db_call("get_recent_query_logs", limit=50, default=[])
    sentiments = await _db_call("get_latest_sentiment_overview", limit=10, default=[])
    recommendations = await _db_call("get_recent_recommendations", limit=5, default=[])
    dashboard_logs = db_logs or list(reversed(query_logs))

    logs_html = ""
    if not dashboard_logs:
        logs_html = "<div class='text-gray-500 text-center py-8'>No queries processed yet. Send messages from the AI Secretary to see them here!</div>"
    else:
        for log in dashboard_logs:
            success_badge = "<span class='px-2 py-0.5 text-xs bg-emerald-500/20 text-emerald-400 rounded-full border border-emerald-500/30'>Success</span>" if log['success'] else "<span class='px-2 py-0.5 text-xs bg-rose-500/20 text-rose-400 rounded-full border border-rose-500/30'>Error</span>"
            timestamp = log.get("timestamp") or log.get("created_at") or ""
            logs_html += f"""
            <div class='border-b border-gray-800 pb-4 mb-4 last:border-0 last:pb-0'>
                <div class='flex justify-between items-start mb-2'>
                    <span class='text-sm text-gray-400 font-mono'>{html.escape(str(timestamp))}</span>
                    {success_badge}
                </div>
                <div class='text-sm text-sky-400 font-medium mb-1'>Sender: <span class='text-gray-300 font-normal'>{html.escape(str(log.get('sender', 'unknown')))}</span></div>
                <div class='text-sm text-sky-400 font-medium mb-1'>Query: <span class='text-white font-normal'>{html.escape(str(log.get('query', '')))}</span></div>
                <div class='text-sm text-emerald-400 font-medium'>Response:</div>
                <div class='text-sm text-gray-300 bg-slate-900/60 p-2 rounded mt-1 border border-slate-800 font-mono whitespace-pre-wrap'>{html.escape(str(log.get('response', '')))}</div>
            </div>
            """

    portfolio_items = mock_portfolio
    if db_holdings:
        portfolio_items = []
        for holding in db_holdings:
            asset = holding.get("ticker") or holding.get("symbol") or holding.get("asset") or "Unknown"
            quantity = holding.get("quantity") or holding.get("shares") or holding.get("units") or "-"
            price = holding.get("current_price") or holding.get("price") or holding.get("average_price") or "-"
            allocation = holding.get("allocation") or holding.get("allocation_percent") or f"{quantity} units"
            change = holding.get("change") or holding.get("change_percent") or "Live"
            trend = "down" if str(change).startswith("-") else "up"
            portfolio_items.append({
                "asset": asset,
                "category": holding.get("category") or holding.get("asset_type") or "Holding",
                "allocation": allocation,
                "price": price,
                "change": change,
                "trend": trend,
            })

    portfolio_html = ""
    for item in portfolio_items:
        color_class = "text-emerald-400" if item['trend'] == 'up' else ("text-rose-400" if item['trend'] == 'down' else "text-gray-400")
        icon = "↑" if item['trend'] == 'up' else ("↓" if item['trend'] == 'down' else "→")
        portfolio_html += f"""
        <tr class="border-b border-gray-800 hover:bg-slate-900/40 transition">
            <td class="py-3 px-4 text-white font-medium">{html.escape(str(item['asset']))}</td>
            <td class="py-3 px-4 text-gray-400 text-sm">{html.escape(str(item['category']))}</td>
            <td class="py-3 px-4 text-sky-400 font-mono">{html.escape(str(item['allocation']))}</td>
            <td class="py-3 px-4 text-white font-mono">{html.escape(str(item['price']))}</td>
            <td class="py-3 px-4 font-mono {color_class}">{icon} {html.escape(str(item['change']))}</td>
        </tr>
        """

    sentiment_html = "<div class='text-gray-500 text-sm'>No live sentiment data available.</div>"
    if sentiments:
        sentiment_rows = []
        for row in sentiments:
            ticker = row.get("ticker", "Unknown")
            score = row.get("score", row.get("sentiment_score", 0))
            label = row.get("label") or row.get("sentiment_label") or "Latest"
            sentiment_rows.append(
                f"<div class='flex justify-between text-sm'><span class='text-white'>{html.escape(str(ticker))}</span>"
                f"<span class='text-sky-400'>{html.escape(str(label))} ({html.escape(str(score))})</span></div>"
            )
        sentiment_html = "".join(sentiment_rows)

    recommendations_html = "<div class='text-gray-500 text-sm'>No recommendations recorded.</div>"
    if recommendations:
        recommendation_rows = []
        for item in recommendations:
            recommendation_rows.append(
                f"<div class='flex justify-between text-sm'><span class='text-white'>{html.escape(str(item.get('ticker', 'Portfolio')))}</span>"
                f"<span class='text-emerald-400'>{html.escape(str(item.get('action', 'REVIEW')).upper())} "
                f"({html.escape(str(item.get('confidence', 'N/A')))})</span></div>"
            )
        recommendations_html = "".join(recommendation_rows)

    openai_status = "Active (Connected)" if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your_") else "Not Configured (Using Ollama or Mock Fallbacks)"
    openai_class = "text-emerald-400" if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("your_") else "text-amber-400 animate-pulse"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Investment Advisor AI Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-main: #0b0f19;
                --bg-card: rgba(17, 24, 39, 0.7);
                --border-color: rgba(255, 255, 255, 0.05);
                --accent-blue: #3b82f6;
                --accent-emerald: #10b981;
            }}
            body {{
                background-color: var(--bg-main);
                color: #f3f4f6;
                font-family: 'Inter', sans-serif;
                margin: 0;
                padding: 0;
                background-image: 
                    radial-gradient(at 10% 20%, rgba(59, 130, 246, 0.1) 0px, transparent 50%),
                    radial-gradient(at 90% 80%, rgba(16, 185, 129, 0.08) 0px, transparent 50%);
                background-attachment: fixed;
            }}
            .glass {{
                background: var(--bg-card);
                backdrop-filter: blur(12px);
                border: 1px solid var(--border-color);
                border-radius: 16px;
            }}
            .custom-scroll::-webkit-scrollbar {{
                width: 6px;
            }}
            .custom-scroll::-webkit-scrollbar-track {{
                background: rgba(0, 0, 0, 0.1);
            }}
            .custom-scroll::-webkit-scrollbar-thumb {{
                background: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
            }}
            .custom-scroll::-webkit-scrollbar-thumb:hover {{
                background: rgba(255, 255, 255, 0.2);
            }}
            .animate-pulse {{
                animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
            }}
            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: .5; }}
            }}
        </style>
    </head>
    <body class="min-h-screen p-6 md:p-12">
        <div class="max-w-7xl mx-auto space-y-8">
            <!-- Header -->
            <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-gray-800 pb-6">
                <div>
                    <div class="flex items-center gap-3">
                        <div class="w-4 h-4 bg-emerald-500 rounded-full animate-pulse"></div>
                        <h1 class="text-3xl font-bold tracking-tight text-white">Investment Advisor AI</h1>
                    </div>
                    <p class="text-gray-400 mt-1">External Microservice for the AI Secretary Brain</p>
                </div>
                <div class="flex gap-4">
                    <div class="bg-gray-900/80 px-4 py-2 rounded-lg border border-gray-800 text-sm">
                        <span class="text-gray-400">Endpoint URL: </span>
                        <code class="text-sky-400 font-mono">http://localhost:{PORT}/advisors/message</code>
                    </div>
                </div>
            </header>

            <!-- Grid Layout -->
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <!-- Left Column: Status & Config -->
                <div class="space-y-8 lg:col-span-1">
                    <div class="glass p-6 space-y-4">
                        <h2 class="text-lg font-semibold text-white border-b border-gray-800 pb-2 flex justify-between items-center">
                            <span>System Status</span>
                            <span class="text-xs bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/30">ONLINE</span>
                        </h2>
                        <div class="space-y-3 text-sm">
                            <div class="flex justify-between">
                                <span class="text-gray-400">Advisor Port:</span>
                                <span class="font-mono text-white">{PORT}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">AI Secretary Status:</span>
                                <span class="text-emerald-400 font-medium">Ready (Shared Channel)</span>
                            </div>
                            <div class="space-y-1">
                                <span class="text-gray-400 block mb-1">OpenAI API Gateway:</span>
                                <span class="font-mono text-xs {openai_class} block break-all">{openai_status}</span>
                            </div>
                            <div class="flex justify-between">
                                <span class="text-gray-400">Ollama Link:</span>
                                <span class="font-mono text-xs text-sky-400">{OLLAMA_URL} ({OLLAMA_MODEL})</span>
                            </div>
                        </div>
                    </div>

                    <div class="glass p-6 space-y-3">
                        <h2 class="text-lg font-semibold text-white border-b border-gray-800 pb-2">Advisor Persona</h2>
                        <div class="text-xs text-gray-300 bg-slate-900/60 p-3 rounded border border-slate-800/80 font-mono leading-relaxed h-64 overflow-y-auto custom-scroll">
                            {system_prompt_html}
                        </div>
                    </div>
                </div>

                <!-- Center Column: Test Panel -->
                <div class="glass p-6 flex flex-col h-[600px] lg:col-span-1">
                    <h2 class="text-lg font-semibold text-white border-b border-gray-800 pb-2 mb-4">Direct Sandbox Testing</h2>
                    <div id="chat-messages" class="flex-grow overflow-y-auto mb-4 p-4 bg-slate-950/80 rounded-xl border border-slate-900 space-y-4 custom-scroll text-sm">
                        <div class="flex gap-2">
                            <div class="bg-slate-800 p-3 rounded-lg text-gray-300 max-w-[85%]">
                                Hello! You can test my investment responses directly in this sandbox before sending query from LINE.
                            </div>
                        </div>
                    </div>
                    <div class="flex gap-2">
                        <input id="chat-input" type="text" placeholder="Ask an investment question..." class="flex-grow bg-slate-900/80 border border-gray-800 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-blue-500 text-sm">
                        <button id="send-btn" class="bg-blue-600 hover:bg-blue-500 transition px-5 py-3 rounded-xl font-medium text-sm text-white">Send</button>
                    </div>
                </div>

                <!-- Right Column: Portfolio and intelligence -->
                <div class="glass p-6 lg:col-span-1 space-y-6">
                    <h2 class="text-lg font-semibold text-white border-b border-gray-800 pb-2">Active Portfolio</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="border-b border-gray-800 text-gray-400 text-xs">
                                    <th class="py-2 px-4">Asset</th>
                                    <th class="py-2 px-4">Type</th>
                                    <th class="py-2 px-4">Alloc</th>
                                    <th class="py-2 px-4">Price</th>
                                    <th class="py-2 px-4">Chg</th>
                                </tr>
                            </thead>
                            <tbody>
                                {portfolio_html}
                            </tbody>
                        </table>
                    </div>
                    <div class="space-y-3 border-t border-gray-800 pt-4">
                        <h3 class="text-sm font-semibold text-white">Sentiment Overview</h3>
                        {sentiment_html}
                    </div>
                    <div class="space-y-3 border-t border-gray-800 pt-4">
                        <h3 class="text-sm font-semibold text-white">Recent Recommendations</h3>
                        {recommendations_html}
                    </div>
                    <div class="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-xs text-emerald-400 leading-relaxed">
                        <strong>💡 Live Integration Tip:</strong> Ask about 'dividend stocks' or 'asset allocation portfolio' in Thai or English to see how the advisor formats specialized responses.
                    </div>
                </div>
            </div>

            <!-- Bottom Section: Query Logs -->
            <div class="glass p-8">
                <h2 class="text-xl font-bold text-white border-b border-gray-800 pb-3 mb-6">Recent Query Logs</h2>
                <div class="max-h-96 overflow-y-auto custom-scroll pr-2">
                    {logs_html}
                </div>
            </div>
        </div>

        <script>
            const chatMessages = document.getElementById('chat-messages');
            const chatInput = document.getElementById('chat-input');
            const sendBtn = document.getElementById('send-btn');

            function appendMessage(text, isUser = false) {{
                const msgDiv = document.createElement('div');
                msgDiv.className = isUser ? 'flex justify-end gap-2' : 'flex gap-2';
                
                const bubble = document.createElement('div');
                bubble.className = isUser 
                    ? 'bg-blue-600/20 text-blue-200 border border-blue-500/30 p-3 rounded-lg max-w-[85%]' 
                    : 'bg-slate-800/80 text-gray-300 border border-slate-700/40 p-3 rounded-lg max-w-[85%] whitespace-pre-wrap';
                bubble.textContent = text;
                
                msgDiv.appendChild(bubble);
                chatMessages.appendChild(msgDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }}

            async function sendMessage() {{
                const text = chatInput.value.trim();
                if (!text) return;
                
                appendMessage(text, true);
                chatInput.value = '';
                
                // Show thinking
                const thinkingDiv = document.createElement('div');
                thinkingDiv.className = 'flex gap-2 text-gray-500 italic';
                thinkingDiv.id = 'thinking';
                thinkingDiv.textContent = 'Thinking...';
                chatMessages.appendChild(thinkingDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;

                try {{
                    const response = await fetch('/advisors/message', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json'
                        }},
                        body: JSON.stringify({{
                            sender: 'sandbox',
                            recipient: 'investment_advisor',
                            intent: 'user_query',
                            payload: {{
                                message: text,
                                history: []
                            }}
                        }})
                    }});
                    
                    const data = await response.json();
                    document.getElementById('thinking').remove();
                    appendMessage(data.response || 'Empty response');
                }} catch (error) {{
                    document.getElementById('thinking').remove();
                    appendMessage('Error contacting advisor: ' + error.message);
                }}
            }}

            sendBtn.addEventListener('click', sendMessage);
            chatInput.addEventListener('keydown', (e) => {{
                if (e.key === 'Enter') sendMessage();
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.post("/advisors/message")
async def execute_advisor(request: Request):
    """
    Handles POST requests from AI Secretary / AgentBroker.
    Receives JSON containing: sender, recipient, intent, payload
    """
    try:
        body = await request.json()
        logger.info(f"Received request body: {json.dumps(body)}")
        
        sender = body.get("sender", "unknown")
        intent = body.get("intent", "user_query")
        payload = body.get("payload", {})
        
        # Get query text
        query = payload.get("message", "")
        history = payload.get("history", []) or []
        portfolio_context = payload.get("portfolio_context")  # injected by secretary

        if not query:
            query = body.get("message", "")

        logger.info(f"Processing query from '{sender}' (intent: '{intent}'): {query}")

        tickers = extract_tickers(query)
        context = await build_advisory_context(query, tickers, db)

        # Always enrich with the live portfolio snapshot injected by the secretary
        # (this covers current value and unrealised P&L that the DB may not store)
        if portfolio_context:
            holdings = portfolio_context.get("holdings", [])
            if holdings:
                lines = ["=== CURRENT PORTFOLIO (from secretary) ==="]
                for h in holdings:
                    line = f"  - {h['ticker']} ({h['name']}): {h.get('quantity', '?')} {h.get('asset_class', '')}"
                    if h.get("current_value_thb"):
                        line += f" | Current value: {h['current_value_thb']:,.0f} THB"
                    if h.get("unrealised_pnl_thb"):
                        pnl = h['unrealised_pnl_thb']
                        sign = "+" if pnl >= 0 else ""
                        line += f" | Unrealised P&L: {sign}{pnl:,.0f} THB"
                    lines.append(line)
                secretary_portfolio_block = "\n".join(lines)
                context = secretary_portfolio_block + ("\n\n" + context if context else "")
                logger.info("[AdvisorMessage] Portfolio context injected by secretary appended to context")

        enriched_prompt = build_system_prompt(context)
        advisory_route = model_router.route_for_task("advisory")
        response_text, llm_model_used = await generate_llm_response(
            enriched_prompt, query, history, advisory_route
        )

        recommendation = detect_recommendation(response_text)
        if recommendation and tickers:
            await _db_call(
                "save_recommendation",
                ticker=tickers[0],
                action=recommendation,
                confidence=0.70,
                rationale=response_text,
                llm_model=llm_model_used,
                sentiment_snapshot=json.dumps({"context": context}, ensure_ascii=False),
                price_at_recommendation=None,
            )

        await _db_call(
            "log_query",
            sender,
            query,
            response_text,
            True,
            llm_model_used,
        )
        
        query_logs.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender,
            "query": query,
            "response": response_text,
            "success": True,
            "llm_model_used": llm_model_used,
        })
        
        # Limit logs size in memory
        if len(query_logs) > 50:
            query_logs.pop(0)
            
        return JSONResponse(content={"response": response_text})
        
    except Exception as e:
        logger.error(f"Error handling advisor message: {e}", exc_info=True)
        await _db_call(
            "log_query",
            "unknown",
            "Error occurred",
            str(e),
            False,
            "none",
        )
        query_logs.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sender": "unknown",
            "query": "Error occurred",
            "response": str(e),
            "success": False
        })
        return JSONResponse(
            status_code=500,
            content={"response": f"Investment Advisor Service Error: {str(e)}"}
        )


@app.post("/execute")
async def execute_legacy(request: Request):
    """Legacy route to support both execute and message standard paths"""
    return await execute_advisor(request)


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Investment Advisor AI service on port {PORT}...")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
