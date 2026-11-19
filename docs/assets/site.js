/* Scroll behaviour for the AppSweep page.
 *
 * Sections arrive once when they reach the fold. That is all: the page's
 * argument is the application's own screens, and they are better looked at
 * than animated around.
 *
 * Everything is additive. The hidden starting state is only applied once
 * GSAP has actually loaded, so a visitor without it — or with "reduce
 * motion" on — gets the whole page, just without the movement.
 */
(function () {
  "use strict";

  var gsap = window.gsap;
  var ScrollTrigger = window.ScrollTrigger;
  if (!gsap || !ScrollTrigger) return;

  gsap.registerPlugin(ScrollTrigger);
  document.documentElement.classList.add("js-anim");

  /* Hiding content and then relying on an animation frame to bring it back
     is a bet. If the frame loop never runs — a throttled background tab, a
     browser that suspends it — the page would simply be missing its text.
     So: if no frame has been drawn shortly after load, undo the hiding and
     leave the page static. */
  setTimeout(function () {
    if (gsap.ticker.frame > 0) return;
    document.documentElement.classList.remove("js-anim");
    gsap.set(".reveal", { clearProps: "opacity,transform" });
  }, 2500);

  var mm = gsap.matchMedia();

  mm.add(
    {
      motion: "(prefers-reduced-motion: no-preference)",
      still: "(prefers-reduced-motion: reduce)"
    },
    function (context) {
      var still = context.conditions.still;

      if (still) {
        // Everything in place, no movement.
        gsap.set(".reveal", { opacity: 1, y: 0 });
        return;
      }

      // --- sections arrive once -------------------------------------
      gsap.utils.toArray(".reveal").forEach(function (el) {
        gsap.to(el, {
          opacity: 1,
          y: 0,
          duration: 0.55,
          ease: "power2.out",
          scrollTrigger: { trigger: el, start: "top 97%", once: true }
        });
      });

      // Cards have a little weight: they land and settle, led by the first.
      gsap.utils.toArray(".grid").forEach(function (grid) {
        gsap.from(grid.children, {
          opacity: 0,
          y: 26,
          duration: 0.6,
          ease: "back.out(1.4)",
          stagger: 0.06,
          scrollTrigger: { trigger: grid, start: "top 92%", once: true }
        });
      });

    }
  );
})();
