"""
Klient Informačního systému datových schránek (ISDS) – webové služby SOAP 1.1.

Přihlášení jménem a heslem (HTTP Basic) uživatele datové schránky. Doporučení: pro aplikaci
zřídit v datové schránce samostatného uživatele bez dvoufázového ověření, jen s právy
k odesílání a čtení zpráv. Údaje patří jen do .env na serveru.

Prostředí:
- ostré:     https://ws1.datovka.gov.cz      (dříve ws1.mojedatovaschranka.cz)
- testovací: https://ws1.datovka-test.gov.cz (dříve ws1.czebox.cz)

Služby: /DS/dz (odeslání, stažení zprávy), /DS/dx (seznamy zpráv).
Formát zpráv podle oficiálních WSDL/XSD ISDS (namespace http://isds.czechpoint.cz/v20).
"""

import base64
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

NS = 'http://isds.czechpoint.cz/v20'
SOAP_NS = 'http://schemas.xmlsoap.org/soap/envelope/'

DEFAULT_HOSTS = {
    'test': 'ws1.datovka-test.gov.cz',
    'prod': 'ws1.datovka.gov.cz',
}

# Pořadí prvků obálky zprávy podle skupiny gMessageEnvelopeSub v dmBaseTypes.xsd
ENVELOPE_ORDER = [
    'dmSenderOrgUnit', 'dmSenderOrgUnitNum', 'dbIDRecipient', 'dmRecipientOrgUnit', 'dmRecipientOrgUnitNum',
    'dmToHands', 'dmAnnotation', 'dmRecipientRefNumber', 'dmSenderRefNumber', 'dmRecipientIdent',
    'dmSenderIdent', 'dmLegalTitleLaw', 'dmLegalTitleYear', 'dmLegalTitleSect', 'dmLegalTitlePar',
    'dmLegalTitlePoint', 'dmPersonalDelivery', 'dmAllowSubstDelivery',
]

TIMEOUT = 60


class IsdsError(Exception):
    """Chyba komunikace s datovou schránkou (síť, přihlášení nebo chybový stav ISDS)."""

    def __init__(self, message, code=None):
        self.code = code
        super().__init__(message)


