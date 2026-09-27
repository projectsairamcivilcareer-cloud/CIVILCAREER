(() => {
  const datePattern = /\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b/g;
  const formatText = (text) => text.replace(datePattern, (match, yyyy, mm, dd, hh, min) => {
    const date = `${dd}-${mm}-${yyyy}`;
    return hh === undefined ? date : `${date} ${hh}:${min}`;
  });
  const excluded = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "INPUT", "CODE", "PRE"]);
  const processNode = (root) => {
    if (!root) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (!parent || excluded.has(parent.tagName) || parent.closest("[data-keep-iso]")) return NodeFilter.FILTER_REJECT;
        datePattern.lastIndex = 0;
        return datePattern.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_SKIP;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      datePattern.lastIndex = 0;
      node.nodeValue = formatText(node.nodeValue);
    });
  };
  document.addEventListener("DOMContentLoaded", () => processNode(document.body));
  if (document.readyState !== "loading") processNode(document.body);
  const observer = new MutationObserver(records => {
    records.forEach(record => {
      record.addedNodes.forEach(node => {
        if (node.nodeType === Node.TEXT_NODE) {
          if (node.parentElement && !excluded.has(node.parentElement.tagName)) {
            datePattern.lastIndex = 0;
            if (datePattern.test(node.nodeValue)) {
              datePattern.lastIndex = 0;
              node.nodeValue = formatText(node.nodeValue);
            }
          } else if (node.nodeType === Node.ELEMENT_NODE) processNode(node);
        } else if (node.nodeType === Node.ELEMENT_NODE) processNode(node);
      });
    });
  });
  if (document.documentElement) observer.observe(document.documentElement, { childList: true, subtree: true });
})();