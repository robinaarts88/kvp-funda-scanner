"""
KVP-Funda Scanner
=================
Vergelijkt automatisch de kamerverhuurvergunninglijst van gemeente Tilburg
met het actuele koopwoningaanbod op Funda.
"""

import re
import time
import json
import os
import smtplib
import unicodedata
import logging
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import requests
import pdfplumber
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# ─── Configuratie ─────────────────────────────────────────────────────────────

KVP_PDF_URL = "https://www.tilburg.nl/fileadmin/files/inwoners/vergunningen/lijst_kvp_internet_251212.pdf"
FUNDA_BASE_URL = "https://www.funda.nl/koop/tilburg/straat-{slug}/"
OUTPUT_DIR = Path("output")
RESULTS_JSON = OUTPUT_DIR / "resultaten.json"
RESULTS_EXCEL = OUTPUT_DIR / "kvp_funda_matches.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_DELAY = 2.0

# ─── Logging ──────────────────────────────────────────────────────────────────

OUTPUT_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(OUTPUT_DIR / "scanner.log"),
    ],
)
log = logging.getLogger(__name__)


# ─── Stap 1: PDF inlezen ──────────────────────────────────────────────────────

def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug


def parse_address_line(line: str):
    line = line.strip()
    match = re.match(
        r"^(.+?)\s+(\d+\s*[A-Za-z0-9\s\-]*?)\s+(\d{4}\s*[A-Z]{2})\s*$",
        line,
        re.IGNORECASE,
    )
    if not match:
        return None
    straat = match.group(1).strip()
    nummer = match.group(2).strip()
    postcode = match.group(3).replace(" ", "").upper()
    if straat.lower() in {"straatnaam", "kamerverhuur-", "huisnummer"}:
        return None
    return straat, nummer, postcode


def download_and_parse_kvp_pdf(url: str) -> list:
    log.info("PDF downloaden van %s", url)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    pdf_path = OUTPUT_DIR / "kvp_lijst.pdf"
    pdf_path.write_bytes(resp.content)

    addresses = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                result = parse_address_line(line)
                if result:
                    straat, nummer, postcode = result
                    addresses.append({
                        "straatnaam": straat,
                        "huisnummer": nummer,
                        "postcode": postcode,
                        "volledig_adres": f"{straat} {nummer}, {postcode} Tilburg",
                    })

    log.info("✓ %d adressen ingelezen uit de KVP-lijst", len(addresses))
    return addresses


# ─── Stap 2: Funda checken ────────────────────────────────────────────────────

def get_funda_listings_for_street(street_name: str) -> list:
    slug = slugify(street_name)
    url = FUNDA_BASE_URL.format(slug=slug)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Fout bij ophalen %s: %s", url, e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    listings = []

    for card in soup.find_all("a", href=re.compile(r"/detail/koop/tilburg/")):
        href = card.get("href", "")
        if not href:
            continue

        full_url = f"https://www.funda.nl{href}" if href.startswith("/") else href
        addr_match = re.search(r"/(?:huis|appartement)-(.+?)/(\d+[a-z0-9\-]*)/", href)
        if not addr_match:
            continue

        huisnummer_raw = addr_match.group(2)
        prijs_el = card.find_parent("li") or card.find_parent("div", class_=re.compile(r"listing|result|property", re.I))
        prijs_text = ""
        status = "Te koop"

        if prijs_el:
            prijs_match = re.search(r"€[\s\d\.,]+", prijs_el.get_text())
            if prijs_match:
                prijs_text = prijs_match.group(0).strip()
            if "onder voorbehoud" in prijs_el.get_text().lower():
                status = "Onder voorbehoud"
            if "verkocht" in prijs_el.get_text().lower() and "onder voorbehoud" not in prijs_el.get_text().lower():
                status = "Verkocht"

        listings.append({
            "funda_url": full_url,
            "straatnaam_funda": street_name,
            "huisnummer_funda": huisnummer_raw,
            "prijs": prijs_text,
            "status": status,
        })

    seen = set()
    unique = []
    for l in listings:
        if l["funda_url"] not in seen:
            seen.add(l["funda_url"])
            unique.append(l)

    return unique


def normalize_number(num: str) -> str:
    return re.sub(r"\s+", "", num).lower()


def numbers_match(kvp_num: str, funda_num: str) -> bool:
    k = normalize_number(kvp_num)
    f = normalize_number(funda_num)
    if k == f:
        return True
    if f.startswith(k) and not f[len(k):len(k)+1].isdigit():
        return True
    if k.startswith(f) and not k[len(f):len(f)+1].isdigit():
        return True
    return False


