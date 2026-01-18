# ServisHub UI/UX Performance Optimizations

> Poslednje ažuriranje: 18. Januar 2026 (v164)

---

## Overview

Ovaj dokument opisuje sve UI/UX optimizacije implementirane za eliminaciju trzanja (flickering), poboljšanje loading stanja i generalno unapređenje korisničkog iskustva.

---

## 1. FOUC Prevention (Flash of Unstyled Content)

### Problem
Prilikom učitavanja stranice, korisnik bi na kratko video nestilovani sadržaj pre nego što se CSS učita, što stvara vizuelni "trzaj".

### Rešenje

**Lokacija:** `app/templates/layouts/base.html`

```css
/* Prevent FOUC - opacity transition instead of visibility */
html:not(.theme-ready) body {
    opacity: 0;
}
html.theme-ready body {
    opacity: 1;
    transition: opacity 0.15s ease-out;
}
```

**JavaScript koji aktivira prikaz:**
```javascript
(function() {
    var root = document.documentElement;
    var theme = localStorage.getItem('servishub-theme') || 'light';
    if (theme === 'glass') {
        root.classList.add('glass-theme');
    }
    // Mark theme as ready to show body immediately
    root.classList.add('theme-ready');
})();
```

### Zašto opacity umesto visibility?
- `visibility: hidden` → `visible` je abruptan prelaz
- `opacity: 0` → `1` sa transition daje smooth fade-in efekat
- Korisnik ne primećuje prelaz jer je dovoljno brz (150ms)

---

## 2. Alpine.js x-cloak Direktiva

### Problem
Alpine.js elementi mogu bljesnuti sa sirovim template sintaksom (`{{ value }}`, `x-text`, itd.) pre nego što se Alpine inicijalizuje.

### Rešenje

**CSS (u base.html):**
```css
[x-cloak] { display: none !important; }
```

**Primena na glavne kontejnere:**

```html
<!-- tenant.html -->
<div class="tenant-app" x-data="tenantApp()" x-cloak>

<!-- settings/index.html -->
<div x-data="settingsPage()" x-cloak>

<!-- dashboard.html -->
<div x-data="dashboardData()" x-cloak>
```

### Gde dodati x-cloak?
- Na root element sa `x-data`
- Na sve elemente koji koriste Alpine binding pre renderovanja
- **NE** dodavati na sub-elemente unutar već zaštićenog kontejnera

---

## 3. Tab Transitions

### Problem
Prelazak između tabova (npr. u Settings stranici) bio je abruptan - sadržaj bi jednostavno nestao/pojavio se.

### Rešenje

**Lokacija:** `app/templates/tenant/settings/index.html`

```html
<!-- Glavni tabovi (150ms) -->
<div x-show="!loading && activeTab === 'profile'"
     x-transition:enter="transition ease-out duration-150"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     class="space-y-6">
```

```html
<!-- Pod-tabovi u Javna Stranica (100ms - brži) -->
<div x-show="publicSubTab === 'basic'"
     x-transition:enter="transition ease-out duration-100"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100"
     class="space-y-6">
```

### Trajanje animacija
| Element | Trajanje | Razlog |
|---------|----------|--------|
| Glavni tabovi | 150ms | Dovoljno vidljivo, nije sporo |
| Pod-tabovi | 100ms | Brži jer korisnik očekuje instant |
| Modali | 200-300ms | Treba da bude primetniji |

---

## 4. Loading Skeletons

### Problem
Dok se podaci učitavaju, korisnik vidi prazne elemente ili "0" vrednosti, što deluje kao bug.

### Rešenje

