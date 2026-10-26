/**
 * Panther Security Operations - Klientské interakce a AI Scanner
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Správa flash zpráv: Důležité zprávy s heslem NIKDY nemizí automaticky!
    var alerts = document.querySelectorAll('.alert');
    alerts.forEach(function (alert) {
        var text = alert.textContent || "";

        if (text.includes('Dočasné heslo') || text.includes('Přihlašovací jméno')) {
            alert.style.border = '2px solid #facc15';
            alert.style.background = 'rgba(26, 32, 44, 0.95)';
            alert.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
            alert.style.position = 'relative';
            alert.style.paddingRight = '80px';

            var closeBtn = document.createElement('button');
            closeBtn.innerHTML = '✕ Zavřít';
            closeBtn.style.position = 'absolute';
            closeBtn.style.right = '12px';
            closeBtn.style.top = '50%';
            closeBtn.style.transform = 'translateY(-50%)';
            closeBtn.style.background = 'rgba(255,255,255,0.1)';
            closeBtn.style.border = '1px solid rgba(255,255,255,0.2)';
            closeBtn.style.color = '#fff';
            closeBtn.style.padding = '5px 10px';
            closeBtn.style.borderRadius = '4px';
            closeBtn.style.cursor = 'pointer';
            closeBtn.style.fontSize = '12px';
            closeBtn.style.fontWeight = 'bold';

            closeBtn.onclick = function () {
                alert.remove();
            };

            alert.appendChild(closeBtn);
        } else {
            setTimeout(function () {
                alert.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                alert.style.opacity = '0';
                alert.style.transform = 'translateY(-10px)';
                setTimeout(function () {
                    alert.remove();
                }, 600);
            }, 10000);
        }
    });

    // 2. Interaktivní celoobrazovkový AI Scanner pro Claude OCR
    var forms = document.querySelectorAll('form[enctype="multipart/form-data"]');
    forms.forEach(function (form) {
        form.addEventListener('submit', function () {
            var hasScanInput = form.querySelector('input[name="scan_id"]') ||
                               form.querySelector('button[name="scan_id"]') ||
                               form.querySelector('button[name="scan_invoice"]') ||
                               form.querySelector('input[type="file"]');

            if (hasScanInput) {
                // Pokud už overlay náhodou existuje, smažeme ho
                var oldOverlay = document.getElementById('ai-scanner-overlay');
                if (oldOverlay) oldOverlay.remove();

                // Vytvoření celoobrazovkového překryvu
                var overlay = document.createElement('div');
                overlay.id = 'ai-scanner-overlay';
                overlay.style.cssText = `
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                    width: 100vw !important;
                    height: 100vh !important;
                    background: rgba(8, 10, 16, 0.94) !important;
                    backdrop-filter: blur(16px) !important;
                    -webkit-backdrop-filter: blur(16px) !important;
                    display: flex !important;
                    flex-direction: column !important;
                    align-items: center !important;
                    justify-content: center !important;
                    z-index: 9999999 !important;
                    overflow: hidden !important;
                    touch-action: none !important;
                `;

                overlay.innerHTML = `
                    <div style="position: relative; width: 140px; height: 140px; margin-bottom: 28px; display: flex; align-items: center; justify-content: center;">
                        <!-- Pulzující radarové vlny -->
                        <div style="position: absolute; inset: 0; border: 3px solid rgba(250, 204, 21, 0.25); border-radius: 50%; animation: pantherPulseWave 2s ease-out infinite;"></div>
                        <div style="position: absolute; inset: -15px; border: 2px dashed rgba(250, 204, 21, 0.15); border-radius: 50%; animation: pantherPulseWave 2.5s ease-out infinite 0.5s;"></div>
                        
                        <!-- Rotující žlutý neonový prstenec -->
                        <div style="position: absolute; inset: 0; border: 3px solid transparent; border-top: 3px solid #facc15; border-right: 3px solid #facc15; border-radius: 50%; animation: pantherSpinRadar 1s linear infinite; filter: drop-shadow(0 0 10px rgba(250, 204, 21, 0.6));"></div>
                        
                        <!-- Ikona robota ve středu s pulzem -->
                        <div style="font-size: 48px; filter: drop-shadow(0 0 16px rgba(250, 204, 21, 0.7)); animation: pantherCorePulse 1.4s ease-in-out infinite alternate;">
                            🤖
                        </div>
                    </div>

                    <h2 style="font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px; margin: 0 0 10px; text-align: center; text-shadow: 0 0 25px rgba(250, 204, 21, 0.4); padding: 0 16px;">
                        Claude AI analyzuje dokument...
                    </h2>
                    <p style="color: #facc15; font-size: 14px; font-weight: 600; text-align: center; max-width: 440px; line-height: 1.5; margin: 0 20px; text-shadow: 0 2px 8px rgba(0,0,0,0.8);">
                        Probíhá bezpečné vytěžování a kontrola dat z dokladu...
                    </p>
                `;

                // Vložení globálních CSS animací
                if (!document.getElementById('ai-scanner-animations')) {
                    var style = document.createElement('style');
                    style.id = 'ai-scanner-animations';
                    style.textContent = `
                        @keyframes pantherSpinRadar {
                            0% { transform: rotate(0deg); }
                            100% { transform: rotate(360deg); }
                        }
                        @keyframes pantherPulseWave {
                            0% { transform: scale(0.85); opacity: 0.9; }
                            100% { transform: scale(1.5); opacity: 0; }
                        }
                        @keyframes pantherCorePulse {
                            0% { transform: scale(0.92); opacity: 0.85; }
                            100% { transform: scale(1.08); opacity: 1; }
                        }
                    `;
                    document.head.appendChild(style);
                }

                document.body.appendChild(overlay);
            }
        });
    });
});