# ─── Stap 3: Vergelijken ──────────────────────────────────────────────────────

def find_matches(kvp_addresses: list):
    kvp_by_street = {}
    for addr in kvp_addresses:
        straat = addr["straatnaam"]
        kvp_by_street.setdefault(straat, []).append(addr)

    all_streets = sorted(kvp_by_street.keys())
    log.info("Funda checken voor %d unieke straten...", len(all_streets))

    matches = []
    scan_log = []

    for i, straat in enumerate(all_streets, 1):
        if i % 50 == 0:
            log.info("  Voortgang: %d/%d straten gescand", i, len(all_streets))

        funda_listings = get_funda_listings_for_street(straat)

        for listing in funda_listings:
            for kvp_addr in kvp_by_street[straat]:
                if numbers_match(kvp_addr["huisnummer"], listing["huisnummer_funda"]):
                    match = {
                        **kvp_addr,
                        **listing,
                        "gevonden_op": datetime.now().isoformat(),
                        "match_type": "exact" if normalize_number(kvp_addr["huisnummer"]) == normalize_number(listing["huisnummer_funda"]) else "gedeeltelijk",
                    }
                    matches.append(match)
                    log.info(
                        "  ✅ MATCH: %s %s — %s (%s)",
                        straat, kvp_addr["huisnummer"],
                        listing.get("prijs", "prijs onbekend"),
                        listing["status"],
                    )

        scan_log.append({
            "straat": straat,
            "funda_resultaten": len(funda_listings),
            "matches": sum(1 for m in matches if m["straatnaam"] == straat),
        })

        time.sleep(REQUEST_DELAY)

    log.info("Scan voltooid: %d matches gevonden", len(matches))
    return matches, scan_log


# ─── Stap 4: Excel exporteren ─────────────────────────────────────────────────

def export_excel(matches: list, scan_log: list) -> Path:
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Matches"

    headers = ["Straatnaam", "Huisnummer", "Postcode", "Volledig adres", "Status", "Vraagprijs", "Funda URL", "Match type", "Gevonden op"]
    ws1.append(headers)

    header_fill = PatternFill("solid", start_color="1A1A2E", end_color="1A1A2E")
    for col in range(1, len(headers) + 1):
        cell = ws1.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.alignment = Alignment(horizontal="center")

    status_colors = {"Te koop": "D5F5E3", "Onder voorbehoud": "FDEBD0", "Verkocht": "FADBD8"}

    for i, m in enumerate(matches, 2):
        ws1.append([
            m.get("straatnaam", ""),
            m.get("huisnummer", ""),
            m.get("postcode", ""),
            m.get("volledig_adres", ""),
            m.get("status", ""),
            m.get("prijs", ""),
            m.get("funda_url", ""),
            m.get("match_type", ""),
            m.get("gevonden_op", "")[:10] if m.get("gevonden_op") else "",
        ])
        color = status_colors.get(m.get("status", ""), "FFFFFF")
        fill = PatternFill("solid", start_color=color, end_color=color)
        for col in range(1, len(headers) + 1):
            ws1.cell(row=i, column=col).fill = fill
            ws1.cell(row=i, column=col).font = Font(name="Arial", size=10)

        url_cell = ws1.cell(row=i, column=7)
        if url_cell.value:
            url_cell.hyperlink = url_cell.value
            url_cell.font = Font(name="Arial", size=10, color="0563C1", underline="single")
            url_cell.value = "Bekijk op Funda →"

    col_widths = [25, 15, 12, 40, 18, 16, 22, 15, 14]
    for col, width in enumerate(col_widths, 1):
        ws1.column_dimensions[get_column_letter(col)].width = width

    wb.save(RESULTS_EXCEL)
    log.info("Excel opgeslagen: %s", RESULTS_EXCEL)
    return RESULTS_EXCEL


# ─── Stap 5: JSON opslaan ─────────────────────────────────────────────────────

def save_json(matches: list, scan_log: list, kvp_count: int):
    payload = {
        "scan_datum": datetime.now().isoformat(),
        "kvp_adressen_totaal": kvp_count,
        "straten_gescand": len(scan_log),
        "matches": matches,
        "scan_log": scan_log,
    }
    RESULTS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    log.info("JSON opgeslagen: %s", RESULTS_JSON)


# ─── Stap 6: E-mail via Outlook ───────────────────────────────────────────────

