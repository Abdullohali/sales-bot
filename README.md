# Sales Bot — sotuvlarni hisobga olish uchun Telegram-bot va admin panel

Ulgurji meva-sabzavot savdosi uchun. Dostavchik sotuvni botga yozadi, bot NDS'ni hisoblaydi va naklad (Excel) yaratadi. Buxgalteriya tayyor ma'lumotni bot yoki admin panel orqali oladi.

Asos: `TZ_telegram_bot_uchet_prodazh.md` (v1.1) va `telegram_bot_admin_panel_reja.md`.

## Stek

Python 3.12 · aiogram 3 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 + Alembic · SQLAdmin · Redis (FSM) · openpyxl · Docker Compose + Caddy · Sentry

## Arxitektura

```
Telegram ──webhook──► Caddy (HTTPS) ──► FastAPI (bitta jarayon)
                                          ├── /webhook  → aiogram (bot)
                                          ├── /admin    → SQLAdmin (panel)
                                          ├── /health
                                          └── services/ → umumiy biznes-mantiq (NDS, naklad, hisobot, Excel)
                                                  │
                                            PostgreSQL ◄── pg_dump (kunlik)
                                            Redis (yarim tugagan nakladlar)
```

Biznes-mantiq faqat `app/services/` ichida. Bot ham, panel ham shu qatlamni chaqiradi, shuning uchun hisob-kitob ikki joyda ikki xil chiqmaydi.

```
app/
├── config.py            sozlamalar (.env)
├── main.py              FastAPI: webhook, /admin, /health
├── cli.py               python -m app.cli create-admin
├── db/                  modellar, sessiya, Alembic migratsiyalari
├── services/            vat · formatting · clock · catalog · sales · reports · excel
├── bot/                 middleware (rol), keyboards, states, parsers, notify, handlers/
└── admin/               auth (bcrypt, rollar), views, pages (hisobot/eksport/import), templates/
tests/                   95 ta test (SQLite va PostgreSQL'da)
scripts/                 backup.sh, restore.sh
```

## Lokal ishga tushirish

```bash
uv sync                                          # bog'liqliklar
cp .env.example .env                             # BOT_TOKEN, ADMIN_IDS ni to'ldiring; WEBHOOK_BASE_URL bo'sh qolsin
docker compose -f docker-compose.dev.yml up -d   # Postgres + Redis
uv run alembic upgrade head
uv run python -m app.cli create-admin admin      # panel uchun login
uv run uvicorn app.main:app --reload             # bot (polling) + panel: http://localhost:8000/admin
```

`WEBHOOK_BASE_URL` bo'sh bo'lsa, bot polling rejimida ishlaydi (lokal uchun). To'ldirilgan bo'lsa, webhook o'rnatiladi. `BOT_TOKEN` bo'sh bo'lsa, faqat panel ishlaydi.

Testlar:

```bash
uv run pytest                                                         # SQLite
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/test uv run pytest   # PostgreSQL
uv run ruff check app tests
```

## Serverga deploy (VPS)

1. Serverda Docker o'rnating. Domen A-yozuvi server IP'siga qarasin.
2. `git clone ... /opt/sales-bot && cd /opt/sales-bot`
3. `cp .env.example .env` va to'ldiring: `BOT_TOKEN`, `ADMIN_IDS`, `DOMAIN`, `WEBHOOK_BASE_URL=https://<DOMAIN>`, `WEBHOOK_SECRET`, `ADMIN_SECRET_KEY`, `POSTGRES_PASSWORD`, `COMPANY_NAME`, `COMPANY_INN`. Maxfiy qiymatlar uchun: `openssl rand -hex 32`.
4. `docker compose up -d --build`. Caddy HTTPS sertifikatini o'zi oladi. Migratsiyalar har start'da avtomatik qo'llanadi.
5. Panel uchun admin yarating: `docker compose exec app python -m app.cli create-admin admin`
6. Zaxira nusxa uchun cron: `15 3 * * * cd /opt/sales-bot && ./scripts/backup.sh >> backups/backup.log 2>&1`. Tashqi joyga nusxa uchun `RCLONE_REMOTE` ni sozlang.
7. **Tiklashni kamida bir marta sinab ko'ring:** `./scripts/restore.sh backups/<fayl>.sql.gz` (staging serverda).

Barcha servislarda `restart: always` bor, shuning uchun server qayta yuklansa bot o'zi ko'tariladi (TZ §10). CI (`.github/workflows/ci.yml`) lint, SQLite va PostgreSQL'da testlar va migratsiya tekshiruvini bajaradi. Avto-deploy uchun repo'da `DEPLOY_ENABLED=true` o'zgaruvchisi va `DEPLOY_HOST/USER/SSH_KEY` secret'lari kerak.

## Fayldan yuklash

