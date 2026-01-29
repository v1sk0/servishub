# Modal Design System - Premium Glassmorphism

Dokumentacija za konzistentan dizajn modala u ServisHub aplikaciji.

---

## Paleta Boja

### Primarne Boje (Purple/Indigo Accent)
```css
--primary-gradient: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
--primary-500: #8b5cf6;
--primary-600: #7c3aed;
--primary-700: #6d28d9;
```

### Akcione Boje
```css
/* Gotovina / Uspeh */
--cash-green: #22c55e;
--cash-green-light: #4ade80;
--cash-bg: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
--cash-border: #86efac;

/* Kartica */
--card-blue: #3b82f6;
--card-blue-light: #60a5fa;
--card-bg: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
--card-border: #93c5fd;

/* Prenos */
--transfer-purple: #8b5cf6;
--transfer-purple-light: #a78bfa;
--transfer-bg: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
--transfer-border: #c4b5fd;

/* Upozorenje (Currency Conversion) */
--warning-bg: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
--warning-border: #fbbf24;
--warning-text: #92400e;
```

### Neutralne Boje
```css
/* Light Theme */
--bg-primary: rgba(255, 255, 255, 0.95);
--bg-secondary: #f8fafc;
--bg-tertiary: #f1f5f9;
--border-light: #e2e8f0;
--border-medium: #cbd5e1;
--text-primary: #1e293b;
--text-secondary: #64748b;
--text-muted: #94a3b8;

/* Dark Theme (Glass) */
--glass-bg: rgba(30, 41, 59, 0.95);
--glass-border: rgba(255, 255, 255, 0.1);
--glass-text-primary: #f1f5f9;
--glass-text-secondary: #94a3b8;
```

---

## Struktura Modala

### HTML Template

```html
<!-- Modal Overlay -->
<div x-show="showModal" x-cloak class="modal-overlay" @click.self="showModal = false">
    <div class="modal-container">
        <!-- Header -->
        <div class="modal-header">
            <div class="modal-header-content">
                <div class="modal-icon">
                    <svg><!-- Icon SVG --></svg>
                </div>
                <div>
                    <h3 class="modal-title">Naslov Modala</h3>
                    <p class="modal-subtitle">Podnaslov ili dodatne info</p>
                </div>
            </div>
            <button class="modal-close" @click="showModal = false">
                <svg><!-- X icon --></svg>
            </button>
        </div>

        <!-- Body -->
        <div class="modal-body">
            <!-- Info Card -->
            <div class="modal-info-card">
                <p class="info-title">Naslov</p>
                <p class="info-subtitle">Podnaslov</p>
            </div>

            <!-- Form Fields -->
            <div class="modal-field">
                <label class="modal-label">Label</label>
                <input type="text" class="modal-input">
            </div>

            <!-- Action Grid (Payment Buttons) -->
            <div class="modal-field">
                <label class="modal-label">Izbor</label>
                <div class="modal-action-grid">
                    <button class="modal-action-btn cash" :class="{'active': selected === 'CASH'}">
                        <svg><!-- Icon --></svg>
                        <span>Gotovina</span>
                    </button>
                    <!-- More buttons -->
                </div>
            </div>

            <!-- Total Card -->
            <div class="modal-total-card">
                <span class="total-label">UKUPNO</span>
                <span class="total-amount">12,500 RSD</span>
            </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
            <button class="modal-btn-cancel">Otkaži</button>
            <button class="modal-btn-confirm">Potvrdi</button>
        </div>
    </div>
</div>
```

---

## CSS Stilovi

### Overlay i Container

```css
/* Overlay with blur */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.6);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    animation: overlayFadeIn 0.2s ease-out;
}

@keyframes overlayFadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Modal container - Glassmorphism */
.modal-container {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 20px;
    width: 100%;
    max-width: 420px;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.1),
        0 20px 50px -10px rgba(0, 0, 0, 0.25),
        0 0 100px -20px rgba(124, 58, 237, 0.15);
    overflow: hidden;
    animation: modalSlideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes modalSlideIn {
    from {
        opacity: 0;
        transform: scale(0.95) translateY(20px);
    }
    to {
        opacity: 1;
        transform: scale(1) translateY(0);
    }
}
```

### Header

