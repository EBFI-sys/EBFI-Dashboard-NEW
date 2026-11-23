"""Which Word template each client is invoiced with, and that client's invoicing rules.

From the invoicing instructions EBFI used for FY 2026-27 (app/invoice_templates/INSTRUCTIONS.md): one template per
client, the same EBFI header and bank block, client-specific description lines, taxes and grouping."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    code: str
    title: str
    file: str
    annexure: str | None = None
    style: str = "std"            # std «4,920» · eu «8 151» / «0,17» (marine surveys)
    date: str = "month_end"       # month_end: last day of the work month · issue: the day the invoice is made
    per_job: bool = False         # one invoice per EBFI job number
    per_coordinator: bool = False  # separate invoices per client coordinator (BV Singapore)
    limit_inr: int | None = None  # TUV Rheinland India: no invoice above ₹20,00,000 with GST
    inr_lines: bool = False       # MAS Marine: day rates converted to INR, the whole invoice in INR
    full_job_ref: bool = False    # Ref.code.no is the full job number (marine), not the series
    notes: tuple[str, ...] = field(default_factory=tuple)


RULES: dict[str, Rule] = {r.code: r for r in [
    Rule("01", "TUV Rheinland India", "TPL_01_TUV_Rheinland_India_USD.docx", "TPL_01_TUV_Rheinland_India_USD_Annexure.xlsx",
         limit_inr=2_000_000, notes=("Отдельные инвойсы по валюте", "Не более ₹20 лакх с GST в одном инвойсе", "К инвойсу — Annexure")),
    Rule("02", "TUV Rheinland LT", "TPL_02_TUV_Rheinland_LT_EUR.docx", "TPL_02_TUV_Rheinland_LT_EUR_Annexure.xlsx",
         limit_inr=2_000_000, notes=("Отдельные инвойсы по валюте", "К инвойсу — Annexure")),
    Rule("03", "TUV NORD (TUV India)", "TPL_03_TUV_NORD.docx", per_job=True, notes=("Один инвойс на номер работы",)),
    Rule("04", "LRQA India", "TPL_04_LRQA_India.docx", per_job=True, notes=("Один инвойс на работу",)),
    Rule("05", "LRQA Singapore", "TPL_05_LRQA_Singapore.docx", per_job=True, notes=("Один инвойс на работу и валюту",)),
    Rule("06", "BV Singapore", "TPL_06_BV_Singapore.docx", per_coordinator=True,
         notes=("Отдельно по валюте и по координатору", "Markus Ehrmann — всегда отдельный инвойс", "RLPP не показывать")),
    Rule("07", "BV Indonesia", "TPL_07_BV_Indonesia.docx", notes=("Отдельно по валюте",)),
    Rule("08", "BV USA", "TPL_08_BV_USA.docx"),
    Rule("09", "TUV Rheinland Qatar", "TPL_09_TUV_Rheinland_Qatar.docx", per_job=True,
         notes=("Один инвойс на работу", "Удержание 5% в итоге")),
    Rule("10", "SPEX Quality Service (Germany)", "TPL_10_SPEX_Germany.docx", notes=("Все работы месяца — один инвойс",)),
    Rule("11", "SPEX Consultancy HK (морские сюрвеи)", "TPL_11_SPEX_HK_Marine.docx", style="eu", date="issue", per_job=True,
         full_job_ref=True, notes=("Каждое судно — отдельный инвойс", "Дата — день выставления", "Лаборатория и draft survey — доп. строками")),
    Rule("12", "TÜV Austria Singapore (морские сюрвеи)", "TPL_12_TUV_Austria_Marine.docx", style="eu", date="issue", per_job=True,
         full_job_ref=True, notes=("Каждое судно — отдельный инвойс", "Проверьте плательщика: SPEX HK или TUV Austria")),
    Rule("13", "Qualcon", "TPL_13_Qualcon.docx", notes=("Ставка за час: Man-Hour",)),
    Rule("14", "DITH / Duferco Asia", "TPL_14_DITH_Duferco.docx", style="eu", date="issue", notes=("Дата — день выставления",)),
    Rule("15", "APPLUS Indonesia", "TPL_15_APPLUS_Indonesia.docx"),
    Rule("16", "EBFI Italy (Franke)", "TPL_16_EBFI_Italy.docx"),
    Rule("17", "ISSPL (Delhi)", "TPL_17_ISSPL.docx", notes=("IGST 18% одной строкой",)),
    Rule("18", "MAS Marine", "TPL_18_MAS_Marine.docx", inr_lines=True, notes=("Ставка пересчитывается в INR за день",)),
    Rule("19", "DNV (GL Italia)", "TPL_19_DNV.docx"),
]}
CREDIT_NOTE = "TPL_20_Credit_Note.docx"

# client names in the directory → template, used until the admin picks one in «Справочники → Клиент»
BY_NAME = [
    (r"rheinland\s*lt", "02"), (r"rheinland\s*qatar", "09"), (r"rheinland(\s*india)?$", "01"),
    (r"^tuv\s*nord|tuv\s*india", "03"), (r"^lrqa\s*singapore", "05"), (r"^lrqa(\s*india)?$", "04"),
    (r"^bv\s*indonesia", "07"), (r"^bv\s*(usa|praveen)", "08"), (r"^bv(\s*singapore)?$", "06"),
    (r"^ispex|spex\s*quality|spex\s*germany", "10"), (r"^spex(\s*hk|\s*consultancy)?$", "11"), (r"^tuv\s*(at|austria)", "12"),
    (r"^qualcon", "13"), (r"^dith|duferco", "14"), (r"^applus", "15"), (r"^ebfi\s*italy|franke", "16"),
    (r"^isspl|^irclass", "17"), (r"^mas\s*marine", "18"), (r"^dnv", "19"),
]


def guess(client_name: str | None) -> str | None:
    n = (client_name or "").strip().lower()
    for pat, code in BY_NAME:
        if re.search(pat, n):
            return code
    return None


def rule_for(client) -> Rule | None:
    code = getattr(client, "invoice_template", None)
    if code is None:  # not set yet (before the start-up fill): by name; "" means «no template» on purpose
        code = guess(getattr(client, "name", None))
    return RULES.get(code) if code else None
