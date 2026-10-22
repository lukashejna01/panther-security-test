/**
 * Panther Security Operations - Klientské interakce a AI Scanner
 */

document.addEventListener('DOMContentLoaded', function () {
    // ==========================================
    // 1. CHYTRÁ SPRÁVA FLASH ZPRÁV (ALERTS)
    // ==========================================
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        var text = alert.textContent || "";

        // Pokud zpráva obsahuje vygenerované heslo nebo přihlašovací údaje:
        if (text.includes('Dočasné heslo') || text.includes('Přihlašovací jméno')) {
            // Zvýrazněný prémiový styl Panther Security
            alert.style.border = '2px solid #facc15';
            alert.style.background = 'rgba(20, 26, 38, 0.98)';
            alert.style.boxShadow = '0 12px 36px rgba(0, 0, 0, 0.6)';
            alert.style.position = 'relative';
            alert.style.paddingRight = '190px';
            alert.style.color = '#ffffff';

            // Kontejner na ovládací tlačítka vpravo
            var actionsContainer = document.createElement('div');
            actionsContainer.style.position = 'absolute';
            actionsContainer.style.right = '14px';
            actionsContainer.style.top = '50%';
            actionsContainer.style.transform = 'translateY(-50%)';
            actionsContainer.style.display = 'flex';
            actionsContainer.style.gap = '8px';

            // Tlačítko 1: Kopírovat údaje do schránky
            var copyBtn = document.createElement('button');
            copyBtn.type = 'button';
            copyBtn.innerHTML = '📋 Kopírovat';
            copyBtn.style.background = '#facc15';
            copyBtn.style.color = '#000000';
            copyBtn.style.border = 'none';
            copyBtn.style.padding = '6px 12px';
            copyBtn.style.borderRadius = '4px';
            copyBtn.style.cursor = 'pointer';
            copyBtn.style.fontSize = '12px';
            copyBtn.style.fontWeight = '700';

            copyBtn.onclick = function () {
                var cleanText = text.replace('✕ Zavřít', '').replace('📋 Kopírovat', '').trim();
                navigator.clipboard.writeText(cleanText).then(function () {
                    copyBtn.innerHTML = '✅ Zkopírováno!';
                    setTimeout(function () {
                        copyBtn.innerHTML = '📋 Kopírovat';
                    }, 2500);
                }).catch(function () {
                    copyBtn.innerHTML = 'Chyba kopírování';
                });
            };

            // Tlačítko 2: Zavřít křížkem
            var closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.innerHTML = '✕ Zavřít';
            closeBtn.style.background = 'rgba(255, 255, 255, 0.12)';
            closeBtn.style.border = '1px solid rgba(255, 255, 255, 0.2)';
            closeBtn.style.color = '#ffffff';
            closeBtn.style.padding = '6px 12px';
            closeBtn.style.borderRadius = '4px';
            closeBtn.style.cursor = 'pointer';
            closeBtn.style.fontSize = '12px';
            closeBtn.style.fontWeight = '600';

            closeBtn.onclick = function () {
                alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(function () {
                    alert.remove();
                }, 400);
            };

            actionsContainer.appendChild(copyBtn);
            actionsContainer.appendChild(closeBtn);
            alert.appendChild(actionsContainer);

            // Není zde setTimeout -> zpráva zůstává trvale zobrazena, dokud ji nezavřeš!
        } else {
            // Obyčejné informační zprávy ponecháme 15 sekund
            setTimeout(function () {
                alert.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(function () {
                    alert.remove();
                }, 600);
            }, 15000);
        }
    });

    // ==========================================
    // 2. INTERAKTIVNÍ ANIMOVANÝ AI SCANNER MODAL
    // ==========================================
    var forms = document.querySelectorAll('form[enctype="multipart/form-data"]');
    forms.forEach(function (form) {
        form.addEventListener('submit', function () {
            // Detekce, zda se jedná o OCR požadavek (OP nebo faktura)
            var hasScanInput = form.querySelector('input[name="scan_id"]') ||
                               form.querySelector('button[name="scan_id"]') ||
                               form.querySelector('button[name="scan_invoice"]') ||
                               form.querySelector('input[type="file"]');

            if (hasScanInput) {
                // Vytvoření celoobrazovkového překryvu (overlay)
                var overlay = document.createElement('div');
                overlay.id = 'ai-scanner-overlay';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100vw';
                overlay.style.height = '100vh';
                overlay.style.background = 'rgba(10, 13, 20, 0.92)';
                overlay.style.backdropFilter = 'blur(14px)';
                overlay.style.webkitBackdropFilter = 'blur(14px)';
                overlay.style.display = 'flex';
                overlay.style.flexDirection = 'column';
                overlay.style.alignItems = 'center';
                overlay.style.justifyContent = 'center';
                overlay.style.zIndex = '99999';

                overlay.innerHTML = `
                    <div style="position: relative; width: 130px; height: 130px; margin-bottom: 24px;">
                        <!-- Pulzující vnější radarový kruh -->
                        <div style="position: absolute; width: 100%; height: 100%; border: 3px solid rgba(250, 204, 21, 0.25); border-radius: 50%; animation: pulseWave 1.8s ease-out infinite;"></div>
                        <!-- Rotující vnější skener v Panther žluté -->
                        <div style="position: absolute; width: 100%; height: 100%; border: 3px solid transparent; border-top: 3px solid #facc15; border-right: 3px solid #facc15; border-radius: 50%; animation: spinRadar 1s linear infinite;"></div>
                        <!-- Ikona AI ve středu -->
                        <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 42px; animation: pulseCore 1.5s ease-in-out infinite alternate;">
                            🤖
                        </div>
                    </div>
                    <h2 style="font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px; margin: 0 0 10px; text-shadow: 0 0 20px rgba(250,204,21,0.3);">
                        Claude AI analyzuje dokument...
                    </h2>
                    <p style="color: #facc15; font-size: 14px; font-weight: 600; text-align: center; max-width: 440px; line-height: 1.5; margin: 0 20px;">
                        Probíhá vytěžování údajů, validace a automatické dohledávání PSČ přes OpenStreetMap API.
                    </p>
                `;

                // Vložení CSS animací
                var style = document.createElement('style');
                style.textContent = `
                    @keyframes spinRadar {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                    @keyframes pulseWave {
                        0% { transform: scale(0.9); opacity: 0.9; }
                        100% { transform: scale(1.4); opacity: 0; }
                    }
                    @keyframes pulseCore {
                        0% { transform: translate(-50%, -50%) scale(0.92); opacity: 0.8; }
                        100% { transform: translate(-50%, -50%) scale(1.08); opacity: 1; }
                    }
                `;
                document.head.appendChild(style);
                document.body.appendChild(overlay);
            }
        });
    });
});