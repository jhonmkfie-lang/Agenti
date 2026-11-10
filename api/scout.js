module.exports = async (req, res) => {
  const key = process.env.YT_KEY;
  const since = new Date(Date.now() - 24*3600*1000).toISOString();
  const s = await fetch(`https://www.googleapis.com/youtube/v3/search?part=id&type=video&order=viewCount&publishedAfter=${since}&maxResults=50&key=${key}`);
  const sd = await s.json();
  const ids = (sd.items || []).map(i => i.id.videoId).join(",");
  if (!ids) return res.status(200).json(sd);
  const v = await fetch(`https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=${ids}&key=${key}`);
  const vd = await v.json();
  const top = (vd.items || [])
    .filter(x => Number(x.statistics.viewCount) >= 1000000)
    .map(x => ({
      titolo: x.snippet.title,
      canale: x.snippet.channelTitle,
      views: x.statistics.viewCount,
      link: "https://youtube.com/watch?v=" + x.id
    }));

  const invia = async (t) => {
    for (let i = 0; i < t.length; i += 3900) {
      await fetch(`https://api.telegram.org/bot${process.env.TG_TOKEN}/sendMessage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: process.env.TG_CHAT, text: t.slice(i, i + 3900), disable_web_page_preview: true })
      });
    }
  };

  const testo = top.length
    ? "🔥 Video virali ultime 24h:\n\n" + top.slice(0, 10).map((x, i) =>
        `${i+1}. ${x.titolo}\n${x.canale} - ${Number(x.views).toLocaleString("it-IT")} views\n${x.link}`
      ).join("\n\n")
    : "Oggi nessun video sopra 1 milione.";
  await invia(testo);

  if (top.length && process.env.GEMINI_KEY) {
    const elenco = top.slice(0, 10).map(x => `- ${x.titolo} (${x.canale}, ${x.views} views)`).join("\n");
    const prompt = `Sei un esperto di contenuti virali. Ecco i video più virali delle ultime 24 ore su YouTube:\n${elenco}\n\nRispondi in italiano, in modo semplice e breve.\n1) Spiega in 3 punti cosa hanno in comune e perché funzionano.\n2) Dai 3 idee di video ORIGINALI ispirate a questi trend (non copiare nessun video). Per ognuna: titolo, frase di apertura dei primi 3 secondi e copione di circa 30 secondi.`;
    try {
      const g = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${process.env.GEMINI_KEY}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
      });
      const gd = await g.json();
      const out = gd.candidates?.[0]?.content?.parts?.map(p => p.text).join("") || ("Errore AI: " + JSON.stringify(gd).slice(0, 300));
      await invia("🧠 Analisi e idee originali:\n\n" + out);
    } catch (e) {
      await invia("Errore AI: " + e.message);
    }
  }
  res.status(200).json(top);
};