class IsdsClient:
    def __init__(self, username, password, environment='test', host=None):
        if not username or not password:
            raise IsdsError("Chybí přihlašovací údaje k datové schránce (ISDS_USERNAME / ISDS_PASSWORD v .env).")
        if environment not in DEFAULT_HOSTS:
            raise IsdsError(f"Neznámé prostředí datových schránek „{environment}“ (povoleno: test, prod).")
        self.username = username
        self.password = password
        self.environment = environment
        self.base_url = f"https://{host or DEFAULT_HOSTS[environment]}/DS"

    # ------------------------------------------------------------------ SOAP

    def _call(self, service, operation, body_xml):
        import requests
        from lxml import etree

        envelope = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<soapenv:Envelope xmlns:soapenv="{SOAP_NS}" xmlns:v20="{NS}" '
            f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<soapenv:Body><v20:{operation}>{body_xml}</v20:{operation}></soapenv:Body></soapenv:Envelope>'
        )
        try:
            response = requests.post(
                f"{self.base_url}/{service}",
                data=envelope.encode('utf-8'),
                headers={'Content-Type': 'text/xml; charset=utf-8', 'SOAPAction': '""'},
                auth=(self.username, self.password),
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise IsdsError(f"Datová schránka není dostupná: {e}")

        if response.status_code == 401:
            raise IsdsError("Datová schránka odmítla přihlášení – zkontrolujte jméno a heslo "
                            "(a že uživatel nemá zapnuté dvoufázové ověření).")
        if response.status_code >= 500 and b'Fault' not in response.content:
            raise IsdsError(f"Datová schránka vrátila chybu serveru (HTTP {response.status_code}).")

        try:
            root = etree.fromstring(response.content)
        except etree.XMLSyntaxError:
            raise IsdsError(f"Datová schránka vrátila nečitelnou odpověď (HTTP {response.status_code}).")

        fault = root.find(f'.//{{{SOAP_NS}}}Fault')
        if fault is not None:
            text = ' '.join(t.strip() for t in fault.itertext() if t.strip())
            raise IsdsError(f"Chyba SOAP z datové schránky: {text}")

        status_code = root.findtext(f'.//{{{NS}}}dmStatus/{{{NS}}}dmStatusCode')
        status_message = root.findtext(f'.//{{{NS}}}dmStatus/{{{NS}}}dmStatusMessage') or ''
        if status_code is None:
            raise IsdsError("Odpověď datové schránky neobsahuje stav operace.")
        if not status_code.startswith('00'):
            raise IsdsError(f"Datová schránka ohlásila chybu {status_code}: {status_message}", code=status_code)
        return root

    @staticmethod
    def _el(name, value):
        if value is None or value == '':
            return f'<v20:{name} xsi:nil="true"/>'
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        return f'<v20:{name}>{escape(str(value))}</v20:{name}>'

    # --------------------------------------------------------- operace

    def send_message(self, recipient_id, annotation, filename, content, mime_type='application/xml',
                     sender_ref=None):
        """Odešle zprávu s jednou přílohou. Vrací ID datové zprávy (dmID)."""
        values = {
            'dbIDRecipient': recipient_id,
            'dmAnnotation': annotation[:255],
            'dmSenderRefNumber': (sender_ref or '')[:50],
            'dmPersonalDelivery': False,
            'dmAllowSubstDelivery': True,
        }
        envelope = ''.join(self._el(name, values.get(name)) for name in ENVELOPE_ORDER)
        encoded = base64.b64encode(content).decode('ascii')
        files = (
            f'<v20:dmFile dmMimeType="{escape(mime_type)}" dmFileMetaType="main" '
            f'dmFileDescr="{escape(filename)}"><v20:dmEncodedContent>{encoded}</v20:dmEncodedContent></v20:dmFile>'
        )
        root = self._call('dz', 'CreateMessage',
                          f'<v20:dmEnvelope>{envelope}</v20:dmEnvelope><v20:dmFiles>{files}</v20:dmFiles>')
        dm_id = root.findtext(f'.//{{{NS}}}dmID')
        if not dm_id:
            raise IsdsError("Datová schránka nepotvrdila odeslání (chybí ID zprávy).")
        return dm_id

    def list_received(self, since, until=None):
        """Seznam přijatých zpráv v časovém okně. Vrací list slovníků."""
        until = until or (datetime.now() + timedelta(minutes=2))
        body = (
            self._el('dmFromTime', since.strftime('%Y-%m-%dT%H:%M:%S'))
            + self._el('dmToTime', until.strftime('%Y-%m-%dT%H:%M:%S'))
            + self._el('dmRecipientOrgUnitNum', None)
            + self._el('dmStatusFilter', '-1')
            + self._el('dmOffset', 1)
            + self._el('dmLimit', 1000)
        )
        root = self._call('dx', 'GetListOfReceivedMessages', body)
        records = []
        for record in root.iter(f'{{{NS}}}dmRecord'):
            records.append({
                'dm_id': record.findtext(f'{{{NS}}}dmID'),
                'sender_id': record.findtext(f'{{{NS}}}dbIDSender'),
                'sender': record.findtext(f'{{{NS}}}dmSender'),
                'annotation': record.findtext(f'{{{NS}}}dmAnnotation') or '',
                'recipient_ref': record.findtext(f'{{{NS}}}dmRecipientRefNumber') or '',
                'delivery_time': record.findtext(f'{{{NS}}}dmDeliveryTime') or '',
            })
        return records

    def download_message(self, dm_id):
        """Stáhne přijatou zprávu. Vrací list příloh: {'name', 'mime', 'content' (bytes)}."""
        root = self._call('dz', 'MessageDownload', self._el('dmID', dm_id))
        files = []
        for node in root.iter(f'{{{NS}}}dmFile'):
            encoded = node.findtext(f'{{{NS}}}dmEncodedContent')
            content = base64.b64decode(encoded) if encoded else b''
            files.append({
                'name': node.get('dmFileDescr') or 'priloha',
                'mime': node.get('dmMimeType') or '',
                'content': content,
            })
        return files


def client_from_settings():
    """Klient podle nastavení v settings / .env."""
    from django.conf import settings

    return IsdsClient(
        username=getattr(settings, 'ISDS_USERNAME', ''),
        password=getattr(settings, 'ISDS_PASSWORD', ''),
        environment=getattr(settings, 'ISDS_ENVIRONMENT', 'test'),
        host=getattr(settings, 'ISDS_HOST', '') or None,
    )