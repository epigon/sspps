/**
 * BackToTop Utility
 * -----------------
 * Usage:
 *   BackToTop.init({
 *     buttonId: 'backToTop',
 *     scrollContainer: '.content',
 *     threshold: 200
 *   });
 */

window.BackToTop = (function () {
    function init({
        buttonId = "backToTop",
        scrollContainer = window,
        threshold = 200
    } = {}) {

        const btn = document.getElementById(buttonId);
        if (!btn) {
            console.warn("BackToTop: button not found");
            return;
        }

        const container =
            typeof scrollContainer === "string"
                ? document.querySelector(scrollContainer)
                : scrollContainer;

        if (!container) {
            console.warn("BackToTop: scroll container not found");
            return;
        }

        const getScrollTop = () =>
            container === window
                ? window.scrollY
                : container.scrollTop;

        const scrollToTop = () => {
            if (container === window) {
                window.scrollTo({ top: 0, behavior: "smooth" });
            } else {
                container.scrollTo({ top: 0, behavior: "smooth" });
            }
        };

        const onScroll = () => {
            btn.classList.toggle("show", getScrollTop() > threshold);
        };

        container.addEventListener("scroll", onScroll);
        btn.addEventListener("click", scrollToTop);

        // Initial state check
        onScroll();
    }

    return { init };
})();
