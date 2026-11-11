import os, json, time, base64, asyncio, subprocess, textwrap, requests, edge_tts
from urllib.parse import quote
from datetime import datetime, timedelta, timezone

E = os.environ
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MODELLI = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
MODELLI_TTS = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]
VOCE = "Kore"
VOCE_ELEVEN = E.get("ELEVEN_VOICE") or "21m00Tcm4TlvDq8ikWAM"
STILE = ("colorful 2D cartoon animation style, Pixar-like illustration, soft lighting, "
         "expressive characters, vertical composition, no text, no letters")
avvisi = []

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
    prompt = ("Sei un creatore di YouTube Shorts a cartoni animati. Video virali di oggi:\n" + elenco +
        "\n\nInventa UNA mini storia ORIGINALE e coinvolgente in italiano, ispirata a questi trend "
        "(non copiare nessun video), con un personaggio simpatico e un po' di emozione. "
        "Rispondi SOLO con JSON con queste chiavi: "
        '"titolo", "descrizione" (con 3 hashtag), '
        '"personaggio" (descrizione in INGLESE, max 20 parole, dell\'aspetto del protagonista, uguale in tutte le scene), '
        '"frasi" (lista di 6 frasi italiane brevi: la prima è un gancio forte, l\'ultima invita a seguire il canale), '
        '"scene" (lista di 6 descrizioni in INGLESE, max 25 parole ciascuna, di cosa si vede nella scena di ogni frase, nello stesso ordine). '
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
                d = json.loads(t.replace("```json", "").replace("```", "").strip())
                if len(d["frasi"]) >= 3 and len(d["scene"]) >= len(d["frasi"]):
                    return d
            except Exception as e:
                ultimo = f"{modello}: {e}"
    raise Exception("AI non risponde. Ultimo errore: " + str(ultimo)[:300])

def durata(f):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f]).decode().strip())

def voce_eleven(frase, i):
    for modello in ("eleven_v3", "eleven_multilingual_v2"):
        try:
            body = {"text": frase, "model_id": modello}
            if modello == "eleven_multilingual_v2":
                body["voice_settings"] = {"stability": 0.35, "similarity_boost": 0.75,
                                          "style": 0.6, "use_speaker_boost": True}
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOCE_ELEVEN}",
                              params={"output_format": "mp3_44100_128"},
                              headers={"xi-api-key": E["ELEVEN_KEY"]}, json=body, timeout=90)
            if r.ok and len(r.content) > 2000:
                out = f"a{i}.mp3"
                open(out, "wb").write(r.content)
                if durata(out) > 0.5:
                    return out
            else:
                avvisi.append(f"ElevenLabs {modello}: {r.status_code} {r.text[:150]}")
        except Exception as e:
            avvisi.append(f"ElevenLabs {modello}: {str(e)[:100]}")
    return None

