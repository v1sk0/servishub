# ServisHub Premium Animations Guide

## Overview

Kolekcija vrhunskih CSS animacija za moderan, profesionalan UI. Sve animacije su optimizovane za performanse i poštuju `prefers-reduced-motion` za accessibility.

## Quick Start

```html
<!-- Include CSS file -->
<link rel="stylesheet" href="/static/css/premium-animations.css">

<!-- Or include in Jinja template -->
{% block head %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/premium-animations.css') }}">
{% endblock %}
```

---

## 1. Entrance Animations

### Fade In Up
Element se pojavljuje odozdo sa fade efektom.

```html
<div class="animate-fade-in-up">
    Content appears from below
</div>
```

### Fade In Down
```html
<div class="animate-fade-in-down">Content from above</div>
```

### Fade In Left / Right
```html
<div class="animate-fade-in-left">From left</div>
<div class="animate-fade-in-right">From right</div>
```

### Scale In
Element se pojavljuje sa scale efektom (0.9 → 1).

```html
<div class="animate-scale-in">
    Scales into view
</div>
```

### Card Entrance
Specijalno za glass cards - kombinacija translateY i scale.

```html
<div class="glass-card animate-card-entrance">
    Premium card content
</div>
```

### Logo Entrance
Sa rotacijom i bounce efektom.

```html
<img src="logo.svg" class="animate-logo-entrance">
```

---

## 2. Stagger Animations (Kaskadno)

Deca elementa se pojavljuju jedan za drugim sa delay-om.

```html
<div class="stagger-children">
    <div>Appears first (0.05s)</div>
    <div>Appears second (0.1s)</div>
    <div>Appears third (0.15s)</div>
    <div>Appears fourth (0.2s)</div>
    <!-- ... up to 10 children supported -->
</div>
```

**Use cases:**
- Liste stavki
- Form polja
- Grid kartice
- Navigation items

---

## 3. Interactive Animations

### Input Glow
Ljubičasti glow efekat na focus.

```html
<input type="text" class="input-glow" placeholder="Focus me">
```

### Button Ripple
Radijalni talas efekat na hover.

```html
<button class="btn-ripple">
    Hover for ripple effect
</button>
```

### Hover Lift
Podizanje elementa sa shadow na hover.

```html
<div class="hover-lift">
    Lifts up on hover
</div>
```

### Hover Glow
Glow efekat na hover.

```html
<div class="hover-glow">
    Glows on hover
</div>
```

### Hover Scale
Scale efekat na hover.

```html
<div class="hover-scale">
    Scales on hover
</div>
```

### Kombinacija hover efekata
```html
<div class="hover-lift hover-glow">
    Premium hover effect
</div>
```

---

## 4. Continuous Animations

### Pulse Glow
Kontinuirano pulsiranje glow-a (za attention).

```html
<div class="pulse-glow">
    Important element
</div>
```

### Float
Lagano lebdenje gore-dole.

```html
<span class="animate-float">
    Floating badge
</span>
```

### Shimmer
Svetlucanje (za promo elemente).

```html
<div class="animate-shimmer">
    Special offer!
</div>
```

### Spin
Rotacija (za loadere).

```html
<svg class="animate-spin" viewBox="0 0 24 24">
    <!-- spinner icon -->
</svg>
```

### Bounce
Bounce efekat (za notification badges).

```html
<span class="animate-bounce">3</span>
```

---

## 5. Success/Status Animations

### Checkmark Draw
Animirano crtanje kvačice.

```html
<svg viewBox="0 0 24 24">
    <path class="animate-check"
          stroke="currentColor"
          stroke-width="2"
          fill="none"
          d="M5 13l4 4L19 7"/>
</svg>
```

### Success Pulse
Zeleni pulse za uspešne akcije.

```html
<div class="animate-success-pulse">
    Success!
</div>
```

### Error Shake
Tresenje za greške.

```html
<input class="animate-error-shake" value="Invalid">
```

---

## 6. Background Animations

### Gradient Orb
Animirani blur gradient.

```css
.my-page::before {
    content: '';
    position: fixed;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, #8b5cf6 0%, transparent 70%);
    top: -200px;
    right: -100px;
}

/* Add animation class */
.my-page::before {
    @extend .gradient-orb;
}
```

---

## 7. Utility Classes

### Animation Delay
```html
<div class="animate-fade-in-up delay-100">100ms delay</div>
<div class="animate-fade-in-up delay-200">200ms delay</div>
<div class="animate-fade-in-up delay-300">300ms delay</div>
<div class="animate-fade-in-up delay-500">500ms delay</div>
<div class="animate-fade-in-up delay-1000">1s delay</div>
```

### Animation Duration
```html
<div class="animate-scale-in duration-fast">Fast (0.2s)</div>
<div class="animate-scale-in duration-normal">Normal (0.4s)</div>
<div class="animate-scale-in duration-slow">Slow (0.6s)</div>
<div class="animate-scale-in duration-slower">Slower (1s)</div>
```

### Smooth Transitions
```html
<div class="smooth-all">
    All properties transition smoothly
</div>
```

---

## 8. CSS Variables

Animacije koriste sledeće CSS varijable (definisati u `:root`):

```css
:root {
    --sh-accent-purple: #8b5cf6;
    --sh-accent-indigo: #6366f1;
    --sh-glow-purple: rgba(139, 92, 246, 0.4);
    --sh-success: #10b981;
    --sh-error: #ef4444;
}
```

---

## 9. Alpine.js Integration

Za dinamičke animacije sa Alpine.js:

