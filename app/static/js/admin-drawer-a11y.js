document.addEventListener("DOMContentLoaded", () => {
  const drawer = document.getElementById("admin-drawer");

  if (!drawer) {
    return;
  }

  const openMotionClasses = [
    "motion-safe:animate-in",
    "motion-safe:fade-in-0",
    "motion-safe:slide-in-from-right-8",
    "motion-safe:duration-300",
  ];

  let wasClosed = null;

  const syncDrawerAccessibility = () => {
    const isClosed = drawer.classList.contains("translate-x-full");

    drawer.toggleAttribute("inert", isClosed);
    drawer.setAttribute("aria-hidden", isClosed ? "true" : "false");

    if (wasClosed === isClosed) {
      return;
    }

    wasClosed = isClosed;

    if (isClosed) {
      drawer.classList.remove(...openMotionClasses);
      return;
    }

    drawer.classList.remove(...openMotionClasses);
    void drawer.offsetWidth;
    drawer.classList.add(...openMotionClasses);
  };

  syncDrawerAccessibility();

  const observer = new MutationObserver(syncDrawerAccessibility);
  observer.observe(drawer, {
    attributes: true,
    attributeFilter: ["class"],
  });
});