```css
.modal-header {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
    padding: 20px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
}

/* Glass shine overlay */
.modal-header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, transparent 50%);
    pointer-events: none;
}

.modal-header-content {
    display: flex;
    align-items: center;
    gap: 14px;
    position: relative;
    z-index: 1;
}

.modal-icon {
    width: 44px;
    height: 44px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(10px);
}

.modal-icon svg {
    width: 24px;
    height: 24px;
    color: white;
}

.modal-title {
    color: white;
    font-size: 17px;
    font-weight: 600;
    margin: 0;
    letter-spacing: -0.02em;
}

.modal-subtitle {
    color: rgba(255, 255, 255, 0.75);
    font-size: 13px;
    margin: 3px 0 0 0;
}

.modal-close {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    border: none;
    background: rgba(255, 255, 255, 0.15);
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}

.modal-close:hover {
    background: rgba(255, 255, 255, 0.25);
    color: white;
}

.modal-close svg {
    width: 18px;
    height: 18px;
}
```

### Body

```css
.modal-body {
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 18px;
}

/* Info Card */
.modal-info-card {
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.info-title {
    font-size: 15px;
    font-weight: 600;
    color: #1e293b;
    margin: 0;
}

.info-subtitle {
    font-size: 13px;
    color: #64748b;
    margin: 4px 0 0 0;
}

/* Status Badge */
.modal-status-badge {
    background: linear-gradient(135deg, #ddd6fe 0%, #c4b5fd 100%);
    color: #6d28d9;
    font-size: 11px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
```

### Form Fields

```css
.modal-field {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.modal-label {
    font-size: 13px;
    font-weight: 500;
    color: #64748b;
}

.modal-input {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    font-size: 14px;
    color: #1e293b;
    background: #fafafa;
    transition: all 0.2s;
}

.modal-input:focus {
    outline: none;
    border-color: #8b5cf6;
    background: white;
    box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.1);
}

/* Large Price Input */
.modal-input-price {
    width: 100%;
    padding: 14px 60px 14px 18px;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    font-size: 20px;
    font-weight: 600;
    color: #1e293b;
    background: #fafafa;
    transition: all 0.2s;
}

.modal-input-price:focus {
    outline: none;
    border-color: #8b5cf6;
    background: white;
    box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.1);
}

.modal-input-suffix {
    position: absolute;
    right: 18px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 14px;
    font-weight: 500;
    color: #94a3b8;
}
```

### Action Grid (Payment Buttons)

```css
.modal-action-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
}

.modal-action-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 14px 8px;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    background: #fafafa;
    color: #64748b;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.modal-action-btn svg {
    width: 22px;
    height: 22px;
}

.modal-action-btn:hover {
    border-color: #cbd5e1;
    background: white;
}

/* Cash Active */
.modal-action-btn.cash.active {
    border-color: #22c55e;
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    color: #16a34a;
}

/* Card Active */
.modal-action-btn.card.active {
    border-color: #3b82f6;
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    color: #2563eb;
}

/* Transfer Active */
.modal-action-btn.transfer.active {
    border-color: #8b5cf6;
    background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
    color: #7c3aed;
}
```

### Special Cards

```css
/* Cash Card (Green) */
.modal-cash-card {
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border: 1px solid #86efac;
    border-radius: 14px;
    padding: 16px 18px;
}

.modal-cash-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: #166534;
    margin-bottom: 10px;
}

.modal-cash-input {
    width: 100%;
    padding: 12px 16px;
    border: 2px solid #86efac;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 600;
    background: white;
    color: #166534;
}

.modal-cash-input:focus {
    outline: none;
    border-color: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15);
}

/* Currency Conversion Card (Yellow) */
.modal-currency-card {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border: 1px solid #fbbf24;
    border-radius: 14px;
    padding: 16px 18px;
}

.modal-currency-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 14px;
}

.modal-currency-header svg {
    width: 18px;
    height: 18px;
    color: #b45309;
}

.modal-currency-header span {
    font-size: 13px;
    font-weight: 600;
    color: #92400e;
}
```

### Total Card

```css
.modal-total-card {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%);
    border-radius: 14px;
    padding: 18px 22px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: relative;
    overflow: hidden;
}

.modal-total-card::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, transparent 50%);
    pointer-events: none;
}

.total-label {
    font-size: 12px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
    letter-spacing: 0.5px;
    position: relative;
    z-index: 1;
}

.total-amount {
    font-size: 26px;
    font-weight: 700;
    color: white;
    letter-spacing: -0.02em;
    position: relative;
    z-index: 1;
}
```

### Footer

```css
.modal-footer {
    padding: 18px 24px;
    background: linear-gradient(to top, #f8fafc, rgba(248, 250, 252, 0.9));
    border-top: 1px solid #e2e8f0;
    display: flex;
    gap: 12px;
}

.modal-btn-cancel {
    flex: 1;
    padding: 14px 20px;
    border: 2px solid #e2e8f0;
    border-radius: 12px;
    background: white;
    color: #64748b;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
}

.modal-btn-cancel:hover {
    border-color: #cbd5e1;
    color: #475569;
    background: #f8fafc;
}

.modal-btn-confirm {
    flex: 1.5;
    padding: 14px 20px;
    border: none;
    border-radius: 12px;
    background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
    color: white;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
}

.modal-btn-confirm:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(34, 197, 94, 0.4);
}

.modal-btn-confirm:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    box-shadow: none;
}

.modal-btn-confirm svg {
    width: 18px;
    height: 18px;
}
```

