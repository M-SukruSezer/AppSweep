/* Scroll behaviour for the AppSweep page.
 *
 * Two things happen here. Sections arrive once when they reach the fold,
 * and one scroll-driven sequence tells the product's own story: an
 * application is lifted away, and what it leaves behind is still there.
 * That is the same idea the application icon carries, at page scale.
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
    gsap.set(".caption span", { opacity: 1, position: "relative" });
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
        // Everything in place, no movement; the three captions become an
        // ordinary stack so the sequence can still be read.
        gsap.set(".reveal", { opacity: 1, y: 0 });
        gsap.set(".tile", { opacity: 1, y: "-30%", x: "22%", scale: 0.8 });
        gsap.set(".footprint, .speck", { opacity: 1 });
        gsap.set(".caption span", { opacity: 1, position: "relative" });
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

      // --- the scroll-driven sequence -------------------------------
      var stage = document.querySelector(".stage");
      if (!stage) return;

      var caps = gsap.utils.toArray(".caption span");
      // The stage is already held in place by CSS sticky, so the library
      // only has to map scroll position onto the timeline.
      var tl = gsap.timeline({
        scrollTrigger: {
          trigger: ".stage-outer",
          start: "top top",
          end: "bottom bottom",
          scrub: 0.6
        }
      });

      // 1. the application is lifted away
      tl.to(".tile", {
        y: "-38%", x: "26%", scale: 0.76, rotate: 7,
        ease: "power1.inOut", duration: 1.2
      })
        .to(".tile", { opacity: 0, duration: 0.5 }, "-=0.35")
        // 2. what it leaves is already there
        .to(".footprint", { opacity: 1, duration: 0.6 }, "-=0.9")
        .to(".speck", { opacity: 1, stagger: 0.12, duration: 0.4 }, "-=0.45")
        .to(caps[0], { opacity: 0, duration: 0.3 }, "-=0.3")
        .to(caps[1], { opacity: 1, duration: 0.4 })
        // a beat of stillness, so the second line can be read
        .to({}, { duration: 0.7 })
        // 3. AppSweep clears it
        .to(".speck", {
          opacity: 0, scale: 0.2, stagger: 0.1, duration: 0.4,
          ease: "power2.in"
        })
        .to(".footprint", {
          borderColor: "rgba(46,194,126,.9)", borderStyle: "solid",
          duration: 0.5
        }, "-=0.5")
        .to(caps[1], { opacity: 0, duration: 0.3 }, "-=0.4")
        .to(caps[2], { opacity: 1, duration: 0.4 })
        .to({}, { duration: 0.6 });
    }
  );
})();
