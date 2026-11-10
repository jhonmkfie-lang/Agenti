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
  const testo = top.length
    ? "🔥 Video virali ultime 24h:\n\n" + top.slice(0, 10).map((x, i) =>
        `${i+1}. ${x.titolo}\n${x.canale} - ${Number(x.views).toLocaleString("it-IT")} views\n${x.link}`
      ).join("\n\n")
    : "Oggi nessun video sopra 1 milione.";
  await fetch(`https://api.telegram.org/bot${process.env.TG_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: process.env.TG_CHAT, text: testo, disable_web_page_preview: true })
  });
  res.status(200).json(top);
};
