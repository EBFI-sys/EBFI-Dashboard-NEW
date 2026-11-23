# EBFI PRIVATE LIMITED — Инструкция по подготовке инвойсов (FY 2026-27)

Этот файл — полная база знаний для Claude по выставлению инвойсов EBFI. Вместе с ним в проект загружены образцы инвойсов (по одному на клиента, папка `Samples`). **Новый инвойс всегда делается копированием последнего инвойса того же клиента** и заменой данных — не с нуля.

---

## 1. Общие правила

| Параметр | Значение |
|---|---|
| Компания-выставитель | EBFI PRIVATE LIMITED, 804/805/806 The Ambience Court, Opp. RTO Office, Sector-19 D, Vashi, Navi Mumbai – 400 703 |
| GST EBFI | 27AAGCE2751D1ZW · PAN AAGCE2751D · MSME DYAM-MH-33-0179555 |
| Банк | ICICI Bank, A/c 095705001599, SWIFT ICICINBBNRI, IFSC ICIC0000957, Branch: Tirupati Compl. Plot #3 Sec-44, Seawood, Navi Mumbai 400706 (блок «Receiver Details / Bank Details» внизу каждого инвойса — не трогать) |
| Номер инвойса | `EBFI-2627-NNN` — сквозная нумерация по всем клиентам и месяцам, никогда не сбрасывается |
| Следующий свободный номер (на 23.11.2026) | **EBFI-2627-297** |
| Исправление инвойса | Используется **тот же номер**, новый номер не создаётся |
| Дата инвойса | Последний день месяца работ (31-October-2026, 30-September-2026). Исключения: морские сюрвеи SPEX/TUV Austria и DITH — дата выставления |
| Формат даты в шапке | `Dated: 31-October-2026` |
| Due Date | Всегда `ADVANCE` |
| Строка «Performance Date» | `Performance Date: October` (месяц работ) |
| Папки | `Desktop/Claude/Invoicing/Sales <Month>/<Client>/EBFI-2627-NNN.docx` |
| Источник данных | Табель (Timesheet) — единственный источник. Лист текущего месяца, напр. «Октябрь 2026» |

### Структура шапки (правая ячейка)
```
Dated: 31-October-2026
Invoice No: EBFI-2627-NNN
Currency: USD            (или EUR / EURO / USD/INR / EUR/INR / INR — как в образце клиента)
Due Date: ADVANCE
Place of Supply: CHINA, KOREA      (все страны инвойса через запятую, ЗАГЛАВНЫМИ)
Ref.code.no: 26.21                 (префикс серии работ; у морских сюрвеев — полный номер работы 26.18-104)
```

### Таблица инвойса
Строки: 0 = заголовок `INVOICE № EBFI-2627-NNN` · 1 = TO / шапка · 2 = `No | Description | Unit | Qty. | Unit Price | Total Price` · 3 = Performance Date · 4…n = строки услуг · далее итоговый блок · последняя строка = Receiver Details + банк.

- В колонке **No** — номер работы EBFI (напр. `26.19-457`).
- Ячейки цены = **2 абзаца**: число и валюта (`205` / `USD`). Никогда не писать символ `|`.
- Единицы: `Man-Day`, `Man-Hour` (Qualcon), `MT`, `Per Lot`, `Pcs`, `OT`.
- Если по одной работе несколько инспекторов/заводов/дат с разной ставкой — отдельная строка на каждого.

---

## 2. Табель (Timesheet) — колонки (раскладка с октября 2026)

