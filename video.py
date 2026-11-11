import os, json, asyncio, subprocess, textwrap, requests, edge_tts
from datetime import datetime, timedelta, timezone

E = os.environ
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MODELLI = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]

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
    return [f"- {x['snippet']['title']} ({x['snippet']['channelTitle']})" for x in items[:8]]

def idea(elenco):
    prompt = ("Sei un creatore di YouTube Shorts. Video virali di oggi:\n" + elenco +
        "\n\nInventa UN video ORIGINALE in italiano ispirato a questi trend (non copiare nessun video). "
        'Rispondi SOLO con JSON: {"titolo": "...", "descrizione": "... con 3 hashtag", '
        '"parole_chiave": "2-3 parole in INGLESE per cercare filmati d\'archivio adatti", '
        '"frasi": ["6 frasi brevi: la prima è un gancio forte, l\'ultima invita a seguire il canale"]}. '
        "Le frasi in totale durano circa 30 secondi.")
    ultimo = None
    for modello in MODELLI:
        for _ in range(2):
            try:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent?key={E['GEMINI_KEY']}",
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {"responseMimeType": "application/json"}},
                    timeout=60).json()
                parts = r["candidates"][0]["content"]["parts"]
                t = "".join(p.get("text", "") for p in parts)
                return json.loads(t.replace("```json", "").replace("```", "").strip())
            except Exception as e:
                ultimo = f"{modello}: {e}"
    raise Exception("AI non risponde. Ultimo errore: " + str(ultimo)[:300])

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

def invia_video(d):
    size = os.path.getsize("final.mp4") // 1024
    cap = (d["titolo"] + "\n\n" + d["descrizione"])[:1000]
    base = f"https://api.telegram.org/bot{E['TG_TOKEN']}/"
    with open("final.mp4", "rb") as f:
        r = requests.post(base + "sendVideo",
                          data={"chat_id": E["TG_CHAT"], "caption": cap, "supports_streaming": "true"},
                          files={"video": f}, timeout=300)
    if not r.ok:
        with open("final.mp4", "rb") as f:
            r = requests.post(base + "sendDocument",
                              data={"chat_id": E["TG_CHAT"], "caption": cap},
                              files={"document": f}, timeout=300)
    if not r.ok:
        tg(f"Video creato ({size} KB) ma Telegram lo rifiuta: {r.status_code} {r.text[:300]}")

def main():
    elenco = trend()
    d = idea("\n".join(elenco) or "- nessun dato")
    urls = clips(d["parole_chiave"]) or clips("nature")
    segs = []
    for i, frase in enumerate(d["frasi"]):
        mp3 = f"a{i}.mp3"
        asyncio.run(edge_tts.Communicate(frase, "it-IT-IsabellaNeural").save(mp3))
        dur = durata(mp3) + 0.4
        clip = f"c{i}.mp4"
        open(clip, "wb").write(requests.get(urls[i % len(urls)], timeout=120).content)
        open(f"t{i}.txt", "w", encoding="utf-8").write(textwrap.fill(frase, 24))
        vf = (f"scale=-2:1920,crop=1080:1920,drawtext=fontfile={FONT}:textfile=t{i}.txt:"
              "fontsize=64:fontcolor=white:borderw=6:bordercolor=black:line_spacing=12:"
              "x=(w-text_w)/2:y=h*0.62")
        subprocess.run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", clip, "-i", mp3,
                        "-t", str(dur), "-vf", vf, "-af", "apad", "-map", "0:v", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", f"s{i}.mp4"],
                       check=True, capture_output=True)
        segs.append(f"s{i}.mp4")
    open("list.txt", "w").write("".join(f"file '{s}'\n" for s in segs))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", "final.mp4"], check=True, capture_output=True)
    invia_video(d)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        extra = ""
        if isinstance(e, subprocess.CalledProcessError) and e.stderr:
            extra = e.stderr.decode(errors="ignore")[-600:]
        tg("Errore video: " + str(e)[:500] + "\n" + extra)
        raise