def voce_gemini(frase, i):
    testo = "Say with warm, expressive emotion like a cartoon narrator: " + frase
    for modello in MODELLI_TTS:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{modello}:generateContent?key={E['GEMINI_KEY']}",
                json={"contents": [{"parts": [{"text": testo}]}],
                      "generationConfig": {"responseModalities": ["AUDIO"],
                          "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOCE}}}}},
                timeout=90).json()
            inl = r["candidates"][0]["content"]["parts"][0]["inlineData"]
            raw = base64.b64decode(inl["data"])
            mime = inl.get("mimeType", "")
            out = f"a{i}.wav"
            if any(x in mime for x in ("wav", "mpeg", "ogg", "mp3")):
                open(f"raw{i}.bin", "wb").write(raw)
                cmd = ["ffmpeg", "-y", "-i", f"raw{i}.bin", out]
            else:
                rate = "24000"
                if "rate=" in mime:
                    rate = mime.split("rate=")[1].split(";")[0].strip()
                open(f"raw{i}.pcm", "wb").write(raw)
                cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", rate, "-ac", "1", "-i", f"raw{i}.pcm", out]
            subprocess.run(cmd, check=True, capture_output=True)
            if durata(out) > 0.5:
                return out
        except Exception as e:
            avvisi.append(f"voce Gemini ({modello}) non disponibile: {str(e)[:80]}")
    return None

def voce(frase, i):
    out = None
    if E.get("ELEVEN_KEY"):
        out = voce_eleven(frase, i)
    if not out:
        out = voce_gemini(frase, i)
    if out:
        return out
    avvisi.append("uso la voce base")
    mp3 = f"a{i}.mp3"
    asyncio.run(edge_tts.Communicate(frase, "it-IT-ElsaNeural", rate="-5%", pitch="+2Hz").save(mp3))
    return mp3

def img_pixabay(q, i):
    try:
        r = requests.get("https://pixabay.com/api/", params={
            "key": E["PIXABAY_KEY"], "q": q, "image_type": "illustration",
            "orientation": "vertical", "per_page": 10}, timeout=60).json()
        hits = r.get("hits", [])
        if hits:
            h = hits[i % len(hits)]
            u = h.get("largeImageURL") or h.get("webformatURL")
            c = requests.get(u, timeout=60).content
            open(f"img{i}.jpg", "wb").write(c)
            return f"img{i}.jpg"
    except Exception:
        pass
    return None

def immagine(scena, personaggio, i):
    p = f"{STILE}. {personaggio}. Scene: {scena}"[:600]
    url = "https://image.pollinations.ai/prompt/" + quote(p)
    for _ in range(3):
        try:
            r = requests.get(url, params={"width": 1080, "height": 1920, "model": "flux",
                                          "nologo": "true", "seed": 42 + i}, timeout=120)
            if r.ok and r.headers.get("content-type", "").startswith("image") and len(r.content) > 10000:
                open(f"img{i}.jpg", "wb").write(r.content)
                return f"img{i}.jpg"
        except Exception:
            pass
        time.sleep(20)
    avvisi.append("immagini Pollinations non disponibili per qualche scena, uso illustrazioni Pixabay")
    return img_pixabay(scena, i)

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
    personaggio = d.get("personaggio", "")
    segs = []
    ultima = None
    for i, frase in enumerate(d["frasi"]):
        if i > 0:
            time.sleep(16)
        audio = voce(frase, i)
        dur = durata(audio) + 0.4
        img = immagine(d["scene"][i], personaggio, i) or ultima
        if not img:
            raise Exception("nessuna immagine disponibile")
        ultima = img
        open(f"t{i}.txt", "w", encoding="utf-8").write(textwrap.fill(frase, 24))
        frames = int(dur * 30) + 2
        z = "1+0.00045*on" if i % 2 == 0 else "1.14-0.00045*on"
        vf = (f"scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps=30,"
              f"drawtext=fontfile={FONT}:textfile=t{i}.txt:fontsize=64:fontcolor=white:borderw=6:"
              "bordercolor=black:line_spacing=12:x=(w-text_w)/2:y=h*0.72,format=yuv420p")
        subprocess.run(["ffmpeg", "-y", "-i", img, "-i", audio, "-t", str(dur), "-vf", vf,
                        "-af", "apad", "-map", "0:v", "-map", "1:a",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", f"s{i}.mp4"],
                       check=True, capture_output=True)
        segs.append(f"s{i}.mp4")
    open("list.txt", "w").write("".join(f"file '{s}'\n" for s in segs))
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                    "-c", "copy", "final.mp4"], check=True, capture_output=True)
    invia_video(d)
    if avvisi:
        tg("Note: " + "; ".join(sorted(set(avvisi)))[:800])

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        extra = ""
        if isinstance(e, subprocess.CalledProcessError) and e.stderr:
            extra = e.stderr.decode(errors="ignore")[-600:]
        tg("Errore video: " + str(e)[:500] + "\n" + extra)
        raise
