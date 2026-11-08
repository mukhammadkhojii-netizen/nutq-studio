# Nutq Studio

Oʻzbek, rus va ingliz tilida matnni ovozga aylantiruvchi sayt (Neuron AI + ElevenLabs uslubida).

- **Bepul va kalitsiz:** Microsoft Edge neyron ovozlari (`edge-tts`): oʻzbekcha (Madina, Sardor va ularning 5 ta uslubi, jami 12 ovoz), ruscha, inglizcha
- **Ixtiyoriy (Aisha AI):** `AISHA_API_KEY` qoʻysangiz, Gulnoza ovozi va uning 4 kayfiyati (neutral, cheerful, happy, sad) qoʻshiladi. Bepul tarifda oyiga taxminan 10 000 belgi, ommaviy saytda tez tugashi mumkin.
- **Ixtiyoriy:** `NEURONAI_API_KEY` yoki `ELEVENLABS_API_KEY` qoʻysangiz, ularning ovozlari ham roʻyxatga qoʻshiladi
- **Boʻlimlar:** Matn → Ovoz, Dialog (koʻp ovoz), Ovozlar kutubxonasi, Tarix
- API kalitlari faqat serverda saqlanadi, brauzerga chiqmaydi

## Lokal ishga tushirish

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Brauzerda: http://localhost:8000

## GitHub + Render orqali joylash

1. Papkani GitHub’ga yuklang (`.env` yuklanmaydi, `.gitignore` himoya qiladi).
2. https://render.com → **New → Blueprint** → GitHub repo’ni tanlang (`render.yaml` oʻqiladi).
3. Deploy tugagach sayt tayyor, kalit kerak emas.

> GitHub Pages ishlamaydi: unda faqat statik fayllar boʻladi, API kalit esa serverda turishi shart.

## Muhim

- Edge ovozlari Microsoft’ning rasmiy boʻlmagan, ochiq xizmatidan foydalanadi (`edge-tts`). Bepul, lekin Microsoft uni istalgan payt oʻzgartirishi yoki cheklashi mumkin. Ovoz chiqmay qolsa: `pip install -U edge-tts`.
- Katta tijorat loyihasi uchun rasmiy xizmat (Azure Speech, ElevenLabs yoki Neuron AI) ishonchliroq.
- `RATE_PER_MIN` va `MAX_CHARS` sozlamalari suiiste’moldan himoya qiladi.
