"""
Generování QR kódů bez externích služeb.
"""

import base64

from reportlab.graphics.barcode import qrencoder


def qr_code_data_uri(text):
    """
    QR kód jako SVG v data URI (QR Platba na fakturách, párování 2FA aplikace).
    Generuje se lokálně, aby údaje v kódu neodcházely na cizí službu.
    """
    qr = qrencoder.QRCode(None, qrencoder.QRErrorCorrectLevel.M)
    qr.addData(text)
    qr.make()
    n = qr.getModuleCount()
    path = ''.join(f'M{c},{r}h1v1h-1z' for r in range(n) for c in range(n) if qr.isDark(r, c))
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {n + 8} {n + 8}" shape-rendering="crispEdges">'
        f'<rect x="-4" y="-4" width="{n + 8}" height="{n + 8}" fill="#fff"/><path d="{path}" fill="#000"/></svg>'
    )
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()
