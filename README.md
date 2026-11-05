# Project Two Lead Hunter

Aplikace pro agenturu [Project Two](https://projectwo.com/), která automaticky vyhledává potenciální klienty,
**skutečně se dívá na jejich weby** (screenshoty + AI vizuální analýza), vyhodnocuje obchodní potenciál
a připravuje personalizované LinkedIn oslovení. Celé rozhraní je v češtině.

> Kvalitní firma + slabá digitální prezentace + ekonomický potenciál + vhodný obchodní moment = zajímavý lead.

Systém nepředpokládá, že každý špatný web znamená zájem o redesign. Neznámé hodnoty nikdy nepočítá jako nulu
a pokud nemá data, řekne to.

---

## Obsah

1. [Rychlý start](#rychlý-start)
2. [Architektura](#architektura)
3. [Co aplikace umí](#co-aplikace-umí)
4. [Scoring – jak se počítá](#scoring--jak-se-počítá)
5. [AI: Ollama a externí API](#ai-ollama-a-externí-api)
6. [Zdroje dat a legálnost](#zdroje-dat-a-legálnost)
7. [Automatizace](#automatizace)
8. [Outreach workspace a klávesové zkratky](#outreach-workspace-a-klávesové-zkratky)
9. [Bezpečnost](#bezpečnost)
10. [Konfigurace](#konfigurace)
11. [Vývoj a testy](#vývoj-a-testy)
12. [Známá omezení](#známá-omezení)

---

## Rychlý start

Požadavky: **Python 3.11+**, **Node.js 20+**, volitelně **[Ollama](https://ollama.com)** pro lokální AI.

**Nejjednodušší způsob (Windows / macOS / Linux):** stáhněte projekt a spusťte

- Windows: dvojklik na **`Spustit Lead Hunter.bat`**
- macOS: dvojklik na **`Spustit Lead Hunter.command`**
- nebo v terminálu: `python run.py`

Při prvním spuštění se vše nainstaluje (několik minut), pak se aplikace sama otevře v prohlížeči
na http://localhost:3000. Další spuštění trvají pár sekund. Ukončení: Ctrl+C / zavřít okno.

Alternativně skripty pro Linux/macOS:

```bash
./scripts/setup.sh      # nainstaluje závislosti, Chromium pro screenshoty, vytvoří DB
./scripts/start.sh      # spustí backend (API + worker + plánovač) a frontend
```

Otevřete **http://localhost:3000**. API dokumentace je na http://127.0.0.1:8000/docs.

### Spuštění v prohlížeči přes GitHub Codespaces (bez instalace)

Na GitHubu: **Code → Codespaces → Create codespace on `claude/quirky-wozniak-fx8c95`**. První spuštění
trvá několik minut (instalace), pak se aplikace otevře sama; jinak ji najdete v záložce **PORTS** (port 3000).
Adresa je soukromá – otevře ji jen váš přihlášený GitHub účet. Codespace se po ~30 minutách nečinnosti
uspí (s ním i automatizace) a znovu ho spustíte z GitHubu; data zůstávají uložená.

Doporučené první kroky:

1. **Nastavení → AI & systém** – zkontrolujte, zda je dostupná Ollama / vision model a Playwright.
2. **Vyhledávání** – zvolte obor (např. *Interiéroví designéři*) a kraj, zapněte „Rovnou analyzovat“.
3. **Leady** – sledujte, jak přibývají analyzované firmy se screenshoty a skóre.
4. **Oslovování** – zpracovávejte kvalifikované leady (30–60 s na lead).

Lokální AI (doporučeno, nulové náklady):

```bash
ollama pull qwen2.5vl:7b          # vision model (16+ GB RAM) – nebo qwen2.5vl:3b / llava:7b
ollama pull qwen2.5:7b-instruct   # textový model pro zprávy – nebo qwen2.5:3b-instruct
```

---

## Architektura

```
frontend/  Next.js 15 · TypeScript · Tailwind CSS 4 · shadcn/ui komponenty · Recharts · SWR
   └─ /api/* a /screenshots/* jdou přes serverový proxy (API token se nedostane do prohlížeče)

backend/   Python · FastAPI · SQLAlchemy 2 · Alembic · APScheduler · Playwright · httpx
   app/connectors/   konektory zdrojů (OSM/Overpass, ARES, Brave Search, Google CSE, ruční import)
   app/services/     crawler, screenshoty, technický audit, vision, signály, deduplikace,
                     LinkedIn asistent, generátor zpráv, follow-upy, learning, reporty
   app/scoring/      transparentní scoring engine
   app/jobs/         DB fronta úloh, worker vlákna, plánovač, handlery
   app/api/          REST API
   alembic/          migrace databáze
```

Databáze: **SQLite** (WAL režim) v `backend/data/`. Model nepoužívá SQLite-specifické typy, migrace na
PostgreSQL = nastavit `DATABASE_URL=postgresql+psycopg://…` a spustit `python -m app.cli migrate`
(+ `pip install psycopg[binary]`).

Entity: Companies, CompanySources (evidence původu), Contacts, Websites, Website Audits, Visual Analyses,
Buying Signals, Lead Scores (s historií), Outreach Messages, Outreach Events, Campaigns, Follow-up Tasks,
Automation Jobs, Data Sources, Suppression List, App Settings. Všechny mají `created_at` / `updated_at`,
cizí klíče s referenční integritou (`PRAGMA foreign_keys=ON`).

### Analytická pipeline jedné firmy

```
crawl webu (robots.txt, max 5 podstránek)  →  ARES (IČO z webu → právní forma, vznik, NACE,
→ jednatelé z obchodního rejstříku)  →  Playwright screenshoty (desktop + mobil homepage, služby,
portfolio, kontakt) + měření v prohlížeči  →  technický audit  →  vision analýza (15 kritérií)
→  nákupní signály  →  scoring  →  (automaticky) příprava zpráv
```

---

## Co aplikace umí

**Discovery engine** – konektory s jednotným rozhraním (`RawCompany`), každý s kontrolou dostupnosti,
rate limitingem, retry s exponenciálním čekáním, evidencí zdroje, logováním chyb a popisem povoleného
přístupu. Vyhledávání podle oboru, kraje, města, země (i zahraničí), klíčového slova a existence webu.
Priority regionů a segmentů jsou nastavitelné.

**Deduplikace** – IČO (s kontrolou kontrolní číslice) → normalizovaná doména (sdílené platformy jako
Webnode/Wix podle subdomény) → ID ve zdroji → název + město → adresa s ulicí + podobný název → telefon.
Opakovaný nález aktualizuje existující záznam a nepřepisuje ručně zadané údaje. Ruční sloučení duplicit v API.

**Visual Intelligence Engine** – Playwright screenshoty (celá stránka + „above the fold“), cookie lišta se
zavře, těžká média se neblokují. Měří se rychlost načtení, přetékání na mobilu, velikost písma, počet
písem, nefunkční / rozmazané obrázky, CTA v první obrazovce, barevná paleta ze screenshotu.
Multimodální model hodnotí 15 kritérií (estetika, modernost, typografie, barvy, hierarchie, layout,
hero, fotografie, branding, mobil, nabídka, důvěryhodnost, portfolio, CTA, vhodnost pro cílovku) –
každé se skóre, pozorováním, důkazem, doporučením a jistotou. **Website Visual Score 0–100** je
označen jako expertní odhad. **Bez vision modelu se hodnocení nevymýšlí** – audit je „neúplný“ a
použijí se jen technické metriky (s nižší jistotou).

**Design Gap Detector** – porovnává Business Quality Signals (AI dojem z fotek práce, kvalita fotografií,
portfolio, sociální sítě, reference/ocenění/média, rozsah nabídky, prémiové pozicování, délka působení)
s kvalitou webu. Bez dostatku dat o podnikání se skóre nepočítá.

**Buying Potential Engine** – odděleně **Commercial Potential** (obor, ceny na webu, právní forma,
základní kapitál, provozovny, tým, prémiovost, marketing, svatby/B2B, stabilita, zahraničí) a
**Buying Readiness** (nábor, nová pobočka, nové služby/produkty, rebranding, expanze, investice,
marketingové nástroje, nedávná aktivita, mladá firma, builder web). Odhad rozpočtu je vždy označen
jako orientační pásmo Project Two, ne zjištěný rozpočet.

**LinkedIn Prospecting Assistant** – rozhodovací osoby z obchodního rejstříku (jednatelé, společníci),
z ARES u OSVČ a z textu webu (označené jako neověřené). Přesné vyhledávací odkazy (lidé ve firmě,
rozhodovací role, firemní stránka, Google X-ray). Ruční uložení profilu, stav spojení, historie, další krok.

**AI Sales Message Generator** – 5 typů zpráv (žádost o spojení, první zpráva, follow-up, alternativa,
obchodní argument) × 5 strategií A–E (vizuální příležitost, obchodní přínos, personalizovaný návrh,
rebranding, konzultativní). Pouze ověřená fakta (zobrazí se, která byla použita). Kontrola kvality
(zakázaná AI klišé, „špatný web“, číselné sliby, délka) s automatickou opravou. Bez LLM skládá zprávy
deterministický kompozitor z faktů – je to v UI jasně označeno.

**Smart Follow-up System** – po oslovení se naplánuje follow-up (konfigurovatelné dny, max. počet),
po žádosti o spojení kontrola přijetí. Odpověď nebo odmítnutí zastaví všechny připomínky. Výslovné
odmítnutí → **Do Not Contact** (blokuje i stejnou osobu přes LinkedIn URL u jiné firmy).
**Nic se neodesílá automaticky.**

**Učení z výsledků** – výkon strategií A–E a segmentů s Bayesovským vyhlazením, návrhy úprav priorit
segmentů (aplikace jedním klikem), automatická volba strategie s průzkumem (epsilon-greedy).

---

## Scoring – jak se počítá

| Komponenta | Váha | Co měří |
|---|---|---|
| Design Gap | 30 % | `(100 − kvalita webu) × kvalita podnikání / 100 × 1,25` |
| Commercial Potential | 25 % | vážený průměr známých ekonomických faktorů |
| Buying Readiness | 20 % | `1 − Π(1 − síla signálu × stáří)` |
| Service Fit | 15 % | tier segmentu, význam vizuálu v oboru, multiplikátor priority, typ potřeby |
| Contactability | 10 % | rozhodovací osoba, LinkedIn, e-mail, telefon, formulář |

- **Neznámé ≠ 0.** Komponenta bez dat má hodnotu `None`; Opportunity Score se přepočítá jen ze známých
  komponent. Pokud známé pokrývají méně než 55 % vah (nastavitelné), skóre se nevypočítá a lead dostane
  kategorii „Nedostatek dat“.
- **Confidence Score** = vážený součet jistot komponent (kvalita důkazů – vizuální vs. technická analýza,
  ověření v registru, počet stažených stránek).
- Kategorie: **80–100 Priority Lead**, **60–79 Strong Opportunity**, **40–59 Potential Lead**, **0–39 Low Priority**.
- Důvody vyřazení: nedostatečná obchodní aktivita, velmi nízký ekonomický potenciál, již kvalitní web,
  nedostatek ověřitelných dat, nevhodný segment, duplicita, firma již byla oslovena, firma odmítla kontaktování.
- Každá komponenta má v UI rozbalitelné důvody a jednotlivé faktory s důkazy.

Váhy, prahy, ceny a priority segmentů se mění v **Nastavení** – po uložení se všechna skóre přepočítají.

---

## AI: Ollama a externí API

`TEXT_PROVIDER` / `VISION_PROVIDER` = `auto` (Ollama → Anthropic → OpenAI-kompatibilní), nebo konkrétní
poskytovatel, nebo `none`.

| RAM / HW | Vision | Text |
|---|---|---|
| 24 GB+ nebo GPU / Apple Silicon | `qwen2.5vl:7b` | `qwen2.5:7b-instruct` |
| 12–16 GB | `qwen2.5vl:3b`, `llava:7b` | `qwen2.5:3b-instruct` |
| méně | externí API (`ANTHROPIC_API_KEY` nebo `OPENAI_API_KEY`) | kompozitor / API |

Aplikace sama najde nainstalovaný vision model (qwen2.5vl, llama3.2-vision, llava, minicpm-v, gemma3 …).
Doporučení pro váš hardware ukazuje **Nastavení → AI & systém**. OpenAI-kompatibilní rozhraní funguje
i s LM Studio, vLLM nebo OpenRouter (`OPENAI_BASE_URL`).

---

## Zdroje dat a legálnost

| Zdroj | Typ | Poznámka |
|---|---|---|
| OpenStreetMap / Overpass API | mapová data | ODbL, fair-use (≈4 dotazy/min), střídání zrcadel |
| ARES (MF ČR) | oficiální registr | IČO, právní forma, vznik, NACE, stav, jednatelé, kapitál |
| Brave Search API | vyhledávací API | zdarma ~2 000 dotazů/měsíc, klíč `BRAVE_API_KEY` |
| Google Programmable Search | vyhledávací API | zdarma 100 dotazů/den, `GOOGLE_CSE_KEY` + `GOOGLE_CSE_CX` |
| Veřejné firemní weby | crawler | robots.txt, max 5 podstránek, 2 s mezi požadavky na doménu, timeouty |
| Ruční zadání / CSV | uživatel | `name, website, city, ico, email, phone, segment_key` |

- **LinkedIn se neautomatizuje**: žádné přihlašování, procházení profilů, pozvánky ani zprávy. Aplikace jen
  generuje odkazy a texty, odesílá člověk.
- Žádné obcházení CAPTCHA, rotace účtů ani simulace chování.
- Z obchodního rejstříku se ukládá jen jméno a funkce (bez data narození a adresy – minimalizace dat).
- Katalogy a sociální sítě se nescrapují; odkazy na sítě se jen evidují (aktivita se neověřuje).

---

## Automatizace

Backend obsahuje **perzistentní frontu úloh v DB** (přežije restart), worker vlákna a **plánovač**.
Automatizace běží i bez otevřeného prohlížeče.

Denní běh (výchozí 6:30, Europe/Prague):

1. naplánuje vyhledávání pro nejlépe prioritizované kombinace segment × kraj (s rotací),
2. po dokončení vybere až **30** webů k analýze (priorita: tier, multiplikátor, region, nové firmy),
3. pro nejlepší kvalifikované leady připraví až **10** sad zpráv,
4. zkontroluje follow-upy a vytvoří **denní přehled** (dashboard).

Cíl objevit až **100** firem denně je maximum, ne garance. Vše je konfigurovatelné.
Fronta: retry s exponenciálním čekáním, deduplikace úloh, odkládání závislých kroků, obnova po pádu,
pozastavení (při pauze běží jen ručně spuštěné úlohy), ruční spuštění, přehled a log každé úlohy.

CLI (vše bez frontendu):

```bash
cd backend && source .venv/bin/activate
python -m app.cli worker                     # samostatný worker + plánovač
python -m app.cli run-daily                  # denní pipeline hned
python -m app.cli discover --segment custom_kitchens --region CZ-64 --limit 30 --analyze
python -m app.cli analyze 12
python -m app.cli import firmy.csv --segment premium_florist
python -m app.cli sources                    # dostupnost zdrojů
```

---

## Outreach workspace a klávesové zkratky

Sekce **Oslovování**: fronta kvalifikovaných neoslovených leadů seřazená podle skóre. U každého leadu
screenshot (desktop/mobil), hlavní problémy, Opportunity Score, důvod oslovení, LinkedIn kontakt
(nebo rychlé uložení profilu), personalizovaná zpráva a akce.

| Klávesa | Akce |
|---|---|
| `C` | Copy Message |
| `L` | Open LinkedIn (profil, jinak vyhledávání rozhodovacích rolí) |
| `M` | Mark as Contacted (+ naplánuje follow-up, přejde na další lead) |
| `R` | Žádost o spojení odeslána (+ kontrola přijetí za 5 dní) |
| `F` | Schedule Follow-up |
| `N` | Not Interested (volitelně Do Not Contact) |
| `G` | Vygenerovat / přegenerovat zprávy |
| `1`–`5` | Typ zprávy |
| `J` / `→`, `K` / `←` | Další / předchozí lead |

Typický postup s připravenou zprávou a ověřeným kontaktem: `C` → `L` → vložit a odeslat na LinkedInu → `M`.

---

## Bezpečnost

- API je ve výchozím stavu jen na `127.0.0.1`. Pro provoz mimo localhost nastavte `API_TOKEN` v
  `backend/.env` a stejný `LEADHUNTER_API_TOKEN` ve `frontend/.env.local` – token přidává serverový proxy.
- Crawler blokuje privátní a lokální adresy (ochrana proti SSRF) i po přesměrování a omezuje velikost stahování.
- Screenshoty se servírují jen z vlastního adresáře (ochrana proti path traversal).
- Do Not Contact se kontroluje před každým oslovením, generováním zpráv i plánováním follow-upu.
- API klíče jen v `.env` (není v gitu).

---

## Konfigurace

Všechny volby backendu jsou v [`backend/.env.example`](backend/.env.example). Nejdůležitější:

| Proměnná | Význam |
|---|---|
| `DATABASE_URL` | výchozí SQLite v `backend/data/` |
| `API_TOKEN` | zapne autorizaci API |
| `WORKER_CONCURRENCY` | počet paralelních úloh (výchozí 2) |
| `PER_DOMAIN_DELAY_SECONDS`, `MAX_PAGES_PER_SITE` | ohleduplnost k cizím webům |
| `PLAYWRIGHT_EXECUTABLE_PATH` | vlastní Chromium (jinak automatická detekce) |
| `BRAVE_API_KEY`, `GOOGLE_CSE_KEY`, `GOOGLE_CSE_CX` | vyhledávací API |
| `OLLAMA_URL`, `OLLAMA_VISION_MODEL`, `OLLAMA_TEXT_MODEL` | lokální AI |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL` | externí AI |

Obchodní nastavení (cíle, váhy, ceny, segmenty, regiony, podpis, fakta o agentuře a reference) se mění
v aplikaci v sekci **Nastavení** a ukládá se do databáze.

---

## Vývoj a testy

```bash
./scripts/dev.sh                                  # backend s reloadem + next dev
cd backend && .venv/bin/python -m pytest -q       # testy backendu
cd frontend && npm run lint && npm run build      # typová kontrola a build
```

Testy pokrývají normalizaci a deduplikaci, extrakci z HTML a technický audit, scoring (včetně
„neznámé ≠ 0“), vision a LLM cesty s mockovaným modelem, frontu úloh (retry, odložení, deduplikace),
outreach pravidla (zastavení follow-upů, DNC, limity), konektory a API.

---

## Známá omezení

- Veřejné instance Overpass mají limity a občas výpadky – konektor střídá zrcadla; pro větší objemy
  zvažte vlastní instanci nebo vyhledávací API.
- ARES neobsahuje weby firem; firmy nalezené jen v ARES se musí doplnit webem (ručně nebo přes
  vyhledávací API), jinak zůstávají s kategorií „Nedostatek dat“.
- Kvalita vizuální analýzy závisí na modelu – malé lokální modely jsou méně přesné, proto se ukládá
  jistota a výsledek je vždy označen jako expertní odhad.
- Aktivita na sociálních sítích se neověřuje (žádný scraping) – evidují se jen odkazy.