| Кол. | Поле | Использование |
|---|---|---|
| A | Client Name | Клиент → определяет шаблон |
| B | Client Project Coordinator | → «Project Coordinator: …» |
| C | Job number | Номер работы EBFI → колонка No |
| D | Client Job Number / Client Name | → SAP / Job.Ref.No / Client / BV Job № (по клиенту) |
| E | Vendor Name | → «Vendor name: …» |
| F | Country | → «… in COUNTRY.» и Place of Supply |
| G | Inspector Name | → «Inspector name: …» |
| H | Date | → «Dates: …» (формат `05,06,07.10.2026`) |
| I | Total (кол-во дней) | Qty |
| J | Валюта: 1 = USD, 2 = EUR | |
| K | Manday Rate | Unit Price |
| L | Мы платим | **Внутреннее — в инвойс не идёт** |
| M | Overtime — нам платят | Если > 0 → отдельная строка OT (см. ниже) |
| N | Overtime — мы платим | Внутреннее, не выставляется |

Ошибки в табеле исправлять разумно: несуществующие даты (31.09 → 30.09); «China .» → CHINA.
Колонку G (инспектор) и B (координатор) **не путать** — в старых шаблонах они были перепутаны.

**Overtime (клиент платит):** отдельная строка: для TUV Rheinland / BV — описание «Over-Time», для SPEX — Unit `OT`, Qty 1, цена = сумма OT. В Annexure — колонка OVERTIME.

---

## 3. Форматы чисел

| Где | Формат | Пример |
|---|---|---|
| INR (Индия) | индийская группировка, 2 знака | `16,25,746.80 INR`, `1,46,317.21` |
| USD/EUR стандарт (BV, TUV, LRQA, SPEX Germany, Qualcon, Italy) | запятая — тысячи | `4,920 USD`, `12,320` |
| Морские сюрвеи (SPEX HK, TUV Austria) | европейский: пробел — тысячи, запятая — десятичные; знак `$` | `47 944,830` MT, `0,17 $`, `8 151 $` |
| DITH (как в образце) | вес `31,497.860`, ставка `0,17`, сумма `5 355` | |

---

## 4. Индийский GST (клиенты в Индии)

Клиенты с GST: **TUV Rheinland India, TUV NORD (TUV India), LRQA India, MAS Marine, ISSPL**.

```
base_inr = round(total_fc × курс, 2)
CGST 9% = round(base_inr × 0.09, 2)
SGST 9% = round(base_inr × 0.09, 2)
TOTAL   = base_inr + CGST + SGST
```
- **ISSPL (Delhi, другой штат)** — вместо CGST+SGST одна строка **IGST 18%**.
- Итоговый блок: `Total Amount in USD/EUR` (кроме TUV Rheinland India — у них сразу INR) → `Total Amount in Indian Rupees | Rate 1 USD | 95.24 | INR | сумма INR` → `CGST 9%` → `SGST 9%` → `TOTAL AMOUNT`.
- Курс задаёт пользователь (курс RBI на последний день месяца / предыдущий день), 2 знака. Если курс не дан — **спросить**.
- История курсов: Апр 94.78 / 110.88 · Май 95.78 / 111.49 · Авг 95.45 / 110.60 · Сен 95.98 / 108.94 · **Окт 95.24 / 106.54** (USD/INR / EUR/INR).
- Если визиты одной работы были в разные даты с разными курсами (по запросу клиента) — разбить на строки по датам, в ячейке курса указать оба курса (пример: 249, 108.3 / 106.5).

---

## 5. Правила по клиентам

