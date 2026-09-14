import asyncio
import os
import sys

sys.path.append(os.path.abspath("api"))
from mcp_server import store_in_vault

async def test_save():
    content = """# Anthropic Revenue Key Figures — August 2026

**Source:** https://www.cnbc.com/2026/08/17/anthropic-says-annualized-revenue-climbed-to-65-billion-in-july.html

## Revenue Run Rate Trajectory

| Metric | Figure |
|---|---|
| Annualized run rate (end of July 2026) | $65B |
| Annualized run rate (May 2026) | $47B |
| Annualized run rate (end of 2025) | ~$9B |
| Year-over-year growth (run rate) | ~7× |
| Q2 2026 revenue (preliminary) | $11.5B+ |
| Q2 2025 revenue (same quarter prior year) | $787M |
| Q2 YoY growth | ~14× |
| Q1 2026 revenue | $4.73B |
| Q2 sequential growth | >140% |
| Company valuation | $965B |
| Investor year-end 2026 run rate expectation | $100B–$120B |

## Competitor Comparison

- OpenAI annualized run rate: $40B (doubled from $20B at end of 2025)

## Context

- Anthropic confidentially filed IPO prospectus with SEC in June 2026
- Preliminary investor meetings underway; IPO expected September–October 2026
- Underwriters: Morgan Stanley, Goldman Sachs, JPMorgan
- Q2 2026 adjusted operating income: positive
- June 2026: Anthropic temporarily disabled Claude Fable 5 and Mythos 5 due to export control directive; restored after ~2 weeks
- Anthropic was blacklisted by the Pentagon earlier in 2026
"""
    try:
        res = await store_in_vault(
            content=content,
            prefix="anthropic_revenue_key_figures_aug2026",
            jsonld_payload=None,
            ai_model_override="Anthropic Claude Sonnet 4.6"
        )
        print("Result:", res[0].text)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test_save())