---

## Dark Theme Support

```css
/* Dark Theme (Glass Theme) */
.glass-theme .modal-overlay {
    background: rgba(0, 0, 0, 0.7);
}

.glass-theme .modal-container {
    background: rgba(30, 41, 59, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.05),
        0 20px 50px -10px rgba(0, 0, 0, 0.5),
        0 0 100px -20px rgba(139, 92, 246, 0.2);
}

.glass-theme .modal-info-card {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
}

.glass-theme .info-title { color: #f1f5f9; }
.glass-theme .info-subtitle { color: #94a3b8; }

.glass-theme .modal-status-badge {
    background: rgba(139, 92, 246, 0.2);
    color: #c4b5fd;
}

.glass-theme .modal-label { color: #94a3b8; }

.glass-theme .modal-input,
.glass-theme .modal-input-price {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
    color: #f1f5f9;
}

.glass-theme .modal-input:focus,
.glass-theme .modal-input-price:focus {
    border-color: #8b5cf6;
    background: rgba(255, 255, 255, 0.08);
    box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.2);
}

.glass-theme .modal-input-suffix { color: #64748b; }

.glass-theme .modal-action-btn {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
    color: #94a3b8;
}

.glass-theme .modal-action-btn:hover {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
}

.glass-theme .modal-action-btn.cash.active {
    background: rgba(34, 197, 94, 0.15);
    border-color: #22c55e;
    color: #4ade80;
}

.glass-theme .modal-action-btn.card.active {
    background: rgba(59, 130, 246, 0.15);
    border-color: #3b82f6;
    color: #60a5fa;
}

.glass-theme .modal-action-btn.transfer.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: #8b5cf6;
    color: #a78bfa;
}

.glass-theme .modal-cash-card {
    background: rgba(34, 197, 94, 0.1);
    border-color: rgba(34, 197, 94, 0.3);
}

.glass-theme .modal-cash-label { color: #4ade80; }

.glass-theme .modal-cash-input {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(34, 197, 94, 0.3);
    color: #4ade80;
}

.glass-theme .modal-currency-card {
    background: rgba(251, 191, 36, 0.1);
    border-color: rgba(251, 191, 36, 0.3);
}

.glass-theme .modal-currency-header svg { color: #fbbf24; }
.glass-theme .modal-currency-header span { color: #fcd34d; }

.glass-theme .modal-footer {
    background: rgba(15, 23, 42, 0.5);
    border-color: rgba(255, 255, 255, 0.1);
}

.glass-theme .modal-btn-cancel {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.1);
    color: #94a3b8;
}

.glass-theme .modal-btn-cancel:hover {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.15);
    color: #f1f5f9;
}
```

---

## Animacije

```css
/* Spinner */
.animate-spin {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

/* Fade transitions za x-show */
[x-cloak] { display: none !important; }
```

---

## Primeri Upotrebe

### Collect Modal (Naplata)
- Header: Purple gradient
- Body: Info card + Price input + Payment buttons + Cash card + Total
- Footer: Cancel + Confirm (green)

### Delete Confirm Modal
- Header: Red gradient (`#ef4444` → `#dc2626`)
- Body: Warning message
- Footer: Cancel + Delete (red)

### Edit Modal
- Header: Blue gradient (`#3b82f6` → `#2563eb`)
- Body: Form fields
- Footer: Cancel + Save (blue)

### Success Modal
- Header: Green gradient (`#22c55e` → `#16a34a`)
- Body: Success message + Icon
- Footer: Close button

---

## Checklist za Novi Modal

1. [ ] Overlay sa blur efektom
2. [ ] Container sa glassmorphism stilom
3. [ ] Header sa gradijentom i ikonom
4. [ ] Close dugme (X) u gornjem desnom uglu
5. [ ] Body sa konzistentnim padding-om (24px)
6. [ ] Form polja sa focus stilovima
7. [ ] Footer sa dugmadima (Cancel levo, Action desno)
8. [ ] Dark theme podrška (.glass-theme)
9. [ ] Animacije (overlay fade, modal slide)
10. [ ] Responsive (max-width, padding na mobilnom)

---

*Poslednje ažuriranje: v421 - Januar 2026*