### 5.1 TUV Rheinland India (+ TUV Rheinland LT) — образцы 241 (USD), 244 (LT, EUR)
- TO: TÜV Rheinland (India) Pvt. Ltd., Office Number 904 to 910, 9th Floor, Damji Shamji Business 78, Near Kanjurmarg Station, Kanjurmarg (West), Mumbai-400078, GST No: 27AAACT7736P1ZN
- Шапка: `Invoice Date: 31-October-2026` + `Date of final Submission : 05-November-2026` (5-е число след. месяца), Currency `USD/INR` или `EUR/INR`, Ref.code.no `26.19`.
- Группировка: **по валюте** (USD → один инвойс, EUR → другой); TUV Rheinland LT — отдельные инвойсы (USD/EUR).
- **Лимит: инвойс не более ₹20,00,000 с GST** → если больше, делить по номерам работ на несколько инвойсов (каждый со своим Annexure).
- Строка услуги (основной): `Inspection Services in CHINA.` / `Inspector name: …` / `Dates: …` / `Vendor name: …` / `Project Coordinator: …` / `SAP Number: …` (из колонки D/данных клиента).
- Строка LT: `Inspection Services in SWEDEN.` / `Inspection subject:` / `Dates:` / `Vendor name:` / `Coordinator name:` / `SAP Number:`
- Итог: без строки USD — сразу `Total Amount in Indian Rupees` + курс → CGST → SGST → TOTAL AMOUNT.
- **К каждому инвойсу — Annexure `EBFI-2627-NNN_Annexure.xlsx`**: шапка (Invoice number, дата = дата подачи, месяц, курс), колонки: TUV SAP Number | EBFI JOB № | DATE | DAYS | TUV CLIENT | VENDOR NAME | PLACE OF INSPECTION | INSPECTION DETAIL | INSPECTOR NAME | DAY RATE (USD/EUR) | DAY RATE (INR) | TOTAL AMOUNT INR | TOTAL AMOUNT (INR) WITH GST | OVERTIME | COORDINATOR NAME; строка TOTAL. Суммы Annexure = суммам инвойса.
- 26.19-387 (Parker Hannifin) исключена из инвойсов LT EUR.

### 5.2 TUV NORD (TUV India Pvt. Ltd.) — образец 246
- TO: TUV INDIA PVT. LTD, 801, Raheja Plaza, LBS Marg, Ghatkopar (W) Mumbai - 400 086, Tel.: +91 22 6647 7000, Fax: +91 22 2579 1301, GST No: 27AAACT2209D2ZT
- **Один инвойс на один номер работы (26.07-xxx)** (подтверждено с сент. 2026).
- Строка: `Conducting a technical inspection (pre-shipment) at BRAZIL.` / `Vendor name:` / `Dates:` / `Project Coordinator:` / `Client:` / `SAP:` (если есть; иначе пусто — TUV Job Number заполняется вручную).
- Итог: `Total Amount in USD` → INR + курс → CGST 9% → SGST 9% → TOTAL AMOUNT.

### 5.3 LRQA India — образец 260
- TO: LRQA Inspection Services India LLP, Solitaire Corporate Park, Building no. 12, 4th Floor, Andheri - Kurla Road, Chakala, Andheri East, Mumbai - 400059, Maharashtra. GST No: 27AAIFL3381M1ZU
- **Один инвойс на работу (26.16-xxx)**. Есть INR + CGST/SGST.
- Шапка: `Dated: 31-October-2026Date of submission: 05.11.2026` (5-е след. месяца).
- Строка: `Inspection Services in FRANCE.` / `Inspection subject:` / `Dates:` / `Project No: 26.16-108` / `Vendor name:` / `PO No.` / `Inspector name:`

### 5.4 LRQA Singapore — образец 264
- TO: LRQA Singapore, 460 Alexandra Road #15-01, M Tower, Singapore 119963. Без GST.
- **Отдельный инвойс на каждый номер работы (26.31-xx) и на каждую валюту**; разные вендоры внутри одной работы — строками в одном инвойсе.
- Строка: `Inspection Services in MEXICO.` / (пустая строка) / `Vendor name:` / `Dates:` / `Inspector name:`
- Итог: `Total Amount in USD`.

### 5.5 BV Singapore — образец 252
- TO: Bureau Veritas Singapore Pte Ltd, 28 Ayer Rajah Crescent #04-01, (S) 139959, Reg.number 200209266D. Без GST.
- Группировка: USD-инвойс, EUR-инвойс, **отдельно по координатору**; **Markus Ehrmann — всегда отдельный инвойс**; отдельные работы — по просьбе координатора.
- Строка: `Conducting a technical inspection in CHINA.` / `Vendor name: …` / `Dates:` / `Project Coordinator:` / `Inspector Name:` / (BV Job Number — только для SGP-работ).
- **RLPP — внутренний код, никогда не показывать.**

