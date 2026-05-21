"""
Daily Briefing - Heitor Castro
Busca notícias via NewsAPI + Anthropic e envia pelo WhatsApp (Twilio)
Agendar: cron  0 9 * * 1-5  /usr/bin/python3 /app/briefing.py
"""

import os
import json
import datetime
import requests
from anthropic import Anthropic

# ── Configurações ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
NEWS_API_KEY       = os.environ["NEWS_API_KEY"]          # https://newsapi.org (free tier ok)
TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN  = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_FROM        = os.environ["TWILIO_FROM"]           # whatsapp:+14155238886
TWILIO_TO          = os.environ["TWILIO_TO"]             # whatsapp:+55119XXXXXXXX

client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Tópicos e queries ──────────────────────────────────────────────────────────
TOPICS = {
    "💻 Tecnologia": [
        "artificial intelligence", "big tech", "startup", "OpenAI", "Google AI",
        "fintech technology", "software"
    ],
    "💳 Pagamentos": [
        "Pix Brazil", "open finance Brasil", "pagamentos digitais", "BNPL",
        "payment processing", "Banco Central Brasil", "fintech payments"
    ],
    "📊 Economia": [
        "economia brasileira", "Selic", "inflação Brasil", "Federal Reserve",
        "mercado financeiro", "PIB Brasil", "dólar real"
    ],
    "🏛️ Política": [
        "política Brasil", "Lula governo", "congresso nacional",
        "regulação tecnologia", "geopolítica", "eleições"
    ],
}

TODAY = datetime.date.today().isoformat()
YESTERDAY = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def fetch_articles(query: str, page_size: int = 3) -> list[dict]:
    """Busca artigos via NewsAPI."""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": YESTERDAY,
        "to": TODAY,
        "sortBy": "relevancy",
        "pageSize": page_size,
        "language": "pt",          # tenta português primeiro
        "apiKey": NEWS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=10)
    articles = r.json().get("articles", [])

    # fallback em inglês se não tiver resultado em pt
    if not articles:
        params["language"] = "en"
        r = requests.get(url, params=params, timeout=10)
        articles = r.json().get("articles", [])

    return [
        {
            "title": a["title"],
            "source": a["source"]["name"],
            "url": a["url"],
            "description": a.get("description", ""),
        }
        for a in articles
        if a.get("title") and "[Removed]" not in a.get("title", "")
    ]


def collect_news() -> dict[str, list[dict]]:
    """Coleta até 5 artigos por tema, deduplicados por URL."""
    results: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()

    for topic, queries in TOPICS.items():
        topic_articles: list[dict] = []
        for q in queries:
            if len(topic_articles) >= 5:
                break
            for art in fetch_articles(q, page_size=3):
                if art["url"] not in seen_urls and len(topic_articles) < 5:
                    seen_urls.add(art["url"])
                    topic_articles.append(art)
        results[topic] = topic_articles

    return results


def summarize_with_claude(news: dict[str, list[dict]]) -> str:
    """Usa Claude para redigir os resumos e montar o briefing."""
    news_json = json.dumps(news, ensure_ascii=False, indent=2)

    prompt = f"""Você é o assistente de inteligência de mercado do Heitor Castro, 
Executive Product Manager de pagamentos em São Paulo.

Hoje é {TODAY}. Com base nas notícias abaixo, crie um briefing diário organizado 
por tema. Para cada notícia inclua:
1. Título em negrito
2. Resumo objetivo de 2-3 linhas em português (sem clichês)
3. Por que isso importa para alguém do mercado de pagamentos/fintech brasileiro
4. Link original

Use emojis de forma sóbria. O tom é profissional mas direto.
Finalize com uma frase de "Insight do dia" transversal aos temas.

NOTÍCIAS:
{news_json}
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def send_whatsapp(body: str) -> None:
    """Envia mensagem via Twilio WhatsApp."""
    # WhatsApp limita mensagens a ~4096 chars — divide se necessário
    chunks = [body[i : i + 4000] for i in range(0, len(body), 4000)]

    from twilio.rest import Client  # type: ignore

    twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    for chunk in chunks:
        twilio.messages.create(
            from_=TWILIO_FROM,
            to=TWILIO_TO,
            body=chunk,
        )
    print(f"✅ Briefing enviado em {len(chunks)} mensagem(ns).")


def main() -> None:
    print(f"📰 Coletando notícias para {TODAY}...")
    news = collect_news()

    total = sum(len(v) for v in news.values())
    print(f"   {total} artigos encontrados. Gerando resumo com Claude...")

    briefing = summarize_with_claude(news)

    header = (
        f"*📋 Daily Briefing — {datetime.date.today().strftime('%d/%m/%Y')}*\n"
        f"_Tecnologia · Pagamentos · Economia · Política_\n\n"
    )
    full_message = header + briefing

    print("📲 Enviando pelo WhatsApp...")
    send_whatsapp(full_message)


if __name__ == "__main__":
    main()
