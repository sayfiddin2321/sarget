# CRM-ni PostgreSQL-ga o'tkazish bo'yicha qo'llanma

Ushbu qo'llanma Sarget CRM ma'lumotlar bazasini SQLite-dan PostgreSQL-ga xavfsiz o'tkazish bosqichlarini o'z ichiga oladi.

---

## 1. PostgreSQL-da ma'lumotlar bazasi va foydalanuvchi yaratish

Linux serverda (PostgreSQL o'rnatilgan bo'lsa):

```bash
sudo -u postgres psql
```

SQL buyruqlari:

```sql
CREATE DATABASE sargetcrm ENCODING 'UTF8';
CREATE USER sargetuser WITH PASSWORD 'kuchli_parol_kiriting';
ALTER ROLE sargetuser SET client_encoding TO 'utf8';
ALTER ROLE sargetuser SET default_transaction_isolation TO 'read committed';
ALTER ROLE sargetuser SET timezone TO 'Asia/Tashkent';
GRANT ALL PRIVILEGES ON DATABASE sargetcrm TO sargetuser;
\c sargetcrm
GRANT ALL ON SCHEMA public TO sargetuser;
\q
```

---

## 2. CRM `.env` faylini sozlash

`c:\Users\User\Desktop\sargetcrm_CRM\.env` (yoki Linux serverda `/opt/sargetcrm/.env`) fayliga quyidagi qatorlarni qo'shing yoki o'zgartiring:

```ini
# Ma'lumotlar bazasi sozlamalari
DB_ENGINE=postgres
DB_NAME=sargetcrm
DB_USER=sargetuser
DB_PASSWORD=kuchli_parol_kiriting
DB_HOST=localhost
DB_PORT=5432
DB_CONN_MAX_AGE=60
```

---

## 3. Mavjud SQLite ma'lumotlarini PostgreSQL-ga ko'chirish (Agar mavjud bo'lsa)

Agar sizda SQLite (`db.sqlite3`) da mavjud talabalar, to'lovlar, guruhlar bo'lsa, ularni PostgreSQL-ga ko'chirish:

### 1-qadam: SQLite-dan ma'lumotlarni eksport qilish (DB_ENGINE=sqlite holatida)
```bash
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission --indent 2 > datadump.json
```

### 2-qadam: .env faylida PostgreSQL-ga o'tish
`.env` faylida `DB_ENGINE=postgres` qilib saqlang.

### 3-qadam: PostgreSQL-da jadvallarni yaratish
```bash
python manage.py migrate
```

### 4-qadam: Ma'lumotlarni PostgreSQL-ga yuklash
```bash
python manage.py loaddata datadump.json
```

Yuklash tugagach, `datadump.json` faylini xavfsizlik uchun o'chirib tashlashingiz mumkin:
```bash
rm datadump.json  # yoki Windows-da: Remove-Item datadump.json
```

---

## 4. Baza ishlashini tekshirish

```bash
python manage.py check
python manage.py test core.test_bot_api core.test_bot_api_extra
```

Hammasi muvaffaqiyatli o'tsa, CRM server to'liq PostgreSQL bilan ishlaydi!