### 5.6 BV Indonesia — образец 257
- TO: PT. Bureau Veritas Indonesia, Wisma 76 Lantai 21 Jalan Letjen S. Parman Kav 76 RT 004 RW 003, Slipi, Palmerah, Jakarta Barat – 11410. Без GST. Отдельный клиент от BV Singapore. Группировка по валюте. Формат строки как у BV Singapore.

### 5.7 BV USA — образец 259
- TO: Praveen Tiwari, Bureau Veritas North America, INC., 16800 Greenspoint Park Drive, Suite 300S Houston, TX 77060.
- Строка как у BV + последняя строка `Job.Ref.No: [колонка D]`.

### 5.8 TUV Rheinland Qatar — образец 273
- TO: TUV Rheinland Gulf LLC, Office C103, 1st Floor, Arkan 25, The Commercial Avenue, Building No. 3, Street 964, Zone 56, P.O. Box 31272, Doha – Qatar.
- **Один инвойс на работу (26.29-xx)**.
- Строка: `Conducting a technical inspection at SWEDEN.` / `Vendor name:` / `Dates:` / `Project Coordinator:` / `Inspector name:` / `Client:`
- Итог с **удержанием налога 5%**: `Amount in USD 700` → `Withholding Tax 5% 35` → `TOTAL AMOUNT 665`.

### 5.9 SPEX Quality Service GmbH (Германия, «ISPEX», серия 26.05) — образец 289
- TO: SPEX Quality Service GmbH, Fritz-Vomfelde-Str. 34, 40547 Düsseldorf, Germany. USD, без GST.
- Все работы месяца — в один инвойс (отдельные работы можно вынести по запросу, как 289).
- Строка: `Conducting a technical inspection` / `Place of inspection: INDIA` / `Vendor name:` / `Date of inspection:` / `Job number: SG-JC26-10.2394` (номер SPEX из колонки D). Без координатора/инспектора.
- OT → отдельная строка, Unit `OT`, Qty 1.

### 5.10 SPEX CONSULTANCY CO., LIMITED (Гонконг) — морские сюрвеи, серия 26.18 — образец 296
- TO: SPEX CONSULTANCY CO., LIMITED, 6/F RFCM, Manulife Place, 348 Kwun Tong Road, Kowloon, Hong Kong
- **Каждое судно — отдельный инвойс.** Дата — дата выставления. Ref.code.no = полный номер работы (26.18-104). Place of Supply — страна погрузки.
- Каждая строка: `Conducting a … ` / `Place of inspection: Argentina.` / `MV <судно>` / (`TAD-000x`, если дан) / `Date of inspection: November 2026` / `Job number: <номер SPEX, если дан, иначе пусто>`
- Европейский формат чисел. Ставки — см. раздел 6.

### 5.11 TÜV AUSTRIA SINGAPORE PTE. Ltd. — образец 231
- TO: TÜV AUSTRIA SINGAPORE PTE. Ltd., 4 Battery Road #25-01, (Bank of China Building), 049908, Singapore. USD, без GST.
- Тот же формат и ставки, что у морских сюрвеев SPEX HK (раздел 6). Каждое судно — отдельный инвойс. Job number вида `TAS-JC26-08.2064`.
- Внимание: инвойсы 193/194/195 сначала были выставлены на SPEX HK, затем сторнированы кредит-нотами CN-010/011/012 и перевыставлены на TUV Austria как 231/232/233 — **проверять плательщика**.

### 5.12 Qualcon, Inc. (США, серия 26.30) — образец 279
- TO: Qualcon, Inc., 100 West Court Square, Livingston, TN 38570, Phone (931) 400-2875.
- Почасовая ставка: Unit `Man-Hour`, напр. 161 × 42 USD. Строка: `Conducting a technical inspection` / `Place of inspection: JAPAN` / `Vendor name: Nippon Steel` / `Date of inspection: 01-31.10.2026` / `Job number: 26.30-01`.

