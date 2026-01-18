# ServisHub Theme Specification

## Overview

ServisHub koristi **Dark Glassmorphic** dizajn sistem sa prozirnim elementima, blur efektima i gradient akcentima. Tema je inspirisana macOS dizajnom sa modernim tamnim UI stilom.

---

## Color Palette

### Primary Colors (Background)
| Naziv | Vrednost | Upotreba |
|-------|----------|----------|
| `bg-darkest` | `#000000` | Krajnji deo radial gradienta |
| `bg-dark` | `#020617` | Srednji deo radial gradienta (slate-950) |
| `bg-dark-secondary` | `#1f2937` | Početak radial gradienta (gray-800) |
| `bg-sidebar` | `rgba(15, 23, 42, 0.95)` | Sidebar pozadina |
| `bg-topbar` | `rgba(15, 23, 42, 0.9)` | Topbar pozadina |

### Background Gradient (Main App)
```css
background: radial-gradient(circle at top, #1f2937 0%, #020617 45%, #000 100%);
```

### Glassmorphic Surfaces
| Naziv | Vrednost | Upotreba |
|-------|----------|----------|
| `glass-bg` | `rgba(255, 255, 255, 0.08)` | Kartice, kontejneri |
| `glass-bg-light` | `rgba(255, 255, 255, 0.05)` | Tabele, sekcije |
| `glass-bg-subtle` | `rgba(255, 255, 255, 0.03)` | Table header, hover states |
| `glass-border` | `rgba(255, 255, 255, 0.1)` | Borderi |
| `glass-border-subtle` | `rgba(255, 255, 255, 0.05)` | Table row borders |

### Text Colors
| Naziv | HEX | RGB | Upotreba |
|-------|-----|-----|----------|
| `text-primary` | `#f1f5f9` | slate-100 | Glavni tekst, naslovi |
| `text-secondary` | `#cbd5e1` | slate-300 | Sekundarni tekst, opisi |
| `text-muted` | `#94a3b8` | slate-400 | Labele, meta tekst |
| `text-subtle` | `#64748b` | slate-500 | Placeholderi, sekcije |

### Accent Colors
| Naziv | HEX | RGBA (20% opacity) | Upotreba |
|-------|-----|---------------------|----------|
| `accent-blue` | `#60a5fa` | `rgba(59, 130, 246, 0.2)` | Linkovi, primary akcije |
| `accent-blue-hover` | `#93c5fd` | - | Link hover |
| `accent-green` | `#4ade80` | `rgba(34, 197, 94, 0.2)` | Uspeh, spremno |
| `accent-purple` | `#a78bfa` | `rgba(139, 92, 246, 0.2)` | Premium, čekanje |
| `accent-yellow` | `#facc15` | `rgba(234, 179, 8, 0.2)` | Upozorenje, pending |
| `accent-red` | `#f87171` | `rgba(239, 68, 68, 0.2)` | Greška, otkazano |
| `accent-orange` | `#fb923c` | `rgba(249, 115, 22, 0.2)` | Alert |

---

## Glassmorphic Effects

### Blur Effects
```css
backdrop-filter: blur(10px);  /* Kartice */
backdrop-filter: blur(20px);  /* Sidebar, Topbar, Modali */
backdrop-filter: blur(4px);   /* Mobile backdrop */
```

### Shadow Effects
```css
box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);        /* Kartice */
box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);  /* Primary buttons */
box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);  /* Primary buttons hover */
```

### Border Radius
```css
border-radius: 12px;   /* Kartice, kontejneri */
border-radius: 0.5rem; /* Dugmići (8px) */
border-radius: 9999px; /* Badges (pill shape) */
```

---

## Component Styles

### 1. Stat Cards
```css
.stat-card {
    background: rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 1.5rem;
    position: relative;
    overflow: hidden;
}

/* Color accent bar (left side) */
.stat-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
}
.stat-card.blue::before { background: linear-gradient(180deg, #3b82f6, #60a5fa); }
.stat-card.green::before { background: linear-gradient(180deg, #22c55e, #4ade80); }
.stat-card.purple::before { background: linear-gradient(180deg, #8b5cf6, #a78bfa); }
.stat-card.yellow::before { background: linear-gradient(180deg, #eab308, #facc15); }
```

