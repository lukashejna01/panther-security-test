"""
Služba pro automatické vytěžování dat z přijatých dodavatelských faktur pomocí Claude API.
"""

import base64
import json
from .claude_ocr import get_anthropic_client


def extract_data_from_invoice(file_obj) -> dict:
    """
    Vytěží strukturovaná data z faktury (PDF, PNG, JPG) pomocí Claude API.
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

    client = get_anthropic_client()

    models_to_try = [
        "claude-sonnet-5",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001"
    ]

    response = None
    last_error = None

    for model_name in models_to_try:
        try:
            kwargs = {
                "model": model_name,
                "max_tokens": 1500,
                "temperature": 0.0,
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
            if is_pdf:
                kwargs["betas"] = ["pdfs-2024-09-25"]

            response = client.beta.messages.create(**kwargs) if is_pdf else client.messages.create(**kwargs)
            if response:
                break
        except Exception as e:
            last_error = e
            continue

    if not response:
        raise RuntimeError(f"Chyba při vytěžování faktury: {last_error}")

    result_text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            result_text = block.text
            break
    if not result_text:
        result_text = response.content[0].text

    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.split("```")[1]
        if result_text.startswith("json"):
            result_text = result_text[4:]
    result_text = result_text.strip()

    return json.loads(result_text)