### 5.13 DITH — DUFERCO ASIA PTE LTD (серия 26.04) — образец 239
- TO: DUFERCO ASIA PTE LTD, 3 Fraser Street, #08-23, Duo Tower, 189352 Singapore, DID: +65 6390 0108 / Fax: +65 6296 9018.
- Погрузка стальной продукции: `Conducting a pre-loading and loading inspection` / `MV <судно>` / `Vendor name:` / `Dates: 10.09.2026 - 03.10.2026` / `Project Coordinator: Rupa Rahate`; Unit MT, ставка 0,17 USD/MT. Отдельные инспекции на заводе — man-day строкой.
- Дата — дата выставления; разбивку по инвойсам даёт пользователь. (26.09 — это серия IEBFI, не DITH.)

### 5.14 APPLUS Indonesia — образец 290
- TO: PT Applus Teknologi dan Industri, Pondok Indah Office Tower 2, Suite 1602, Jl. Sultan Iskandar Muda KAV. V-TA, Kebayoran Lama, Jakarta Selatan 12310, Indonesia. Серия 26.32. Без GST. Валюта пишется `EURO`. Формат строки как у BV Indonesia.

### 5.15 EBFI Italy — ENGINEERING BUREAU FRANKE INTERNATIONAL SRLS — образец 291
- TO: viale IV novembre 69 G, Marina di Ravenna (Ra), 48122 Italia, P. IVA / VAT 04225561200, Cod. Fisc. 04225561200.
- Погрузка/маркировка: `Conducting a loading supervision` / `Vessel name: MV …` / `Equipment: Steel billets` / `Dates: 02-16.10.2026`; Unit MT; ставки 0.11 USD/MT (supervision), 0.03 USD/MT (colour coding). Серия 26.02.

### 5.16 ISSPL LIMITED (бывш. IRCLASS, Дели) — образец 234
- TO: ISSPL LIMITED, 104, Copia Corporate Suites, District Centre, Jasola, South Delhi, Delhi - 110025, GST No: 07AADCI5198M1ZZ. Серия 26.06.
- EUR/INR, **IGST 18%** (одной строкой). Строка: `Conducting a technical inspection at SPAIN.` / `Vendor name:` / `Equipment:` / `Dates:` / `Project Coordinator:` / `Inspector name:`

### 5.17 MAS MARINE SERVICES (INDIA) PVT LTD — образец 223
- TO: MEERA ARCADE, 1st & 2nd Floor, Sector 1-A, Gandhidham Kachchh, UDYAM-GJ-13-0005540, GSTIN 24AAFCM3371C1ZV, State Gujarat Code 24, CIN U93000GJ2007PTC051786, PAN AAFCM3371C. Серия 26.28.
- Ставка в табеле в EUR → **пересчитать в INR за день** (ставка × курс EUR/INR), весь инвойс в INR + CGST/SGST 9%. Place of Supply: `N/A`.

### 5.18 DNV — Germanischer Lloyd Industrial Services Italia Srl — образец 080
- TO: Via Energy Park, 14 20871 Vimercate (MB) ITALY, VAT Reg.n° IT11360150152. Серия 26.13. Без GST.
- В шапке Currency / Due Date / Place of Supply / Ref.code.no — **в одном абзаце**.
- Строка: `Conducting a technical inspection in USA.` / `Vendor name:` / `Dates:` / `Inspector: …` / `Coordinator: …` (порядок обратный BV).

### Клиенты без образца (появлялись в табеле, но не выставлялись)
IEBFI (26.09), PANDA, EBFIUK, 2R, Arvin, DYC и др. — при появлении **спросить пользователя** про шаблон, валюту и реквизиты.

---

## 6. Морские сюрвеи (SPEX HK / TUV Austria) — ставки