### 2. Stat Icons
```css
.stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.stat-icon.blue { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
.stat-icon.green { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
.stat-icon.purple { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
.stat-icon.yellow { background: rgba(234, 179, 8, 0.2); color: #facc15; }
```

### 3. Glass Table Container
```css
.glass-table-container {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    overflow: hidden;
}

.glass-table-header {
    padding: 1rem 1.5rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.glass-table-header h3 {
    color: #f1f5f9;
    font-size: 1.125rem;
    font-weight: 600;
}
```

### 4. Glass Table
```css
.glass-table thead {
    background: rgba(255, 255, 255, 0.03);
}

.glass-table th {
    padding: 0.75rem 1.5rem;
    text-align: left;
    font-size: 0.75rem;
    font-weight: 500;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.glass-table tbody tr {
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    transition: background 0.2s;
}

.glass-table tbody tr:hover {
    background: rgba(255, 255, 255, 0.05);
}

.glass-table td {
    padding: 1rem 1.5rem;
    font-size: 0.875rem;
}

.glass-table .cell-primary { color: #f1f5f9; font-weight: 500; }
.glass-table .cell-secondary { color: #94a3b8; }
.glass-table .cell-link { color: #60a5fa; }
.glass-table .cell-link:hover { color: #93c5fd; }
```

### 5. Status Badges
```css
.status-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}

.status-received { background: rgba(234, 179, 8, 0.2); color: #facc15; }
.status-in-progress { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
.status-waiting { background: rgba(139, 92, 246, 0.2); color: #a78bfa; }
.status-ready { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
.status-delivered { background: rgba(107, 114, 128, 0.2); color: #9ca3af; }
.status-cancelled { background: rgba(239, 68, 68, 0.2); color: #f87171; }
```

### 6. Primary Button
```css
.btn-primary {
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-weight: 600;
    font-size: 0.875rem;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s;
    box-shadow: 0 4px 15px rgba(59, 130, 246, 0.3);
}

.btn-primary:hover {
    background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
}
```

### 7. Secondary Button
```css
.btn-secondary {
    background: rgba(255, 255, 255, 0.1);
    color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.15);
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-weight: 500;
    transition: all 0.2s;
}

.btn-secondary:hover {
    background: rgba(255, 255, 255, 0.15);
}
```

### 8. Form Inputs
```css
input, textarea, select {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #f1f5f9;
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
}

input::placeholder, textarea::placeholder {
    color: #64748b;
}

input:focus, textarea:focus, select:focus {
    border-color: rgba(96, 165, 250, 0.5);
    box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.15);
    outline: none;
}

select option {
    background: #1e293b;
    color: #f1f5f9;
}
```

### 9. Modal Dialog
```css
.modal-backdrop {
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(4px);
}

.modal-content {
    background: rgba(30, 41, 59, 0.95);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
}

.modal-header {
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    padding: 1rem 1.5rem;
}

.modal-title {
    color: #f1f5f9;
    font-size: 1.125rem;
    font-weight: 600;
}

.modal-close {
    color: #94a3b8;
}

.modal-close:hover {
    color: #f1f5f9;
}
```

### 10. Sidebar
```css
.sidebar-glass {
    background: rgba(15, 23, 42, 0.95);
    backdrop-filter: blur(20px);
    border-right: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-logo {
    color: #f1f5f9;
}

.nav-item {
    color: #94a3b8;
    transition: all 0.2s ease;
}

.nav-item:hover {
    color: #f1f5f9;
    background: rgba(255, 255, 255, 0.1);
}

.nav-item.active {
    color: #60a5fa;
    background: rgba(96, 165, 250, 0.15);
}

.nav-section-title {
    color: #64748b;
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
}
```

