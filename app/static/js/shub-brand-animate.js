/**
 * Shub Brand Animation
 *
 * Animates "ServisHub" text from center outward, then contracts to "SHub"
 *
 * Sequence:
 * 1. Start from middle: sH
 * 2. Expand outward: isHu → visHub → rvisHub → ervisHub → ServisHub
 * 3. Pause at full text
 * 4. Contract to: SHub (and stay)
 *
 * Usage:
 * <span class="shub-brand-animate" data-shub-animate>ServisHub</span>
 *
 * Options (data attributes):
 * - data-shub-delay="1000" - Initial delay before animation starts (ms)
 * - data-shub-expand-speed="100" - Speed of expansion per character (ms)
 * - data-shub-pause="1500" - Pause duration at full text (ms)
 * - data-shub-contract-speed="80" - Speed of contraction per character (ms)
 * - data-shub-final="Shub" - Final text to display
 * - data-shub-loop="false" - Whether to loop the animation
 */

(function() {
    'use strict';

    const FULL_TEXT = 'ServisHub';
    const FINAL_TEXT = 'SHub';

    // Expansion sequence (from center outward)
    // ServisHub = S e r v i s H u b
    //             0 1 2 3 4 5 6 7 8
    // Center is between 's' (5) and 'H' (6) -> "sH"
    const EXPAND_SEQUENCE = [
        'sH',        // Start - center
        'isHu',      // +1 each side
        'visHub',    // +1 each side
        'rvisHub',   // +1 left only (right is done)
        'ervisHub',  // +1 left
        'ServisHub'  // Full text
    ];

    // Contract sequence (to final "SHub")
    // ServisHub → SHub (keep S, remove ervi, keep Hub)
    const CONTRACT_SEQUENCE = [
        'ServisHub',
        'SrvisHub',   // Remove 'e'
        'SvisHub',    // Remove 'r'
        'SisHub',     // Remove 'v'
        'SsHub',      // Remove 'i'
        'SHub'        // Remove 's' - final!
    ];

    class ShubBrandAnimate {
        constructor(element) {
            this.element = element;
            this.options = {
                delay: parseInt(element.dataset.shubDelay) || 300,
                expandSpeed: parseInt(element.dataset.shubExpandSpeed) || 50,
                pause: parseInt(element.dataset.shubPause) || 800,
                contractSpeed: parseInt(element.dataset.shubContractSpeed) || 40,
                finalText: element.dataset.shubFinal || FINAL_TEXT,
                loop: element.dataset.shubLoop === 'true'
            };

            this.originalText = element.textContent.trim();
            this.init();
        }

        init() {
            // Measure the full text width first to prevent layout shift
            const tempSpan = document.createElement('span');
            tempSpan.style.visibility = 'hidden';
            tempSpan.style.position = 'absolute';
            tempSpan.style.whiteSpace = 'nowrap';
            tempSpan.textContent = FULL_TEXT;
            tempSpan.style.font = window.getComputedStyle(this.element).font;
            document.body.appendChild(tempSpan);
            const fullWidth = tempSpan.offsetWidth;
            document.body.removeChild(tempSpan);

            // Set minimum width to prevent layout shift
            this.element.style.minWidth = fullWidth + 'px';
            this.element.style.display = 'inline-block';

            // Set initial state (hidden)
            this.element.innerHTML = '';
            this.element.classList.add('animating');

            // Start animation after delay
            setTimeout(() => this.runAnimation(), this.options.delay);
        }

        renderText(text, highlightNew = false, prevText = '') {
            this.element.innerHTML = '';

            const chars = text.split('');
            const prevChars = prevText.split('');

            chars.forEach((char, index) => {
                const span = document.createElement('span');
                span.className = 'shub-char visible';
                span.textContent = char;

                // Highlight newly added characters
                if (highlightNew && !prevChars.includes(char) && prevChars.length > 0) {
                    span.classList.add('highlight');
                    // Remove highlight after a moment
                    setTimeout(() => span.classList.remove('highlight'), 200);
                }

                this.element.appendChild(span);
            });
        }

        async runAnimation() {
            // Phase 1: Expand from center
            let prevText = '';
            for (const text of EXPAND_SEQUENCE) {
                this.renderText(text, true, prevText);
                prevText = text;
                await this.sleep(this.options.expandSpeed);
            }

            // Phase 2: Pause at full text
            await this.sleep(this.options.pause);

            // Phase 3: Contract to final
            for (const text of CONTRACT_SEQUENCE) {
                this.renderText(text, false);
                await this.sleep(this.options.contractSpeed);
            }

            // Final state
            this.element.classList.remove('animating');
            this.element.classList.add('final');

            // Loop if enabled
            if (this.options.loop) {
                await this.sleep(3000);
                this.element.classList.remove('final');
                this.init();
            }
        }

        sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }
    }

    // Auto-initialize on DOM ready
    function initShubAnimations() {
        document.querySelectorAll('[data-shub-animate]').forEach(el => {
            // Skip if already initialized
            if (el.dataset.shubInitialized) return;
            el.dataset.shubInitialized = 'true';
            new ShubBrandAnimate(el);
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShubAnimations);
    } else {
        initShubAnimations();
    }

    // Also observe for dynamically added elements
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (node.nodeType === 1) {
                    if (node.hasAttribute('data-shub-animate')) {
                        if (!node.dataset.shubInitialized) {
                            node.dataset.shubInitialized = 'true';
                            new ShubBrandAnimate(node);
                        }
                    }
                    node.querySelectorAll?.('[data-shub-animate]').forEach(el => {
                        if (!el.dataset.shubInitialized) {
                            el.dataset.shubInitialized = 'true';
                            new ShubBrandAnimate(el);
                        }
                    });
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Expose globally for manual initialization
    window.ShubBrandAnimate = ShubBrandAnimate;
    window.initShubAnimations = initShubAnimations;
})();