**Погрузка (Loading supervision), $/MT:**
| Груз / страна | Ставка | Формат |
|---|---|---|
| Зерно/сухие грузы, Аргентина | 0,17 | 3–4 строки |
| Зерно, Бразилия | 0,06 | 3 строки: lab 795 $ (composite) + draft 600 $ |
| Масло/наливные, Аргентина | 0,14 | 1 строка |
| Масло, Индонезия | **0,18** (с 13.11.2026, раньше 0,22) | 1 строка |
| Масло, Украина | 0,16 | 1 строка |
| Масло, Россия | 0,07 | 1 строка |

**Лабораторный анализ:**
- **Кукуруза (Corn)** — 1 композитная проба × 750 $ (Аргентина) / 795 $ (Бразилия); пестициды нет. 3 строки: loading + lab `(Composite)` + draft.
- **Соя / соевый шрот (SOYA, SBM) и прочие** — лоты: `lots = ceil(вес / 5000)` × 660 $ + **пестициды 1 лот × 150 $** отдельной строкой `Conducting a lab analysis (Pesticides)`. 4 строки.
- Draft survey: 1 Pcs × 700 $ (Аргентина), 600 $ (Бразилия).
- Количество лотов считать по весу, **не** из колонки Qty табеля.

**Расчёт:** `loading = round(вес × ставка)` (целые $); итог = сумма строк.
Пример (296, MV DRAFTVADER, Аргентина, соя, 47 944,830 MT): 8 151 + 10 × 660 = 6 600 + 700 + 150 = **15 601 $**.

---

## 7. Кредит-ноты — образец CN-2627-010
- Номер `CN-2627-NNN`, следующий — **CN-2627-013**.
- Это копия исходного инвойса; в строке 0 две строки: `INVOICE № CN-2627-NNN` / `CREDIT NOTE PASS AGAINST INVOICE № EBFI-2627-XXX`; `Dated` = дата кредит-ноты; остальное (Invoice No, суммы) — как в исходном инвойсе.
- Хранить в `Sales <Month>/<Client>/Credit Notes/`.

---

## 8. Оформление документа (обязательно на каждом инвойсе)
1. Шрифт **только Times New Roman** (rFonts ascii/hAnsi/cs/eastAsia в document.xml, styles.xml, header; убрать theme fonts).
2. Всё внутри таблицы — **10 pt** (`w:sz=20` на каждом run **и** на метке абзаца, включая строку 0 и Performance Date).
3. **Жирный — только** итоговый блок (Total Amount / Rate / CGST / SGST / IGST / Withholding / TOTAL AMOUNT) и строки «Receiver Details» / название компании. Строки услуг и шапка — не жирные.
4. Не ломать структуру: редактировать XML (python `zipfile` + `lxml`), строки услуг **клонировать** из существующей строки (`copy.deepcopy`), лишние удалять. Не пересоздавать документ через python-docx с нуля.
5. Текст абзаца заменять целиком в первом `w:t`, остальные `w:t` абзаца очищать (`xml:space="preserve"`).
6. После сборки — перечитать таблицу и сверить: номер, дата, валюта, Place of Supply, Ref.code.no, кол-ва × ставки, итог, GST.

---

## 9. Рабочий процесс (ежемесячно)
1. Получить табель месяца и курсы USD/INR, EUR/INR (если нужны).
2. Отфильтровать строки по клиенту; пропустить строки без кол-ва/ставки/работы — сообщить о них.
3. Сгруппировать по правилам клиента (раздел 5).
4. Присвоить номера по порядку с первого свободного.
5. Скопировать последний инвойс клиента → заменить данные → оформить (раздел 8). Для TUV Rheinland India — Annexure.
6. Проверить лимит ₹20 лакх (TUV Rheinland India).
7. Сохранить в `Sales <Month>/<Client>/`.
8. Дать пользователю сводку: № инвойса → клиент → работы → сумма; список пропущенных строк и вопросов.

**Если не хватает данных** (курс, номер SPEX/TAD, тип груза, плательщик, группировка) — спросить, не придумывать. Поле Job number можно оставить пустым и сообщить об этом.

---