### 11. Topbar
```css
.topbar-glass {
    background: rgba(15, 23, 42, 0.9);
    backdrop-filter: blur(20px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.search-input {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #f1f5f9;
}

.search-input::placeholder {
    color: #64748b;
}

.search-input:focus {
    border-color: rgba(96, 165, 250, 0.5);
    box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.1);
}

.user-avatar {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
}

.user-dropdown {
    background: rgba(15, 23, 42, 0.98);
    border: 1px solid rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(20px);
}
```

---

## Subscription Badges
```css
.sub-badge-demo { background: rgba(147, 51, 234, 0.2); color: #c084fc; }
.sub-badge-trial { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
.sub-badge-active { background: rgba(34, 197, 94, 0.2); color: #4ade80; }
.sub-badge-expired { background: rgba(234, 179, 8, 0.2); color: #facc15; }
.sub-badge-suspended { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.sub-badge-cancelled { background: rgba(107, 114, 128, 0.2); color: #9ca3af; }
```

---

## Tailwind Class Overrides

Ovi stilovi automatski konvertuju standardne Tailwind klase u dark temu:

```css
/* bg-white -> glass effect */
.tenant-app .bg-white {
    background: rgba(255, 255, 255, 0.08) !important;
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
}

/* Text colors */
.tenant-app .text-gray-900, .text-gray-800 { color: #f1f5f9 !important; }
.tenant-app .text-gray-700, .text-gray-600 { color: #cbd5e1 !important; }
.tenant-app .text-gray-500, .text-gray-400 { color: #94a3b8 !important; }

/* Borders */
.tenant-app .border-gray-200, .border-gray-300 {
    border-color: rgba(255, 255, 255, 0.1) !important;
}

/* Shadows */
.tenant-app .shadow, .shadow-sm, .shadow-md, .shadow-lg {
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3) !important;
}

/* Primary colors */
.tenant-app .text-primary-600 { color: #60a5fa !important; }
.tenant-app .bg-primary-600 {
    background: linear-gradient(135deg, #3b82f6, #8b5cf6) !important;
}
```

---

## Transitions

Sve interaktivne elemente koriste:
```css
transition: all 0.2s ease;
```

---

## File Locations

- **Global theme**: `app/templates/layouts/tenant.html` (linija 4-309)
- **Dashboard components**: `app/templates/tenant/dashboard.html` (linija 6-168)
- **Tickets list**: `app/templates/tenant/tickets/list.html`

---

## Design Principles

1. **Glassmorphism**: Svi elementi koriste providne pozadine sa blur efektom
2. **Gradient Accents**: Primary dugmići i accent elementi koriste blue-to-purple gradient
3. **Subtle Borders**: Borderi su uvek rgba(255,255,255,0.1) za suptilno razdvajanje
4. **Consistent Spacing**: Kartice imaju padding 1.5rem, tabele 1rem-1.5rem
5. **Color Coding**: Svaki status ima svoju boju (blue=active, green=success, yellow=pending, red=error)
6. **Hover States**: Elementi imaju hover state sa povećanom providnošću ili transformacijom

---

## Performance & Animations

Za detalje o UI/UX performance optimizacijama (FOUC prevention, loading skeletons, transitions, reduced motion), pogledaj:

**[UI_UX_PERFORMANCE.md](./UI_UX_PERFORMANCE.md)**

### Quick Reference

| Tehnika | Fajl | Opis |
|---------|------|------|
| FOUC Prevention | `base.html` | opacity transition umesto visibility |
| x-cloak | sve stranice | skriva Alpine elemente do init |
| Tab Transitions | `settings/index.html` | 100-150ms ease-out |
| Loading Skeletons | `dashboard.html`, `list.html` | animirani placeholder |
| Reduced Motion | `base.html` | podrška za accessibility |

---

## Version History

- **v164**: UI/UX Performance optimizacije - FOUC fix, skeletons, transitions
- **v128**: Complete dark glassmorphic theme implementation
- Global theme auto-converts Tailwind classes to dark equivalents
- All tenant pages use consistent styling