"""
Vydávání neveřejných souborů z MEDIA_ROOT (faktury, potvrzení o platbách).
Tyto soubory nesmí být dostupné přímým odkazem do /media/ – jdou jen přes
pohledy s kontrolou oprávnění, které na konci zavolají serve_private_file().
"""

import os

from django.http import FileResponse, Http404

# Typy, které prohlížeč smí zobrazit přímo. Cokoli jiného (např. nahrané .html
# nebo .svg) se jen stáhne, aby se nespustilo jako stránka pod naší doménou.
INLINE_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.gif'}


def serve_private_file(field_file, download_name=None):
    """Vrátí FileResponse pro uložený soubor, nebo 404, pokud na disku chybí."""
    if not field_file:
        raise Http404("Soubor neexistuje.")

    try:
        handle = field_file.open('rb')
    except FileNotFoundError:
        raise Http404("Soubor na serveru chybí.")

    name = download_name or os.path.basename(field_file.name)
    inline = os.path.splitext(name)[1].lower() in INLINE_EXTENSIONS
    response = FileResponse(handle, as_attachment=not inline, filename=name)
    response['Cache-Control'] = 'private, no-store'
    return response
