"""
Služba pro OCR digitalizaci českých dokladů totožnosti (občanský průkaz / pas).
Využívá Anthropic Claude API a automaticky doplňuje chybějící PSČ přes Nominatim.
"""

import base64
import json
import os
import anthropic
from django.conf import settings

from .nominatim import lookup_postcode_by_address


def get_anthropic_client() -> anthropic.Anthropic:
    """Vrací inicializovaného klienta Anthropic s API klíčem z konfigurace."""
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None) or os.getenv('ANTHROPIC_API_KEY')
    if not api_key or api_key == 'tvuj-anthropic-api-klic':
        raise ValueError("Chybí platný ANTHROPIC_API_KEY v settings.py / .env souboru!")
    return anthropic.Anthropic(api_key=api_key)


def extract_data_from_id(image_file) -> dict:
    """
    Odešle PDF nebo obrázek dokladu do Claude API a vrátí strukturovaný slovník.
    """
    client = get_anthropic_client()

    image_file.seek(0)
    file_bytes = image_file.read()
    file_base64 = base64.b64encode(file_bytes).decode('utf-8')

    content_type = getattr(image_file, 'content_type', None) or ''
    file_name = getattr(image_file, 'name', '').lower()
    is_pdf = 'pdf' in content_type or file_name.endswith('.pdf')

    if is_pdf:
        source_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": file_base64,
            }
        }
    else:
        media_type = "image/png" if file_name.endswith('.png') else "image/jpeg"
        source_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": file_base64,
            }
        }

    prompt = """Jsi specializovaný asistent pro OCR českých dokladů totožnosti (občanský průkaz, pas).
Dokument může obsahovat přední i zadní stranu.
Vytáhni údaje a vrať VÝHRADNĚ validní JSON bez jakéhokoliv dalšího textu či značek:
{
    "first_name": "Jméno",
    "last_name": "Příjmení",
    "birth_date": "YYYY-MM-DD",
    "birth_number": "XXXXXX/XXXX",
    "id_card_number": "Číslo dokladu",
    "street": "Ulice",
    "house_number": "číslo popisné",
    "orientation_number": "číslo orientační",
    "city": "Město",
    "zip_code": "11000"
}
Pravidla:
- "street": Pouze název ulice bez čísla. Pokud obec nemá ulice, uveď název obce.
- "birth_number": Uveď s lomítkem.
- "orientation_number": Pokud na dokladu není, nech prázdný řetězec "".
"""

    models_to_try = [
        "claude-sonnet-5",
        "claude-3-5-sonnet-20241022",
        "claude-haiku-4-5-20251001",
    ]

    response = None
    last_error = None

    for model_name in models_to_try:
        try:
            extra_headers = {"anthropic-beta": "pdfs-2024-09-25"} if is_pdf else {}
            response = client.messages.create(
                model=model_name,
                max_tokens=1500,
                extra_headers=extra_headers,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            source_block,
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
            if response:
                break
        except Exception as e:
            last_error = e
            print(f"[Claude OCR] Pokus s modelem '{model_name}' selhal: {e}")
            continue

    if not response:
        print(f"[Claude OCR FATAL] Žádný model neuspěl. Poslední chyba: {last_error}")
        raise RuntimeError(f"Chyba Claude API: {last_error}")

    # Zpracování odpovědi
    raw_response = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            raw_response = block.text
            break

    if not raw_response:
        raw_response = response.content[0].text

    raw_response = raw_response.strip()
    if raw_response.startswith("```"):
        raw_response = raw_response.split("```")[1]
        if raw_response.startswith("json"):
            raw_response = raw_response[4:]
    raw_response = raw_response.strip()

    extracted = json.loads(raw_response)

    # Automatické dohledání PSČ, pokud na OP chybí
    if not extracted.get('zip_code'):
        hn = extracted.get('house_number', '') or extracted.get('orientation_number', '')
        found_zip = lookup_postcode_by_address(
            street=extracted.get('street', ''),
            house_number=hn,
            city=extracted.get('city', '')
        )
        if found_zip:
            extracted['zip_code'] = found_zip

    return extracted