**CSS (dodato u dashboard.html i list.html):**
```css
/* Skeleton loading animation */
.skeleton {
    background: linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%);
    background-size: 200% 100%;
    animation: skeleton-loading 1.5s infinite;
    border-radius: 4px;
}

/* Glass theme variant */
.glass-theme .skeleton {
    background: linear-gradient(90deg,
        rgba(255,255,255,0.05) 25%,
        rgba(255,255,255,0.1) 50%,
        rgba(255,255,255,0.05) 75%);
    background-size: 200% 100%;
}

@keyframes skeleton-loading {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
}

/* Skeleton variants */
.skeleton-text {
    height: 1em;
    width: 60%;
}

.skeleton-value {
    height: 2.5rem;
    width: 4rem;
    margin-top: 0.5rem;
}

.skeleton-cell {
    height: 1rem;
    display: inline-block;
}
```

**Primena u Dashboard stat karticama:**
```html
<template x-if="loading">
    <div class="skeleton skeleton-value"></div>
</template>
<template x-if="!loading">
    <p class="stat-value mt-2" x-text="stats.openTickets || 0"></p>
</template>
```

**Primena u Tickets tabeli:**
```html
<!-- Loading skeleton rows -->
<template x-if="loading">
    <template x-for="i in 5" :key="'skeleton-'+i">
        <tr class="skeleton-row">
            <td><div class="skeleton skeleton-cell w-16"></div></td>
            <td><div class="skeleton skeleton-cell w-20"></div></td>
            <td><div class="skeleton skeleton-cell w-32"></div></td>
            <td><div class="skeleton skeleton-cell w-24"></div></td>
            <td><div class="skeleton skeleton-cell w-20"></div></td>
            <td><div class="skeleton skeleton-cell w-16"></div></td>
            <td><div class="skeleton skeleton-cell w-20"></div></td>
        </tr>
    </template>
</template>
```

### Skeleton dimenzije
| Tip | Širina | Visina | Upotreba |
|-----|--------|--------|----------|
| `skeleton-value` | 4rem | 2.5rem | Brojevi u stat karticama |
| `skeleton-text` | 60% | 1em | Tekst labele |
| `skeleton-cell` | varijabilna (w-16, w-20, w-32) | 1rem | Ćelije tabele |

---

## 5. Chart.js Theme-Aware Tooltips

### Problem
Chart.js tooltips u Glass temi imali su loš kontrast - beli tekst na beloj pozadini.

### Rešenje

**Lokacija:** `app/templates/tenant/dashboard.html`

```javascript
getChartOptions(gridColor, textColor) {
    const isGlassTheme = document.documentElement.classList.contains('glass-theme');
    return {
        // ...
        plugins: {
            tooltip: {
                backgroundColor: isGlassTheme ? 'rgba(30, 41, 59, 0.95)' : '#ffffff',
                titleColor: isGlassTheme ? '#f1f5f9' : '#1e293b',
                bodyColor: isGlassTheme ? '#cbd5e1' : '#64748b',
                borderColor: isGlassTheme ? 'rgba(255, 255, 255, 0.1)' : '#e2e8f0',
                borderWidth: 1,
                titleFont: { size: 13 },
                bodyFont: { size: 12 },
                padding: 12,
                cornerRadius: 8
            }
        }
        // ...
    };
}
```

### Boje po temi
| Property | Light Theme | Glass Theme |
|----------|-------------|-------------|
| Background | `#ffffff` | `rgba(30, 41, 59, 0.95)` |
| Title | `#1e293b` | `#f1f5f9` |
| Body | `#64748b` | `#cbd5e1` |
| Border | `#e2e8f0` | `rgba(255, 255, 255, 0.1)` |

---

## 6. Animation Performance Optimizations

### 6.1 Shimmer Animation (License Widget)

**Pre optimizacije:**
```css
.animate-shimmer {
    animation: shimmer 5s ease-in-out infinite;  /* Neprestano */
}
```

**Posle optimizacije:**
```css
.animate-shimmer {
    animation: shimmer 1.5s ease-in-out;  /* Jednom */
    width: 50%;
    will-change: transform;
}

/* Opciono: samo na hover */
.shimmer-on-hover .animate-shimmer {
    animation: none;
}
.shimmer-on-hover:hover .animate-shimmer {
    animation: shimmer 1s ease-in-out;
}
```

