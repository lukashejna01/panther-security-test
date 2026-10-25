"""
Služba pro automatické vytěžování dat z přijatých dodavatelských faktur pomocí Claude API.
Používá přímé volání přes urllib pro maximální stabilitu na PythonAnywhere.
"""

import base64
import json
import os
import urllib.request
from django.conf import settings


def _get_api_key():
    key = getattr(settings, 'ANTHROPIC_API_KEY', None) or os.getenv('ANTHROPIC_API_KEY')
    if not key and os.path.exists('.env'):
        for line in open('.env'):
            if line.startswith('ANTHROPIC_API_KEY='):
                key = line.strip().split('=', 1)[1].strip('\"\' ')
                break
    return key


def extract_data_from_invoice(file_obj) -> dict:
    """
    Vytěží strukturovaná data z faktury (PDF, PNG, JPG) pomocí Claude API.
    Vrací slovník připravený pro předvyplnění formuláře Invoice.
    """
    file_obj.seek(0)
    file_bytes = file_obj.read()
    file_obj.seek(0)
    base64_encoded = base64.b64encode(file_bytes).decode('utf-8')

    name_lower = getattr(file_obj, 'name', '').lower()
    is_pdf = name_lower.endswith('.pdf')

    if name_lower.endswith(('.jpg', '.jpeg')):
        mime_type = "image/jpeg"
    elif name_lower.endswith('.png'):
        mime_type = "image/png"
    else:
        mime_type = "application/pdf"

    prompt = """
Jsi specializovaný účetní asistent pro vytěžování českých a slovenských faktur a daňových dokladů.
Analyzuj přiložený dokument a vytěž z něj přesná data v následujícím formátu JSON.
Pokud údaj na faktuře chybí, uveď prázdný řetězec "" nebo 0.0 u částek.

Vrať VÝHRADNĚ validní JSON bez jakýchkoli formátovacích značek (žádné ```json ani komentáře):
{
    "supplier_name": "Název dodavatele / firmy",
    "supplier_ico": "IČO dodavatele",
    "supplier_dic": "DIČ dodavatele",
    "supplier_bank_account": "Číslo účtu / IBAN",
    "invoice_number": "Číslo faktury",
    "variable_symbol": "Variabilní symbol",
    "issue_date": "YYYY-MM-DD",
    "tax_date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "amount_without_vat": 0.0,
    "vat_rate": 21,
    "vat_amount": 0.0,
    "total_amount": 0.0,
    "notes": "Předmět faktury / popis plnění"
}
"""

    if is_pdf:
        content_item = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64_encoded
            }
        }
    else:
        content_item = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64_encoded
            }
        }

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Nenalezen ANTHROPIC_API_KEY v konfiguraci ani v .env.")

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": [
                    content_item,
                    {"type": "text", "text": prompt}
                ]
            }
        ]
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "Accept-Encoding": "identity",
    }
    if is_pdf:
        headers["anthropic-beta"] = "pdfs-2024-09-25"

    req = urllib.request.Request(
        "[https://api.anthropic.com/v1/messages](https://api.anthropic.com/v1/messages)",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        raise RuntimeError(f"Chyba Anthropic API ({e.code}): {err_body}")
    except Exception as e:
        raise RuntimeError(f"Chyba spojení s Anthropic API: {e}")

    result_text = ""
    for block in resp_data.get("content", []):
        if block.get("type") == "text":
            result_text = block.get("text", "")
            break

    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
    result_text = result_text.strip()

    return json.loads(result_text)