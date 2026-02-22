# 📋 Stap-voor-stap handleiding — KVP × Funda Scanner op GitHub

Geen technische kennis vereist. Je hebt alleen een **webbrowser** nodig.
Totale tijd: ±15 minuten.

---

## Stap 1 — Maak een gratis GitHub account aan

1. Ga naar **github.com** in je browser
2. Klik op **"Sign up"** (rechtsboven)
3. Vul in:
   - Je e-mailadres (gebruik je privé-mail, niet werk)
   - Een zelfgekozen wachtwoord
   - Een gebruikersnaam (bv. `jouw-naam-scan`)
4. Voltooi de verificatie en bevestig je e-mail

> 💡 GitHub is gratis voor dit gebruik en is eigendom van Microsoft —  
> hetzelfde bedrijf als achter Teams en Office 365.

---

## Stap 2 — Maak een nieuwe repository aan

Een "repository" is gewoon een map in de cloud waar je bestanden in bewaart.

1. Klik na inloggen op de groene knop **"New"** (of ga naar github.com/new)
2. Vul in:
   - **Repository name:** `kvp-funda-scanner`
   - **Description:** `Automatische scan KVP-lijst × Funda`
   - Kies **Private** (dan zijn je bestanden alleen voor jou zichtbaar)
3. Vink aan: **"Add a README file"**
4. Klik op de groene knop **"Create repository"**

---

## Stap 3 — Upload de bestanden

Je hebt 4 bestanden nodig (die je eerder hebt gedownload via Claude):
- `kvp_scanner.py`
- `requirements.txt`
- `dashboard.html`
- `.github/workflows/kvp_scan.yml` ← dit is het automatische schema

### 3a. Upload de gewone bestanden

1. Klik in je repository op **"uploading an existing file"** of de knop **"Add file" → "Upload files"**
2. Sleep de bestanden `kvp_scanner.py`, `requirements.txt` en `dashboard.html` naar het uploadvenster
3. Scroll naar beneden en klik op **"Commit changes"** (groene knop)

### 3b. Maak de workflow-map aan

GitHub Actions vereist dat het bestand in een specifieke map staat. Dat doe je zo:

1. Klik op **"Add file" → "Create new file"**
2. In het naamveld bovenaan typ je precies dit (inclusief de schuine strepen):
   ```
   .github/workflows/kvp_scan.yml
   ```
   → GitHub maakt automatisch de mappen aan
3. Kopieer de volledige inhoud van het bestand `.github/workflows/kvp_scan.yml`  
   en plak het in het grote tekstvak
4. Klik op **"Commit changes"** → nog een keer **"Commit changes"**

---

## Stap 4 — Zet GitHub Actions aan

1. Klik in je repository op het tabblad **"Actions"** (bovenaan)
2. Als er een melding staat "Workflows aren't being run on this repository" → klik op **"I understand my workflows, enable them"**
3. Je ziet nu jouw workflow **"KVP × Funda Dagelijkse Scan"** in de lijst

### Test of het werkt

1. Klik op de workflow **"KVP × Funda Dagelijkse Scan"**
2. Klik rechts op de knop **"Run workflow" → "Run workflow"** (groene knop)
3. Ververs de pagina na 10 seconden
4. Je ziet een gele cirkel (bezig) → na ±25 minuten een groen vinkje ✅

---

## Stap 5 — Resultaten bekijken

Na een succesvolle scan:

1. Klik op de laatste scan-run (de rij met het groene vinkje)
2. **Samenvatting:** Scroll naar beneden → je ziet direct een tabel met matches
3. **Excel downloaden:**
   - Scroll naar beneden naar **"Artifacts"**
   - Klik op **"kvp-funda-resultaten-1"** → downloadt een zip-bestand
   - Pak de zip uit → open `kvp_funda_matches.xlsx` in Excel

---

## Automatisch — geen actie nodig!

Vanaf nu draait de scan **elke ochtend om ±07:00** automatisch.  
Je ontvangt een **e-mail van GitHub** als er iets misgaat (standaard ingesteld).

### E-mail instellen voor succesvolle scans

GitHub stuurt standaard alleen een mail bij fouten. Wil je ook een mail bij matches?

1. Ga naar **github.com** → je profielfoto (rechtsboven) → **"Settings"**
2. Ga naar **"Notifications"** in het linkermenu
3. Onder "Actions" → zet "Email" aan voor "Successful workflows"

---

## Overzicht — wat doet GitHub precies?

```
Elke dag om 07:00
    ↓
GitHub start een virtuele computer in de cloud
    ↓
Downloadt de KVP-PDF van gemeente Tilburg
    ↓
Checkt Funda voor alle ~600 unieke straten
    ↓
Vergelijkt huisnummers → vindt matches
    ↓
Slaat Excel + JSON op als downloadbaar bestand
    ↓
Toont samenvatting in GitHub
    ↓
Virtuele computer wordt uitgeschakeld
```

Jouw laptop staat hier **volledig buiten**. Geen installaties, geen risico's.

---

## Vragen?

- **De scan duurt te lang (>30 min)?** Normaal — er zijn ~600 straten om te checken
- **Rode X bij de scan?** Klik erop → scroll naar de foutmelding → stuur een screenshot naar Claude
- **Wil je de scan vaker?** Verander in het workflow-bestand `'0 5 * * *'` naar bv. `'0 5 * * 1'` (alleen maandag)