### 6.2 Fade-In Animation (bez layout shift)

**Pre:**
```css
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(-10px); }
    to { opacity: 1; transform: translateY(0); }
}
```

**Posle:**
```css
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
```

Uklonjen `translateY` jer je uzrokovao layout shift prilikom učitavanja.

### 6.3 Reduced Motion Support

```css
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
    html.theme-ready body {
        transition: none;
    }
}
```

Korisnici sa vestibularnim poremećajima mogu uključiti "Reduce motion" u OS settings, i sve animacije će biti instant.

### 6.4 Content Visibility

```css
.content-auto {
    content-visibility: auto;
    contain-intrinsic-size: 0 500px;
}
```

Za dugačke liste/stranice, browser neće renderovati offscreen sadržaj dok ne bude potreban.

---

## 7. Implementacione Smernice

### Kada dodati x-cloak?
- ✅ Root element sa `x-data`
- ✅ Elementi koji prikazuju dinamički sadržaj pre renderovanja
- ❌ Statički sadržaj (HTML bez Alpine bindinga)
- ❌ Unutar već zaštićenog x-cloak kontejnera

### Kada dodati loading skeleton?
- ✅ Stat kartice sa API podacima
- ✅ Tabele koje učitavaju podatke
- ✅ Forme koje čekaju inicijalne podatke
- ❌ Statički sadržaj (tekst, labele)
- ❌ Elementi koji se učitavaju instant

### Transition trajanja
| Kontekst | Trajanje | Easing |
|----------|----------|--------|
| Tab switch | 100-150ms | ease-out |
| Modal open | 200-300ms | ease-out |
| Modal close | 150-200ms | ease-in |
| Dropdown | 100ms | ease-out |
| Toast notification | 300ms | ease-out |

---

## 8. Testiranje

### Checklist za UI/UX review
- [ ] Nema FOUC pri učitavanju stranice
- [ ] Nema Alpine template bljeskanja
- [ ] Tab prelazi su smooth
- [ ] Loading stanja imaju skeleton
- [ ] Glass tema ima dobar kontrast
- [ ] Animacije rade sa "Reduce motion" uključenim
- [ ] Nema layout shift-a

### Browser DevTools
1. **Performance tab** - proveri FPS tokom animacija
2. **Network tab** - simuliraj slow network da vidiš loading stanja
3. **Rendering** - uključi "Paint flashing" da vidiš repaint-ove
4. **Accessibility** - proveri kontrast ratio

---

## 9. File Locations

| Komponenta | Fajl |
|------------|------|
| FOUC prevention | `app/templates/layouts/base.html` (line 38-45) |
| x-cloak CSS | `app/templates/layouts/base.html` (line 48) |
| Reduced motion | `app/templates/layouts/base.html` (line 61-72) |
| Shimmer animation | `app/templates/layouts/base.html` (line 80-96) |
| Glass theme CSS | `app/templates/layouts/base.html` (line 143-314) |
| Tenant x-cloak | `app/templates/layouts/tenant.html` (line 440) |
| Settings transitions | `app/templates/tenant/settings/index.html` |
| Dashboard skeletons | `app/templates/tenant/dashboard.html` (line 266-290) |
| Dashboard chart themes | `app/templates/tenant/dashboard.html` (line 769-798) |
| Tickets skeletons | `app/templates/tenant/tickets/list.html` |

---

## 10. Version History

### v164 (18. Januar 2026)
- Dashboard: Chart.js tooltip theming za Glass temu
- Dashboard: Loading skeleton za stat kartice
- Tickets: Loading skeleton za tabelu

### v163 (18. Januar 2026)
- Base: FOUC fix - opacity umesto visibility
- Base: Reduced motion media query
- Base: Shimmer optimization (jednom umesto infinite)
- Base: fadeIn bez translateY (nema layout shift)
- Tenant: x-cloak na root element
- Settings: x-transition na sve tabove (7 glavnih + 8 pod-tabova)

---

*Generisano: 18. Januar 2026*