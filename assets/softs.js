// Sugar and coffee sections. Until each commodity's full tab set is built, show the existing desk page in a frame.
const Softs = (() => {
  const LEGACY = { sugar: 'sugar.html', coffee: 'coffee.html' };
  const built = {};
  function show(k) {
    const el = document.getElementById(k);
    if (window[k === 'sugar' ? 'Sugar' : 'Coffee'] && window[k === 'sugar' ? 'Sugar' : 'Coffee'].show) return window[k === 'sugar' ? 'Sugar' : 'Coffee'].show();
    if (!built[k]) {
      el.style.padding = '0';
      el.innerHTML = `<iframe title="${k}" src="${LEGACY[k]}" style="display:block;width:100%;height:calc(100vh - 92px);min-height:640px;border:0"></iframe>`;
      built[k] = 1;
    }
    history.replaceState(null, '', k === 'sugar' ? '#su' : '#kc');
  }
  return { show };
})();
