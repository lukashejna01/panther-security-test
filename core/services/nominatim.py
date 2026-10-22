"""
Služba pro geografické dohledání poštovního směrovacího čísla (PSČ).
Využívá bezplatné Nominatim API (OpenStreetMap) pro ČR a SR.
"""

import json
import re
import urllib.parse
import urllib.request


def lookup_postcode_by_address(street: str, house_number: str, city: str) -> str:
    """
    Dohledá PSČ přes Nominatim API (OpenStreetMap) pro ČR a SR.
    Pokud adresa není nalezena nebo API neodpoví, vrátí prázdný řetězec.
    """
    if not city:
        return ""

    street_full = f"{street} {house_number}".strip() if street else house_number

    params = {
        'format': 'jsonv2',
        'addressdetails': '1',
        'countrycodes': 'cz,sk',
        'limit': '1',
    }
    if street_full:
        params['street'] = street_full
    params['city'] = city

    url = f"https://nominatim.openstreetmap.org/search?{urllib.parse.urlencode(params)}"
    headers = {
        'User-Agent': 'PantherSecurityApp/1.0 (ops@panther-security.cz)'
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                results = json.loads(response.read().decode('utf-8'))
                if results and 'address' in results[0]:
                    raw_postcode = results[0]['address'].get('postcode', '')
                    clean_postcode = re.sub(r'\D', '', raw_postcode)
                    if len(clean_postcode) == 5:
                        return f"{clean_postcode[:3]} {clean_postcode[3:]}"
                    return clean_postcode
    except Exception as e:
        print(f"[Nominatim API] Vyhledání PSČ selhalo: {e}")

    return ""