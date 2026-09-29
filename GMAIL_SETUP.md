# InstaKids — Gmail API orqali kod yuborish

Bu loyiha endi Gmail SMTP/App Password ishlatmaydi. Email kodlari Gmail API orqali OAuth 2.0 bilan yuboriladi.

## 1. Google Cloud sozlash

1. Google Cloud Console'da yangi loyiha yarating yoki mavjud loyihani tanlang.
2. **Gmail API**ni Enable qiling.
3. Google Auth Platform → Branding bo‘limida OAuth consent screen'ni sozlang.
4. Testing rejimida bo‘lsa, o‘zingiz ishlatadigan Gmail manzilini **Test users** ro‘yxatiga qo‘shing.
5. Google Auth Platform → Clients → **Create Client** → **Desktop app** tanlang.
6. JSON faylni yuklab oling va StartApp papkasiga `credentials.json` nomi bilan qo‘ying.

Google rasmiy qo‘llanmasi: https://developers.google.com/workspace/gmail/api/quickstart/python

## 2. Paketlarni o‘rnatish

```bash
pip install -r requirements.txt
```

## 3. `.env`ni to‘ldirish

```env
GMAIL_SENDER_EMAIL=sizninggmail@gmail.com
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=token.json
```

## 4. Gmailni bir marta ulash

StartApp papkasida:

```bash
python manage.py gmail_auth
```

Brauzer ochiladi. Gmail akkauntingizni tanlang va ruxsat bering. Muvaffaqiyatli bo‘lsa `token.json` yaratiladi.

Keyingi safar sayt kod yuborganda App Password so‘ralmaydi. OAuth refresh token orqali Gmail API ishlaydi.

## 5. Saytni ishga tushirish

```bash
python manage.py migrate
python manage.py runserver
```

## Muhim

- `credentials.json` va `token.json`ni hech kimga yubormang va GitHub'ga yuklamang.
- `gmail.send` scope faqat email yuborish uchun ishlatiladi.
- Google API uchun OAuth 2.0 avtorizatsiyasi talab qilinadi.
- Agar OAuth consent screen Testing rejimida bo‘lsa, Gmail manzilingizni Test users'ga qo‘shing.
- `token.json` o‘chib ketsa, `python manage.py gmail_auth`ni qayta ishga tushiring.