def send_email(matches: list):
    """
    Stuurt een e-mail via Outlook/Hotmail met de scan-resultaten.
    Leest inloggegevens uit GitHub Secrets (omgevingsvariabelen).
    """
    sender = os.environ.get("EMAIL_SENDER", "")
    password = os.environ.get("EMAIL_PASSWORD", "")
    recipient = os.environ.get("EMAIL_RECIPIENT", "")

    if not all([sender, password, recipient]):
        log.info("Geen e-mailconfiguratie gevonden — e-mail overgeslagen")
        return

    datum = datetime.now().strftime("%d-%m-%Y")
    aantal = len(matches)
    tekoop = sum(1 for m in matches if m.get("status") == "Te koop")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🏠 KVP×Funda: {aantal} match(es) gevonden — {datum}"
    msg["From"] = sender
    msg["To"] = recipient

    # Plain text
    plain = [f"KVP×Funda Scan — {datum}", "=" * 40, ""]
    if matches:
        for m in matches:
            plain.append(f"• {m.get('volledig_adres', '')} — {m.get('prijs', '')} ({m.get('status', '')})")
            plain.append(f"  {m.get('funda_url', '')}")
            plain.append("")
    else:
        plain.append("Geen matches gevonden vandaag.")
    msg.attach(MIMEText("\n".join(plain), "plain"))

    # HTML
    if matches:
        rows_html = ""
        for m in matches:
            color = {"Te koop": "#d5f5e3", "Onder voorbehoud": "#fdebd0", "Verkocht": "#fadbd8"}.get(m.get("status", ""), "#fff")
            rows_html += f"""
            <tr style="background:{color}">
              <td style="padding:10px;border:1px solid #ddd">{m.get('volledig_adres','')}</td>
              <td style="padding:10px;border:1px solid #ddd"><strong>{m.get('prijs','—')}</strong></td>
              <td style="padding:10px;border:1px solid #ddd">{m.get('status','')}</td>
              <td style="padding:10px;border:1px solid #ddd"><a href="{m.get('funda_url','')}">Bekijken →</a></td>
            </tr>"""
        tabel = f"""
        <table style="border-collapse:collapse;width:100%;margin-top:16px">
          <tr style="background:#1A1A2E;color:#fff">
            <th style="padding:10px;text-align:left">Adres</th>
            <th style="padding:10px;text-align:left">Prijs</th>
            <th style="padding:10px;text-align:left">Status</th>
            <th style="padding:10px;text-align:left">Link</th>
          </tr>
          {rows_html}
        </table>"""
    else:
        tabel = "<p style='color:#666'>Geen matches gevonden vandaag.</p>"

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto">
      <div style="background:#E87722;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">🏠 KVP × Funda Scanner</h2>
        <p style="color:rgba(255,255,255,0.85);margin:6px 0 0">{datum}</p>
      </div>
      <div style="background:#f9f9f9;padding:20px;border:1px solid #eee">
        <p>Scan voltooid. <strong>{aantal} match(es)</strong> gevonden, waarvan <strong>{tekoop} te koop</strong>.</p>
        {tabel}
        <p style="margin-top:20px;font-size:12px;color:#999">
          Het Excel-bestand is te downloaden via GitHub Actions → Artifacts.<br>
          Automatisch verzonden door KVP×Funda Scanner via vastgoed-automatisering@hotmail.com
        </p>
      </div>
    </body></html>"""
    msg.attach(MIMEText(html, "html"))

    # Excel als bijlage
    if RESULTS_EXCEL.exists():
        with open(RESULTS_EXCEL, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="kvp_funda_matches_{datum}.xlsx"')
            msg.attach(part)

    # Outlook/Hotmail gebruikt smtp-mail.outlook.com op poort 587
    try:
        with smtplib.SMTP("smtp-mail.outlook.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        log.info("✉️  E-mail verzonden naar %s", recipient)
    except Exception as e:
        log.error("E-mail versturen mislukt: %s", e)


# ─── Hoofdfunctie ─────────────────────────────────────────────────────────────

def run_scan():
    OUTPUT_DIR.mkdir(exist_ok=True)
    log.info("=" * 60)
    log.info("KVP × Funda Scanner gestart — %s", datetime.now().strftime("%d-%m-%Y %H:%M"))
    log.info("=" * 60)

    kvp_addresses = download_and_parse_kvp_pdf(KVP_PDF_URL)
    matches, scan_log = find_matches(kvp_addresses)
    save_json(matches, scan_log, len(kvp_addresses))
    export_excel(matches, scan_log)
    send_email(matches)

    log.info("=" * 60)
    log.info("Klaar! Resultaten in: output/")
    log.info("=" * 60)

    return matches


if __name__ == "__main__":
    run_scan()
