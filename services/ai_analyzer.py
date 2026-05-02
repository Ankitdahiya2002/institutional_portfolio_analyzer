import google.generativeai as genai
import anthropic
import json
import re

# Current valid Gemini models (as of 2025)
GEMINI_MODEL    = "gemini-flash-latest"          # latest, fast, free tier
CLAUDE_MODEL    = "claude-3-5-sonnet-20241022" # best quality

class AIAnalyzerService:
    def __init__(self, gemini_key=None, claude_key=None):
        self.gemini_key  = gemini_key
        self.claude_key  = claude_key
        self.gemini_model = GEMINI_MODEL
        self.claude_client = CLAUDE_MODEL

        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel(GEMINI_MODEL)
            except Exception as e:
                print(f"Gemini init error: {e}")

        if claude_key:
            try:
                self.claude_client = anthropic.Anthropic(api_key=claude_key)
            except Exception as e:
                print(f"Claude init error: {e}")

    def is_configured(self):
        return bool(self.gemini_key or self.claude_client)

    def _ask_ai(self, prompt, model_choice='Gemini', max_tokens=2000):
        """
        Tries AI models in order until one succeeds.
        Order: Gemini (all keys × models) → Claude → OpenRouter.
        Every failure is logged with a clear reason.
        """
        last_error = "No AI model available"

        # ── 1. Gemini (primary — fastest, cheapest) ───────────────
        if self.gemini_key:
            import google.generativeai as genai
            import os
            _PLACEHOLDER_PATTERNS = ('api_key', 'your_key', 'xxx', 'placeholder', '...')
            def _is_real_key(k):
                if not k: return False
                return not any(p in k.strip().lower() for p in _PLACEHOLDER_PATTERNS)

            gemini_keys = [k for k in [
                os.getenv("GEMINI_API_KEY_1"),
                os.getenv("GEMINI_API_KEY_2"),
                self.gemini_key,
            ] if _is_real_key(k)]

            # Only use currently active models (1.5-* and preview builds are deprecated on v1beta)
            gemini_models = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
            ]
            for model_name in gemini_models:
                for key in gemini_keys:
                    try:
                        genai.configure(api_key=key)
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(
                            prompt,
                            generation_config={"max_output_tokens": max_tokens},
                            request_options={"timeout": 30}
                        )
                        if response and response.text:
                            print(f"[AI] Success with {model_name} (key ...{key[-6:]})")
                            return response.text.strip()
                    except Exception as e:
                        err = str(e)
                        print(f"[AI] {model_name} (key ...{key[-6:]}) failed: {err[:80]}")
                        if any(x in err.lower() for x in ["quota", "rate", "429", "resource"]):
                            continue
                        break

        # ── 2. Claude (fallback) ───────────────────────────────────
        if self.claude_client and not isinstance(self.claude_client, str):
            try:
                msg = self.claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=max_tokens,
                    system="You are a financial data engineer. Return valid JSON only.",
                    messages=[{"role": "user", "content": prompt}]
                )
                return msg.content[0].text.strip()
            except Exception as e:
                last_error = f"Claude: {str(e)[:120]}"
                print(f"[AI] {last_error}")

        # ── 2. Gemini — try every key × every model in order ─────
        if self.gemini_key:
            import google.generativeai as genai
            import os
            # Collect all available Gemini keys — skip obvious placeholders
            _PLACEHOLDER_PATTERNS = ('api_key', 'your_key', 'xxx', 'placeholder', '...')
            def _is_real_key(k):
                if not k: return False
                kl = k.strip().lower()
                return not any(p in kl for p in _PLACEHOLDER_PATTERNS)

            gemini_keys = [k for k in [
                os.getenv("GEMINI_API_KEY_1"),
                os.getenv("GEMINI_API_KEY_2"),
                self.gemini_key,
            ] if _is_real_key(k)]
            # Only use currently active models (1.5-* and preview builds are deprecated on v1beta)
            gemini_models = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.0-flash-lite",
            ]
            for model_name in gemini_models:
                for key in gemini_keys:
                    try:
                        genai.configure(api_key=key)
                        model = genai.GenerativeModel(model_name)
                        response = model.generate_content(
                            prompt,
                            generation_config={"max_output_tokens": max_tokens},
                            request_options={"timeout": 30}
                        )
                        if response and response.text:
                            print(f"[AI] Success with {model_name} (key ...{key[-6:]})")
                            return response.text.strip()
                    except Exception as e:
                        err = str(e)
                        print(f"[AI] {model_name} (key ...{key[-6:]}) failed: {err[:80]}")
                        # On quota/rate errors try the next key; otherwise skip model
                        if any(x in err.lower() for x in ["quota", "rate", "429", "resource"]):
                            continue
                        break  # non-quota error — skip remaining keys for this model

        or_key = __import__('os').getenv('OPENROUTER_API_KEY')
        if or_key:
            try:
                import requests
                resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                     headers={"Authorization": f"Bearer {or_key}"},
                                     json={
                                         "model": "google/gemini-2.5-flash:free",
                                         "max_tokens": max_tokens,
                                         "messages": [{"role": "user", "content": prompt}]
                                     }).json()
                content = resp['choices'][0]['message']['content']
                if content:
                    print("[AI] Success with OpenRouter fallback")
                    return content.strip()
            except Exception as e:
                err = str(e)[:80]
                print(f"[AI] OpenRouter failed: {err}")
                last_error = err

        print(f"[AI] All models failed. Last error: {last_error}")
        return ""

    def _parse_json(self, text):
        """Extract valid JSON from AI response text."""
        # Remove markdown fences
        text = re.sub(r'```(?:json)?', '', text).strip('`').strip()
        # Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try extracting JSON block
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        return None

    # ──────────────────────────────────────────────────────────────
    # WEB SEARCH — ISIN Enrichment via SerpAPI → Screener.in → NSE
    # ──────────────────────────────────────────────────────────────
    def _web_search_isin(self, stock_name: str) -> str:
        """
        3-tier ISIN lookup:
          1. SerpAPI  — Google Search (most reliable, requires SERP_API_KEY)
          2. Screener.in — free scrape
          3. NSE autocomplete — free API
        Returns a valid 12-char Indian ISIN or '' if not found.
        """
        import requests, re, time, urllib.parse, os

        _ISIN_RE = re.compile(r'\b(IN[A-Z0-9]{10})\b')

        _headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
        }

        # Clean name for search query
        clean = re.sub(
            r'\s+(LTD\.?|LIMITED|INDUSTRIES|ENTERPRISES|PHARMA|'
            r'CHEMICALS?|TECHNOLOGIES?|TECH)$',
            '', stock_name.upper()
        ).strip()

        def _extract_isin(text):
            m = _ISIN_RE.search(text)
            return m.group(1) if m else ''

        # ── 1. SerpAPI (Google Search) ──────────────────────────
        serp_key = os.getenv('SERP_API_KEY', '')
        if serp_key:
            try:
                query = f"{stock_name} NSE ISIN site:nseindia.com OR site:screener.in OR site:bseindia.com"
                resp = requests.get(
                    "https://serpapi.com/search.json",
                    params={
                        "q":       query,
                        "api_key": serp_key,
                        "engine":  "google",
                        "num":     5,
                        "gl":      "in",
                        "hl":      "en",
                    },
                    timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Check organic results titles + snippets
                    for result in data.get('organic_results', []):
                        for field in ('snippet', 'title', 'link'):
                            isin = _extract_isin(result.get(field, ''))
                            if isin:
                                print(f"[ISIN SerpAPI] {isin} ← '{stock_name}'")
                                return isin
                    # Also check knowledge graph / answer box
                    for field in ('answer_box', 'knowledge_graph'):
                        box = data.get(field, {})
                        if isinstance(box, dict):
                            for v in box.values():
                                isin = _extract_isin(str(v))
                                if isin:
                                    print(f"[ISIN SerpAPI KG] {isin} ← '{stock_name}'")
                                    return isin
                else:
                    print(f"[ISIN SerpAPI] HTTP {resp.status_code} for '{stock_name}'")
            except Exception as e:
                print(f"[ISIN SerpAPI] Failed for '{stock_name}': {str(e)[:80]}")


        # ── 2. Screener.in (free scrape) ────────────────────────
        encoded = urllib.parse.quote(clean)
        try:
            s = requests.Session()
            s.get("https://www.screener.in/", headers=_headers, timeout=15)
            resp = s.get(
                f"https://www.screener.in/api/company/search/?q={encoded}&v=3&fts=1",
                headers={**_headers,
                         "X-Requested-With": "XMLHttpRequest",
                         "Referer": "https://www.screener.in/"},
                timeout=15
            )
            if resp.status_code == 200:
                hits = resp.json()
                if hits:
                    company_url = hits[0].get('url', '')
                    if company_url:
                        page = s.get(
                            f"https://www.screener.in{company_url}",
                            headers=_headers, timeout=20
                        )
                        if page.status_code == 200:
                            isin = _extract_isin(page.text)
                            if isin:
                                print(f"[ISIN Screener] {isin} ← '{stock_name}'")
                                return isin
        except Exception as e:
            print(f"[ISIN Screener] Failed for '{stock_name}': {str(e)[:60]}")


        # ── 3. NSE India autocomplete (free API) ─────────────────
        try:
            nse = requests.Session()
            nse.get("https://www.nseindia.com", headers=_headers, timeout=15)
            resp = nse.get(
                f"https://www.nseindia.com/api/search/autocomplete?q={encoded}",
                headers={**_headers, "Referer": "https://www.nseindia.com/"},
                timeout=15
            )
            if resp.status_code == 200:
                for sym in resp.json().get('symbols', []):
                    isin = sym.get('isin_code') or sym.get('isinCode') or ''
                    if isin and len(isin) == 12 and isin.upper().startswith('IN'):
                        print(f"[ISIN NSE] {isin} ← '{stock_name}'")
                        return isin.upper()
        except Exception as e:
            print(f"[ISIN NSE] Failed for '{stock_name}': {str(e)[:60]}")

        print(f"[ISIN Web] ✗ Not found: '{stock_name}'")
        return ''

    def lookup_isins(self, stock_names, model_choice='Gemini'):

        """
        Two-stage ISIN Enrichment:
          Stage 1 — AI internal knowledge (fast, batch)
          Stage 2 — Live web search via Screener.in / NSE (for any still-missing ISINs)
        """
        if not stock_names:
            return {}

        def _valid(v):
            return bool(v) and len(str(v).strip()) == 12 and str(v).strip().upper().startswith('IN')

        # ── Stage 1: AI batch lookup ────────────────────────────
        results = {}
        chunk_size = 20
        for i in range(0, len(stock_names), chunk_size):
            chunk = stock_names[i:i+chunk_size]
            prompt = f"""Find the official 12-digit Indian ISIN (starts with 'IN') for each stock below.
Source: NSE / BSE / NSDL. Return ONLY a valid JSON object (no markdown).
Format: {{"Stock Name": "ISIN_CODE", ...}}
If unknown, return empty string.

Stocks: {json.dumps(chunk)}"""
            text   = self._ask_ai(prompt, model_choice=model_choice, max_tokens=1500)
            parsed = self._parse_json(text)
            if isinstance(parsed, dict):
                results.update(parsed)

        # ── Stage 2: Web search for still-missing ISINs ─────────
        missing = [n for n in stock_names if not _valid(results.get(n, ''))]
        if missing:
            print(f"[ISIN] AI resolved {len(stock_names)-len(missing)}/{len(stock_names)}. "
                  f"Web-searching {len(missing)} more...")
            from concurrent.futures import ThreadPoolExecutor
            
            def _web_worker(name):
                isin = self._web_search_isin(name)
                return name, isin

            with ThreadPoolExecutor(max_workers=5) as executor:
                web_results = list(executor.map(_web_worker, missing))
                
            for name, isin in web_results:
                if isin:
                    results[name] = isin

        found = sum(1 for v in results.values() if _valid(v))
        print(f"[ISIN] Final: {found}/{len(stock_names)} resolved.")
        return results


    def generate_portfolio_report(self, df, stats, model_choice='Claude'):
        """
        Generates an institutional-grade behavioral & strategic report.
        Sends a compact summary to avoid free-tier token limits.
        """
        # Send only key columns, max 20 holdings to stay within token limits
        summary_cols = ['stock_name', 'quantity', 'invested_amount',
                        'current_value', 'pnl_pct', 'asset_type', 'sector']
        available = [c for c in summary_cols if c in df.columns]
        top_holdings = df[available].head(20).to_csv(index=False)

        prompt = f"""You are a friendly financial advisor who explains things in simple, everyday language — like talking to a friend over chai.

Analyze this Indian equity portfolio and return a JSON report.

KEY STATS:
- Total Invested: ₹{stats.get('total_invested', 0):,.0f}
- Current Value: ₹{stats.get('total_current', 0):,.0f}
- Total P&L: ₹{stats.get('total_pnl', 0):,.0f} ({stats.get('total_pnl_pct', 0):+.1f}%)
- Holdings: {stats.get('holdings_count', len(df))}
- ISIN Coverage: {df.attrs.get('isin_coverage', 'N/A')}

TOP HOLDINGS (CSV):
{top_holdings}

INSTRUCTIONS:
- Use clear, warm, everyday Hindi-English (Hinglish) tone — no jargon.
- Imagine you are explaining this to someone's parent or relative at a family dinner.
- Use relatable Indian analogies (cricket, chai, farming, gold, FD, thali) where natural.
- Do NOT repeat the numbers back. Talk about the feeling and direction.
- Keep each field to 1-2 short sentences max.

CRITICAL: Return ONLY valid JSON. No markdown, no extra text.

{{
  "behavioral_signature": "3-6 word casual investor personality title (e.g. 'Steady Long-Term Player')",
  "strategic_verdict": "One warm sentence about the portfolio's overall situation — is it doing well, struggling, or somewhere in the middle?",
  "concentration_risk": "One sentence about whether the money is spread out wisely or too concentrated in one area — use a simple analogy.",
  "rebalancing_advice": ["One plain-English action", "One plain-English action", "One plain-English action"],
  "simple_summary": "One sentence in the style of advice from a wise Indian uncle or grandparent — warm, grounded, and easy to understand. Use an everyday analogy, not numbers."
}}"""

        text = self._ask_ai(prompt, model_choice=model_choice, max_tokens=1500)
        parsed = self._parse_json(text)
        if parsed:
            return parsed
            
        # Warm, easy-language fallback if AI is unavailable
        safe_fallback = {
            "behavioral_signature": "Steady Long-Term Player",
            "strategic_verdict": "Your portfolio is like a thali — it has most of the right items, but the portions need a little balancing.",
            "concentration_risk": "Your money is not all in one basket, which is good — but keep an eye so one stock doesn't become too dominant, like too much salt in a dish.",
            "rebalancing_advice": [
                "Review the stocks that are down — decide if they deserve more time or need to go",
                "Make sure you have exposure to at least 4-5 different sectors, not just one industry",
                "If one position has grown very large, consider taking some profits off the table"
            ],
            "simple_summary": "Think of your portfolio like a kitchen garden — some plants are growing well, some need water, and a couple should be uprooted. Overall, the soil is good."
        }

        return safe_fallback
