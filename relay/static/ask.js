// Inputs for the secrets a request asks the user to type, shaped by what each one is:
// codes and CVCs as boxes (when the length is known), card numbers in groups of 4, expiry as
// MM/YY, passwords hidden with a Show toggle. Values live in the inputs only until sent.
const SPECS = {
  "one-time code": { label: "Code", numeric: true, ac: "one-time-code", min: 4, max: 10, letters: true },
  cvc: { label: "Security code (CVC)", numeric: true, ac: "cc-csc", min: 3, max: 4 },
  card_number: { label: "Card number", numeric: true, ac: "cc-number", min: 12, max: 19, group: true },
  expiry: { label: "Expiry", numeric: true, ac: "cc-exp", expiry: true },
  password: { label: "Password", ac: "current-password", password: true },
};
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids);
  return e;
};
const luhn = (d) => [...d].reverse().reduce((s, c, i) => {
  let n = +c * (i % 2 ? 2 : 1);
  return s + (n > 9 ? n - 9 : n);
}, 0) % 10 === 0;

function field(ask, onChange) {
  const sp = SPECS[ask.what] || { label: ask.what };
  const n = ask.length || null;
  let letters = false;
  const input = el("input", {
    autocomplete: sp.ac || "off", autocapitalize: "off", spellcheck: false, enterKeyHint: "done",
    type: sp.password ? "password" : "text", inputMode: sp.numeric ? "numeric" : "text",
  });
  input.setAttribute("autocorrect", "off");
  const max = n || sp.max || (sp.expiry ? 5 : 256);
  const boxes = n && n <= 10 && !sp.group && !sp.expiry && !sp.password;
  const row = boxes ? el("div", { className: "boxes" }, ...Array.from({ length: n }, () => el("span"))) : null;
  const note = el("p", { className: "small hint" });

  const clean = () => {
    let v = input.value;
    if (sp.expiry) {
      let d = v.replace(/\D/g, "").slice(0, 4);
      if (d.length === 1 && +d > 1) d = "0" + d;
      v = d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
    } else if (sp.group) {
      v = v.replace(/\D/g, "").slice(0, max).replace(/(\d{4})(?=\d)/g, "$1 ");
    } else if (sp.numeric && !letters) {
      v = v.replace(/\D/g, "").slice(0, max);
    } else if (sp.numeric) {
      v = v.replace(/[^0-9A-Za-z]/g, "").slice(0, max);
    }
    if (v !== input.value) input.value = v;
  };
  const value = () => (sp.group ? input.value.replace(/\D/g, "") : input.value);
  const valid = () => {
    const v = value();
    if (sp.password) return v.length > 0;
    if (sp.expiry) return /^(0[1-9]|1[0-2])\/\d{2}$/.test(v);
    if (n && !sp.group) return v.length === n;
    return v.length >= (sp.min || 1) && v.length <= max;
  };
  const render = () => {
    clean();
    const v = value();
    if (row) [...row.children].forEach((b, i) => {
      b.textContent = v[i] || "";
      b.classList.toggle("at", i === Math.min(v.length, n - 1) && document.activeElement === input);
    });
    if (sp.group) note.textContent = v.length < 12 ? `${v.length} digits` : luhn(v) ? "✓ number looks right" : "Check the number: it doesn't add up";
    else if (n && !boxes) note.textContent = `${v.length} / ${n}`;
    else if (!n && sp.min) note.textContent = `${sp.min}–${max} characters`;
    onChange();
  };
  input.addEventListener("input", render);
  input.addEventListener("focus", render);
  input.addEventListener("blur", render);

  const wrap = el("label", { className: "ask" }, el("span", { className: "label" }, sp.label));
  if (row) {
    input.maxLength = n;
    input.className = "overlay";
    const code = el("div", { className: "code" }, row, input);
    code.style.setProperty("--n", n);                   // sizes the tap area to the boxes
    wrap.append(code);
  } else {
    if (sp.numeric) input.className = "spaced";
    wrap.append(input);
  }
  const extras = el("div", { className: "extras" }, note);
  if (sp.password) extras.append(toggle("Show", "Hide", (on) => { input.type = on ? "text" : "password"; }));
  if (sp.letters) extras.append(toggle("Code has letters", "Digits only", (on) => {
    letters = on; input.inputMode = on ? "text" : "numeric"; input.blur(); input.focus(); render();
  }));
  wrap.append(extras);
  render();
  return { what: ask.what, el: wrap, input, valid, value, clear: () => { input.value = ""; render(); } };
}

function toggle(off, on, apply) {
  let state = false;
  const b = el("button", { type: "button", className: "link", textContent: off });
  b.onclick = (e) => { e.preventDefault(); state = !state; b.textContent = state ? on : off; apply(state); };
  return b;
}

// Builds the inputs for `asks` into `container`; onChange fires whenever validity may change.
export function build(container, asks, onChange) {
  const fields = (asks || []).map((a) => field(a, onChange));
  container.replaceChildren(...fields.map((f) => f.el));
  return {
    valid: () => fields.every((f) => f.valid()),
    values: () => Object.fromEntries(fields.map((f) => [f.what, f.value()])),
    clear: () => { fields.forEach((f) => f.clear()); container.replaceChildren(); },
    focus: () => fields[0]?.input.focus(),
  };
}
