(function () {
  var WIDE_PX = 76.25 * 16; // matches the 76.25em CSS breakpoint

  function positionSidenotes() {
    var sidenotes = document.querySelectorAll(".sidenote");
    if (!sidenotes.length) return;

    sidenotes.forEach(function (sn) {
      sn.style.top = "";
      sn.style.left = "";
      sn.style.width = "";
      sn.classList.remove("sidenote--wide");
    });

    if (window.innerWidth < WIDE_PX) return;

    var article = document.querySelector("article.md-content__inner");
    if (!article) return;

    // Blog posts integrate the ToC into the left meta sidebar (toc.integrate),
    // so their right margin is reserved for sidenotes via the
    // .md-content--sidenotes gutter (see sidenotes.css). On any page without
    // that reserved gutter the article is full-width, rightSpace is tiny, and
    // the check below cleanly falls back to inline block notes.
    var articleRect = article.getBoundingClientRect();
    var rightSpace = window.innerWidth - articleRect.right;
    if (rightSpace < 120) return;

    // Compute pixel positions so placement is independent of article width.
    // left is relative to the article's own left edge (positioned ancestor).
    var snLeft = articleRect.width + 56;
    var snWidth = Math.min(176, rightSpace - 72);

    sidenotes.forEach(function (sn) {
      sn.classList.add("sidenote--wide");
      sn.style.left = snLeft + "px";
      sn.style.width = snWidth + "px";
    });

    requestAnimationFrame(function () {
      var lastBottom = 0;
      var articleHeight = article.offsetHeight;
      sidenotes.forEach(function (sn) {
        var sup = document.getElementById(sn.dataset.refId);
        if (!sup) return;
        var top = Math.max(sup.offsetTop, lastBottom);
        // Don't let the sidenote overflow below the article boundary
        top = Math.min(top, articleHeight - sn.offsetHeight);
        sn.style.top = top + "px";
        lastBottom = top + sn.offsetHeight + 10;
      });
    });
  }

  function initSidenotes() {
    var footnoteSection = document.querySelector(".footnote");
    if (!footnoteSection) return;

    document.querySelectorAll("sup[id^='fnref']").forEach(function (sup) {
      var link = sup.querySelector("a[href]");
      if (!link) return;

      var targetId = link.getAttribute("href").slice(1);

      // Attribute selector — colon in "#fn:x" breaks CSS ID selectors
      var li = footnoteSection.querySelector("[id='" + targetId + "']");
      if (!li) return;

      // Extract innerHTML of each <p>, dropping the wrapper tag itself.
      // Keeping <p> inside a <span> (inline) causes browsers to restructure
      // the DOM and silently drop content.
      var parts = [];
      li.querySelectorAll("p").forEach(function (p) {
        var clone = p.cloneNode(true);
        // Match by class OR by href pattern — Material's tooltip feature can
        // mutate class lists, so the href fallback keeps removal reliable.
        var backref = clone.querySelector(".footnote-backref, a[href^='#fnref']");
        if (backref) {
          var prev = backref.previousSibling;
          if (prev && prev.nodeType === Node.TEXT_NODE) prev.remove();
          backref.remove();
        }
        var text = clone.innerHTML.trim();
        if (text) parts.push(text);
      });

      var content = parts.length ? parts.join(" ") : li.textContent.trim();
      var num = link.textContent.trim();

      var sidenote = document.createElement("span");
      sidenote.className = "sidenote";
      sidenote.dataset.refId = sup.id;
      sidenote.innerHTML =
        '<span class="sidenote-number">' + num + "</span> " + content;

      sup.after(sidenote);
    });

    var preceding = footnoteSection.previousElementSibling;
    if (preceding && preceding.tagName === "HR") preceding.remove();
    footnoteSection.remove();

    // Reserve the right-margin gutter only on blog posts that actually have
    // sidenotes, so note-less posts keep the full content width.
    if (document.querySelector(".sidenote")) {
      var postContent = document.querySelector(".md-content--post");
      if (postContent) postContent.classList.add("md-content--sidenotes");
    }

    positionSidenotes();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(initSidenotes);
  } else {
    document.addEventListener("DOMContentLoaded", initSidenotes);
  }

  window.addEventListener("resize", positionSidenotes);
})();