Mahsulotlar, mijozlar va kuryerlar `.xlsx` yoki `.csv` fayl orqali birdaniga yuklanadi: panelda har bir bo'limning (Mijozlar, Mahsulotlar, Kuryerlar) ro'yxatidagi **Fayldan yuklash** tugmasi, botda faylni yuborish (turi sarlavhadan aniqlanadi), namunalar `/template`. Fayl tuzilishi qoidalari: [docs/import-format.md](docs/import-format.md). Kod: `app/services/importer.py` (`SCHEMAS` o'zgarsa, hujjatni ham yangilang).

## Tillar (uz / ru / en)

Barcha matnlar `app/i18n/` ichida: `uz.py`, `ru.py`, `en.py` (kalitlar bir xil, test tekshiradi).

- **Bot:** til `/lang` yoki menyudagi «🌐» tugmasi bilan tanlanadi va `bot_users` jadvalida saqlanadi. Tanlanmagan bo'lsa, Telegram ilovasi tili, u ham mos kelmasa `DEFAULT_LANGUAGE` ishlatiladi. Yuk xati (Excel) har bir qabul qiluvchiga o'z tilida yuboriladi.
- **Panel:** yuqoridagi til tanlagich (login sahifasida pastda), tanlov cookie'da saqlanadi. Aks holda brauzer tili, keyin `DEFAULT_LANGUAGE`.
- **Excel import** ustun nomlarini uchala tilda ham taniydi.
- Mijoz, mahsulot nomlari va o'lchov birliklari (ma'lumotlar) tarjima qilinmaydi.
- Yangi matn qo'shish: kalitni uchala faylga qo'shing va `t(lang, "kalit")` (bot) yoki `pt("kalit")` / shablonda `{{ t("kalit") }}` (panel) bilan chaqiring.

## Rollar

| Rol | Qayerda | Nima qila oladi |
|---|---|---|
| Administrator | bot (`ADMIN_IDS`) | hammasi: katalog, import, hisobot, eksport, `/delsale`, sotuv yozish |
| Dostavchik | bot (`/courier ID Ism`) | faqat o'z sotuvini yozadi va bugungi o'z yetkazmalarini ko'radi |
| Begona | bot | hech narsa; "нет доступа" va o'z ID'si |
| admin | panel | hammasi, panel foydalanuvchilarini boshqarish ham |
| accountant (buxgalter) | panel | ko'rish, hisobot, Excel eksport; o'zgartira olmaydi |

Bot buyruqlari TZ §6 bo'yicha, qo'shimcha: `/invoice №` (nakladni qayta yuborish), `/delcourier ID`, `/cancel`.

## TZ'dan farqlar va qabul qilingan qarorlar

1. **`vat_rate` har bir qatorda saqlanadi** (snapshot). `VAT_RATE` o'zgarsa, eski nakladlar qayta hisoblanmaydi.
2. **Yaxlitlash qator darajasida, 0,01 gacha.** Jami summa yaxlitlangan qatorlar yig'indisi. Qator ichida `NDS = jami − NDSsiz summa`, shuning uchun har qatorda `NDSsiz + NDS = jami` aniq bajariladi. Narx NDS bilan kiritilgan bo'lsa, qator jami `miqdor × kiritilgan narx` ga teng (TZ §5.3), "yarim tiyin" holatlarida ham. **Buxgalter bilan tasdiqlash kerak**, qoida `app/services/vat.py` va `tests/test_vat_parsers_format.py` da.
3. **Naklad raqami** Postgres sequence orqali beriladi, bir vaqtda yozishda ham takrorlanmaydi. Saqlash xato bilan tugasa, raqamda bo'shliq qolishi mumkin (sequence xususiyati).
4. **O'chirish auditi:** `deleted_by` (`tg:<id>` yoki `web:<login>`) va `deleted_at`.
5. **IKPU ustuni 32 belgigacha.** Noto'g'ri IKPU ham ogohlantirish bilan saqlanadi (TZ §3.1). 17 belgida bunday qiymat bazaga sig'masdi.
6. **Admin ham sotuv yoza oladi.** Buning uchun u `couriers` jadvaliga avtomatik (nofaol holda) qo'shiladi.
7. **Yarim tugagan draft** Redis'da 24 soat saqlanadi (`FSM_TTL_SECONDS`). Undan keyin "Сессия устарела" chiqadi.
8. **"Завершить" ikki marta bosilsa,** ikkinchi naklad yaratilmaydi (`saving` holati).
9. Naklad yetkazib bo'lmagan admin (botga `/start` bosmagan) boshqalarga yuborishni to'xtatmaydi, faqat logga yoziladi.

## Ochiq savollar (buyurtmachidan)

- Yaxlitlash qoidasi (yuqoridagi 2-band) buxgalteriya / 1C bilan mosmi?
- Naklad raqami formati: oddiy (`17`) yoki `2026/001`?
- Lgotali (NDS'siz) tovarlar bormi? Ma'lumot modeli tayyor (`vat_rate = 0`), faqat tovarga belgi qo'shish kerak.
- Naklad klientga ham yuboriladimi? Qaytarishlar hisobga olinadimi?
- IKPU va birlik kodlari qayerdan olinadi (soliq katalogi yoki 1C)?
- Panelda nechta buxgalter bo'ladi?

## Keyingi bosqichlar (TZ §11)

Tannarx va marja · klient qarzlari · ESF integratsiyasi · 1C eksport · imzoli naklad fotosi · nakladni tahrirlash (audit bilan) · kerak bo'lsa React/Refine panel (`/api`).