```html
<!-- Trigger on show -->
<div x-show="isVisible"
     x-transition:enter="animate-fade-in-up"
     x-transition:enter-start="opacity-0"
     x-transition:enter-end="opacity-100">
    Content
</div>

<!-- Trigger on condition change -->
<div :class="{ 'animate-success-pulse': success, 'animate-error-shake': error }">
    Status
</div>

<!-- Step transitions -->
<div x-show="step === 1" class="animate-fade-in-right">
    Step 1 content
</div>
```

---

## 10. Best Practices

### Performance
- Koristi `transform` i `opacity` za animacije (GPU accelerated)
- Izbegavaj animiranje `width`, `height`, `top`, `left`
- Koristi `will-change` samo kad je potrebno

### Accessibility
- CSS automatski disabluje animacije za `prefers-reduced-motion: reduce`
- Ne oslanjaj se samo na animacije za feedback
- Obezbedi alternative za važne informacije

### UX Guidelines
- **Entrance animations**: 0.3s - 0.6s
- **Hover effects**: 0.2s - 0.3s
- **Continuous animations**: Koristi sparingly
- **Stagger delay**: 0.05s - 0.1s između elemenata

---

## 11. Complete Example

```html
<div class="register-page">
    <!-- Background orbs -->
    <div class="gradient-orb" style="top: -200px; right: -100px;"></div>

    <!-- Main card -->
    <div class="glass-card animate-card-entrance">
        <!-- Logo -->
        <div class="logo animate-logo-entrance pulse-glow">
            <img src="logo.svg">
        </div>

        <!-- Title -->
        <h1 class="animate-fade-in-up delay-200">Welcome</h1>

        <!-- Form -->
        <form class="stagger-children">
            <div class="form-group">
                <input type="text" class="input-glow" placeholder="Name">
            </div>
            <div class="form-group">
                <input type="email" class="input-glow" placeholder="Email">
            </div>
            <button class="btn-ripple hover-lift">
                Submit
            </button>
        </form>

        <!-- Promo -->
        <div class="promo-badge animate-float animate-shimmer">
            Special offer!
        </div>
    </div>

    <!-- Footer -->
    <footer class="animate-fade-in-up delay-500">
        <a href="#" class="hover-lift hover-glow">
            Powered by ServisHub.rs
        </a>
    </footer>
</div>
```

---

## 12. Success Celebration Overlay

Premium celebration komponenta sa confetti, fireworks i sparkle efektima. Koristi se za važne uspešne akcije (registracija, velika kupovina, milestone).

### HTML Structure

```html
<!-- Success Celebration Overlay -->
<div id="successOverlay" class="success-overlay">
    <div class="fireworks-container" id="fireworksContainer"></div>
    <canvas class="confetti-canvas" id="confettiCanvas"></canvas>

    <div class="success-card">
        <div class="success-checkmark">
            <div class="success-checkmark-circle">
                <svg class="success-checkmark-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
            </div>
        </div>

        <h2 class="success-title">Naslov uspešne akcije!</h2>
        <p class="success-subtitle">Podnaslov sa detaljima</p>

        <div class="success-promo-badge">
            <svg style="width: 24px; height: 24px;" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v13m0-13V6a2 2 0 112 2h-2zm0 0V5.5A2.5 2.5 0 109.5 8H12zm-7 4h14M5 12a2 2 0 110-4h14a2 2 0 110 4M5 12v7a2 2 0 002 2h10a2 2 0 002-2v-7" />
            </svg>
            Promo tekst!
        </div>

        <p class="success-redirect">
            Preusmeravanje za <span id="redirectCountdown">5</span> sekundi...
        </p>
    </div>
</div>
```

### JavaScript Functions

```javascript
// Pokreni celebration (poziva sve efekte)
showSuccessCelebration();

// Pojedinačni efekti (mogu se koristiti zasebno)
startConfetti();      // Confetti padaju sa vrha
startFireworks();     // Fireworks eksplozije
startSparkles();      // Sparkle zvezde
```

### Testiranje

Za testiranje bez prolaska kroz ceo flow, otvori browser console (F12) i ukucaj:

```javascript
showSuccessCelebration()
```

### Komponente

| Komponenta | Opis | Trajanje |
|------------|------|----------|
| `success-overlay` | Glassmorphism pozadina sa blur | - |
| `success-card` | Glavni card sa scale animacijom | 0.6s |
| `success-checkmark` | Animirana kvačica sa pulse ringovima | 0.6s + infinite pulse |
| `success-promo-badge` | Badge sa glow animacijom | infinite glow |
| `confetti-canvas` | Canvas sa 150 confetti čestica | 6s |
| `fireworks-container` | 15 firework eksplozija | 6s |
| `sparkles` | 30 sparkle zvezda | 6s |

### Boje

Confetti i fireworks koriste sledeću paletu:
```javascript
const colors = ['#8b5cf6', '#6366f1', '#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#ffffff'];
```

### Customization

```javascript
// Promena countdown vremena
let countdown = 10; // 10 sekundi umesto 5

// Promena broja confetti čestica
for (let i = 0; i < 200; i++) { // 200 umesto 150

// Promena broja fireworks
const maxFireworks = 20; // 20 umesto 15

// Promena redirect URL-a
window.location.href = '/dashboard'; // umesto /login
```

### Use Cases

- Uspešna registracija korisnika
- Uspešna kupovina / plaćanje
- Dostignuće milestone-a
- Završetak onboarding-a
- Osvajanje nagrade

---

## File Locations

```
app/static/css/premium-animations.css     - Reusable animation classes
app/templates/tenant/register.html        - Success celebration implementation
```

## Version

1.1.0 - Added Success Celebration Overlay
1.0.0 - Initial release