## 10. Реестр номеров (кратко)
- Апрель 025–039 · Май 049–086 · Июнь 091–128 · Июль 129–161 · Август 162–195 · Сентябрь 196–238 · Октябрь 239–290 · Ноябрь 292–296 (291 = EBFI Italy).
- Последние: 292–295 SPEX HK (13.11), **296 SPEX HK MV DRAFTVADER 26.18-104 $15,601 (18.11)**.
- **Следующий номер: EBFI-2627-297. Следующая кредит-нота: CN-2627-013.**

## Образцы (папка Samples)
| Файл | Клиент |
|---|---|
| 01_TUV_Rheinland_India_USD_EBFI-2627-241 (+ Annexure.xlsx) | TUV Rheinland India |
| 02_TUV_Rheinland_LT_EUR_EBFI-2627-244 (+ Annexure.xlsx) | TUV Rheinland LT |
| 03_TUV_NORD_EBFI-2627-246 | TUV NORD / TUV India |
| 04_LRQA_India_EBFI-2627-260 | LRQA India |
| 05_LRQA_Singapore_EBFI-2627-264 | LRQA Singapore |
| 06_BV_Singapore_EBFI-2627-252 | BV Singapore |
| 07_BV_Indonesia_EBFI-2627-257 | BV Indonesia |
| 08_BV_USA_EBFI-2627-259 | BV USA |
| 09_TUV_Rheinland_Qatar_EBFI-2627-273 | TUV Rheinland Qatar |
| 10_SPEX_Germany_EBFI-2627-289 | SPEX Quality Service GmbH |
| 11_SPEX_HK_Marine_EBFI-2627-296 | SPEX Consultancy HK |
| 12_TUV_Austria_EBFI-2627-231 | TÜV Austria Singapore |
| 13_Qualcon_EBFI-2627-279 | Qualcon |
| 14_DITH_Duferco_EBFI-2627-239 | DITH / Duferco Asia |
| 15_APPLUS_Indonesia_EBFI-2627-290 | APPLUS Indonesia |
| 16_EBFI_Italy_EBFI-2627-291 | EBFI Italy (Franke) |
| 17_ISSPL_EBFI-2627-234 | ISSPL |
| 18_MAS_Marine_EBFI-2627-223 | MAS Marine |
| 19_DNV_EBFI-2627-080 | DNV (GL Italia) |
| 20_Credit_Note_CN-2627-010 | Формат кредит-ноты |

## Пустые шаблоны (папка Templates)
Файлы `TPL_NN_<Client>.docx` — те же образцы без цифр и данных работ: оставлены реквизиты клиента (блок TO), реквизиты и банк EBFI, все строки/столбцы, единицы, валюты и подписи итогов (CGST 9%, IGST 18%, Withholding Tax 5% и т.д.). Переменные поля помечены плейсхолдерами в квадратных скобках:
`[NNN]` номер инвойса · `[DD-Month-YYYY]` дата · `[DD.MM.YYYY]` дата подачи · `[Month]` месяц работ · `[COUNTRY]` · `[Job series]` · `[Job No]` · `[Vendor name]` · `[Inspector name]` · `[Coordinator name]` · `[Dates]` · `[SAP number]` · `[End client]` · `[Client job number]` · `[Vessel name]` · `[Qty]` · `[Rate]` · `[Amount]` · `[Exchange rate]`.
В каждом шаблоне одна строка услуги каждого типа — при заполнении её клонировать на нужное число строк. Все плейсхолдеры должны быть заменены; поля, для которых нет данных, оставить пустыми после двоеточия (например `Job number: `). TUV Rheinland India / LT — вместе с пустым `…_Annexure.xlsx` (адрес TÜV Rheinland в Annexure — тот же, что в инвойсе: Office Number 904 to 910, 9th Floor, Damji Shamji Business 78, Near Kanjurmarg Station, Kanjurmarg (West), Mumbai-400078; старый адрес D.S Business Galleria не использовать).
