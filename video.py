import os, json, asyncio, subprocess, textwrap, requests, edge_tts
from datetime import datetime, timedelta, timezone

E = os.environ
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def tg(t):
    requests.post(f"https://api.telegram.org/bot{E['TG_TOKEN']}/sendMessage",
                  json={"chat_id": E["TG_CHAT"], "text": t[:3900]})

def trend():
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s = requests.get("https://www.googleapis.com/youtube/v3/search", params={
        "part": "id", "type": "video", "order": "viewCount",
        "publishedAfter": since, "maxResults": 50, "key": E["YT_KEY"]}).json()
    ids = ",".join(i["id"]["videoId"] for i in s.get("items", []))
    if not ids:
        return []
    v = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "snippet,statistics", "id": ids, "key": E["YT_KEY"]}).json()
    items = sorted(v.get("items", []), key=lambda x: int(x["statistics"].get("viewCount", 0)), reverse=True)
    return [f"- {x['snippet']['title']} ({x['snippet']['channelTitle']})" for x in items[:10]]

def idea(elenco):
    prompt = ("Sei un creatore di YouTube Shorts. Video virali di oggi:\n" + elenco +
        "\n\nInventa UN video ORIGINALE in italiano ispirato a questi trend (non copiare nessun video). "
        'Rispondi SOLO con JSON: {"titolo": "...", "descrizione": "... con 3 hashtag", '
        '"parole_chiave": "2-3 parole in INGLESE per cercare filmati d\'archivio adatti", '
        '"frasi": ["6 frasi brevi: la prima è un gancio forte, l\'ultima invita a seguire il canale"]}. '
        "Le frasi in totale durano circa 30 secondi.")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={E['GEMINI_KEY']}",
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json"}}, timeout=120).json()
    parts = r["candidates"][0]["content"]["parts"]
    t = "".join(p.get("text", "") for p in parts)
    return json.loads(t.replace("```json", "").replace("```", "").strip())

def clips(q):
    r = requests.get("https://pixabay.com/api/videos/", params={
        "key": E["PIXABAY_KEY"], "q": q, "per_page": 10}).json()
    urls = []
    for h in r.get("hits", []):
        for k in ("large", "medium", "small"):
            u = h["videos"].get(k, {}).get("url")
            if u:
                urls.append(u)
                break
    return urls

def durata(f):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).decode().strip())

def main():
    elenco = trend
