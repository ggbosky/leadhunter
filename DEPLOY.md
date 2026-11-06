# Nasazení – aplikace na vlastní webové adrese (zdarma)

Po nastavení poběží Lead Hunter na adrese typu **`https://vas-ucet-leadhunter.hf.space`**.
Otevřete ji odkudkoliv v prohlížeči (i z mobilu), nic se neinstaluje. Každý push do GitHubu aplikaci
automaticky aktualizuje.

Jak to funguje: **GitHub** (kód) → GitHub Action → **Hugging Face Spaces** (zdarma běží aplikace)
+ **Neon** (zdarma online databáze, aby se data neztrácela).

Celé nastavení zabere asi 15 minut a dělá se jen jednou.

---

## 1. Databáze – Neon (zdarma)

1. Otevřete https://neon.tech a klikněte **Sign up** (nejrychleji „Continue with GitHub“).
2. Vytvořte projekt: název `leadhunter`, region **Europe (Frankfurt)**, Postgres verze nechte výchozí.
3. Na stránce projektu klikněte **Connect** a zkopírujte **Connection string**
   (začíná `postgresql://…` a končí `…?sslmode=require`). Uložte si ho na chvíli stranou.

## 2. Hosting – Hugging Face (zdarma)

1. Otevřete https://huggingface.co/join a založte účet (potvrďte e-mail).
2. Vpravo nahoře ikona účtu → **Settings** → **Access Tokens** → **Create new token**.
3. Typ tokenu zvolte **Write**, název třeba `leadhunter-deploy`, a klikněte **Create token**.
4. Token zkopírujte (začíná `hf_…`). Zobrazí se jen jednou.

## 3. Klíče do GitHubu

V repozitáři na GitHubu: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
Přidejte tyto položky (Name = přesně takto, Secret = hodnota):

| Name | Hodnota | Povinné |
|---|---|---|
| `HF_TOKEN` | token z Hugging Face (`hf_…`) | ano |
| `APP_PASSWORD` | heslo, kterým se budete do aplikace přihlašovat (vymyslete si silné) | ano |
| `DATABASE_URL` | connection string z Neonu | doporučeno |
| `ANTHROPIC_API_KEY` nebo `OPENAI_API_KEY` | klíč pro AI hodnocení vzhledu webů a psaní zpráv | volitelné |
| `BRAVE_API_KEY` | klíč Brave Search API pro hledání dalších firem | volitelné |
| `HF_PRIVATE` | `true`, pokud nechcete, aby byl kód aplikace na Hugging Face veřejně vidět* | volitelné |

\* U soukromého Space se aplikace otevírá jen přihlášenému uživateli Hugging Face. Spolehlivější je
veřejný Space – data i tak chrání heslo `APP_PASSWORD` a klíče nejsou v kódu, jen v šifrovaných secrets.

## 4. Spuštění nasazení

1. Na GitHubu otevřete záložku **Actions** → workflow **Nasazení na Hugging Face**.
2. Otevřete poslední běh a klikněte **Re-run all jobs** (nebo **Run workflow**, pokud je tlačítko vidět).
3. Po dokončení (zelená fajfka) je v souhrnu běhu adresa aplikace.
4. Hugging Face pak aplikaci poprvé sestavuje **cca 5–10 minut**. Průběh je vidět na
   `https://huggingface.co/spaces/<váš-účet>/leadhunter` (záložka „Logs“).

## 5. Otevření

Otevřete **`https://<váš-účet>-leadhunter.hf.space`**, zadejte heslo a můžete pracovat.
Adresu si uložte do záložek nebo na plochu telefonu.

---

## Dobré vědět

- **Uspání:** bezplatný Space se po 48 hodinách bez návštěvy uspí. Při dalším otevření se za
  1–2 minuty probudí a pokud zmeškal denní automatický běh, dožene ho.
- **Screenshoty** se ukládají na disk Space – po restartu se ztratí a znovu vzniknou při další analýze.
  Leady, kontakty, zprávy, skóre i historie jsou v databázi Neon a zůstávají.
- **AI:** lokální Ollama na hostingu neběží. Bez API klíče aplikace funguje, jen vizuální hodnocení
  označí jako neúplné a zprávy skládá z ověřených faktů bez AI.
- **Aktualizace:** každý push do větve (nebo `main`) spustí testy a nové nasazení automaticky.
- **Vlastní doména / stálý provoz bez uspání:** stejný Docker image (`Dockerfile` v kořeni) poběží
  na libovolném VPS: `docker build -t leadhunter . && docker run -d -p 80:7860 -e APP_PASSWORD=… -e DATABASE_URL=… leadhunter`.
