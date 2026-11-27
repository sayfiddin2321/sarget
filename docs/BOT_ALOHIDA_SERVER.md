# Botni CRMdan ajratish — to'liq yo'riqnoma

## Qanday ishlaydi
```
Telegram  <──────►  [BOT SERVER]  ──HTTPS + API kalit──►  [CRM SERVER]
                    sarget_bot/bot.py                       Django (sayt + baza)
                    (faqat bot_state.sqlite3)               /api/bot/...
```
- Bot **bazaga tegmaydi**. Ariza, kurslar, ulash (/link), xabarlar — hammasi CRM API orqali.
- CRM -> Telegram yo'nalishi (hisobotlar, eslatmalar, xodimlarga bildirishnoma) **CRMda qoladi**:
  CRM tokenni ishlatib Telegramga to'g'ridan-to'g'ri yuboradi. Shuning uchun CRMda token qoladi,
  lekin CRM Telegramdan xabar **qabul qilmasligi** kerak (polling/webhook o'chiriladi).

## Nima uchun hozir serverda bot ishlamayapti
Serverda `DJANGO_DEBUG=False` bo'lgani uchun CRM botni *webhook* rejimida ishga tushirishga urinadi.
Buning uchun `.env` da `TELEGRAM_PUBLIC_URL` va `TELEGRAM_WEBHOOK_SECRET` kerak — ularda yo'q (secret bo'sh).
Ajratsangiz bu muammo yo'qoladi: bot alohida serverda *polling* bilan ishlaydi (HTTPS/domen shart emas).

## 1-qadam. CRM serverida (3 ta o'zgarish)
1. `crm_patch/core/api_bot_extra.py` ni CRMdagi `core/` papkasiga qo'ying (yangi fayl).
2. `core/urls.py` da 1 ta importga `api_bot_extra` qo'shing va `api/bot/courses/` qatoridan keyin 2 ta yo'l qo'shing
   (tayyor fayl: `crm_patch/core/urls.py`; o'zingiznikidan farqi faqat shu 3 qator).
3. CRM `.env`:
```
TELEGRAM_BOT_MODE=disabled      # CRM Telegramdan xabar olmaydi (buni bot serveri qiladi)
TELEGRAM_BOT_TOKEN=<token>      # QOLADI: CRM xabar yuborishi uchun
CRM_API_KEY=<uzun tasodifiy kalit>
```
Kalit yaratish: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
Keyin CRMni qayta ishga tushiring. CRM **HTTPS** orqali tashqaridan ochiq bo'lishi kerak.

## 2-qadam. Bot serverida
```bash
sudo mkdir -p /opt/sarget_bot && cd /opt/sarget_bot
# sarget_bot/ ichidagi fayllarni shu yerga ko'chiring (bot.py, requirements.txt, .env.example)
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env && nano .env
```
`.env` (CRM_API_KEY CRMdagi bilan **bir xil**):
```
TELEGRAM_BOT_TOKEN=...
CRM_API_URL=https://crm.sizning-domen.uz
CRM_API_KEY=...
```
Sinov: `./venv/bin/python bot.py` — Telegramda `/start` yuboring.
Doimiy ishlashi uchun: `sarget-bot.service` dagi `User` ni moslab `/etc/systemd/system/` ga qo'ying:
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now sarget-bot
sudo journalctl -u sarget-bot -f
```

## Muhim qoidalar
- **Bitta token — bitta qabul qiluvchi.** Lokal kompyuterda ham `runserver` botni polling qilmasin
  (lokalda `TELEGRAM_BOT_MODE=disabled` qiling yoki alohida test bot tokeni oling), aks holda Telegram "409 Conflict" beradi.
- Bot ichida suhbat holati `bot_state.sqlite3` da. Uni o'chirsangiz faqat tugallanmagan arizalar boshidan boshlanadi.
- CRM vaqtincha o'chiq bo'lsa, bot xabarni yo'qotmaydi: foydalanuvchiga "aloqa muammosi" deydi va qayta urinishni so'raydi.
- Bot (polling) uchun bot serveridan faqat chiquvchi ulanish kerak: `api.telegram.org` va CRM domeni.

## Tekshirish ro'yxati
1. `curl -H "X-CRM-API-Key: KALIT" https://crm.domen.uz/api/bot/courses/` -> `{"ok": true, "courses": [...]}`
2. Telegramda `/start` -> ism -> familiya -> kurs tugmalari -> telefon -> "Arizangiz qabul qilindi".
3. CRMda **Qabul** bo'limida yangi ariza paydo bo'lganini ko'ring.
4. CRMdan "Telegram ulash" kodi oling, botga `/link KOD` yuboring.

## XAVFSIZLIK (muhim)
Yuborgan zipingizdagi `.env` va `backups/` ichida **haqiqiy bot tokeni va baza** bor. Zipni kimgadir
jo'natgan bo'lsangiz, @BotFather -> `/revoke` bilan tokenni almashtiring va yangisini ikkala `.env` ga yozing.
Serverga `venv/` (Windows), `backups/`, `db.sqlite3` ni nusxalamang.
