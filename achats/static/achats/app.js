/* =========================================================================
   Achats du jour — interface temps réel (Tailwind CSS + icônes Lucide)
   - filtres, marquage quotidien et prix envoyés par une API JSON
   - la page est régulièrement re-synchronisée avec le serveur (polling),
     donc toute modification faite ailleurs apparaît sans rechargement.
   - les articles sont groupés par catégorie.
   ========================================================================= */
(() => {
  "use strict";

  const CFG = window.APP_CONFIG || { currency: "Ar", poll: 5 };
  const $ = (sel, root = document) => root.querySelector(sel);

  /* ---------------------------------------------------------------- État */
  const state = {
    date: "",
    q: "",
    category: "",
    status: "",
    min_price: "",
    max_price: "",
    ordering: "name",
    inactive: false,
  };

  let articlesById = new Map();
  let currentCategories = [];
  let lastDataKey = null;
  /** Suppression en attente de confirmation dans la modale. */
  let pendingDelete = null;

  /* ------------------------------------------------------------- Références */
  const els = {
    list: $("#list"),
    history: $("#history"),
    dateInput: $("#date-input"),
    dayTitle: $("#day-title"),
    resultInfo: $("#result-info"),
    toasts: $("#toasts"),
    modal: $("#modal"),
    form: $("#article-form"),
    formError: $("#form-error"),
    catModal: $("#cat-modal"),
    catForm: $("#cat-form"),
    confirmModal: $("#confirm-modal"),
    confirmForm: $("#confirm-form"),
    confirmTitle: $("#confirm-title"),
    confirmMessage: $("#confirm-message"),
    catName: $("#cat-name"),
    catError: $("#cat-error"),
    filters: {
      q: $("#f-q"),
      category: $("#f-category"),
      status: $("#f-status"),
      min: $("#f-min"),
      max: $("#f-max"),
      order: $("#f-order"),
      inactive: $("#f-inactive"),
    },
    sum: {
      count: $("#sum-count"),
      active: $("#sum-active"),
      todo: $("#sum-todo"),
      done: $("#sum-done"),
      planned: $("#sum-planned"),
      spent: $("#sum-spent"),
      remaining: $("#sum-remaining"),
    },
    article: {
      id: $("#a-id"),
      name: $("#a-name"),
      price: $("#a-price"),
      unit: $("#a-unit"),
      category: $("#a-category"),
      newCategory: $("#a-new-category"),
      active: $("#a-active"),
      title: $("#modal-title"),
    },
  };

  /* ------------------------------------------------------------ Utilitaires */
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const nf = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
  const fmt = (v) => nf.format(Number(v) || 0);
  const money = (v) => `${fmt(v)} ${CFG.currency}`.trim();

  /** Rend (ou rend à nouveau) les icônes Lucide du document. */
  function icons() {
    if (!window.lucide) return;
    try {
      window.lucide.createIcons();
    } catch (_) {
      /* CDN indisponible : la page reste utilisable */
    }
  }

  /** Saisie libre → nombre : « 1 200 », « 1200,50 », « 1.200 »… */
  function parseNum(v) {
    if (v === null || v === undefined) return NaN;
    let s = String(v).replace(/[\s\u202f\u00a0]/g, "");
    if (!s) return NaN;
    const hasC = s.includes(","), hasD = s.includes(".");
    if (hasC && hasD) {
      s = s.lastIndexOf(",") > s.lastIndexOf(".")
        ? s.replace(/\./g, "").replace(",", ".")
        : s.replace(/,/g, "");
    } else if (hasC) {
      s = s.replace(",", ".");
    } else if (/^\d{1,3}(\.\d{3})+$/.test(s)) {
      s = s.replace(/\./g, "");
    }
    const n = parseFloat(s);
    return Number.isNaN(n) ? NaN : n;
  }

  function localToday() {
    return iso(new Date());
  }
  function iso(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
      d.getDate()
    ).padStart(2, "0")}`;
  }
  function shiftDate(isoStr, days) {
    const [y, m, d] = isoStr.split("-").map(Number);
    return iso(new Date(y, m - 1, d + days));
  }
  function dayLabel(isoStr, opts) {
    const [y, m, d] = isoStr.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("fr-FR", opts);
  }

  function getCookie(name) {
    const m = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)")
    );
    return m ? decodeURIComponent(m[1]) : null;
  }

  function toast(message, type = "") {
    const el = document.createElement("div");
    const color =
      type === "err" ? "bg-red-500" : type === "ok" ? "bg-emerald-600" : "bg-slate-900";
    el.className = `toast rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${color}`;
    el.textContent = message;
    els.toasts.appendChild(el);
    setTimeout(() => {
      el.style.transition = "opacity .3s";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 320);
    }, 2800);
  }

  /* ------------------------------------------------------- Paramètres / URL */
  function queryString() {
    const p = new URLSearchParams();
    p.set("date", state.date);
    if (state.q) p.set("q", state.q);
    if (state.category) p.set("category", state.category);
    if (state.status) p.set("status", state.status);
    if (state.min_price) p.set("min_price", state.min_price);
    if (state.max_price) p.set("max_price", state.max_price);
    if (state.ordering && state.ordering !== "name") p.set("ordering", state.ordering);
    if (state.inactive) p.set("inactive", "1");
    return p.toString();
  }

  function syncUrl() {
    const qs = queryString();
    history.replaceState(null, "", qs ? `?${qs}` : location.pathname);
  }

  function readUrl() {
    const p = new URLSearchParams(location.search);
    state.date = /^\d{4}-\d{2}-\d{2}$/.test(p.get("date") || "") ? p.get("date") : localToday();
    state.q = p.get("q") || "";
    state.category = p.get("category") || "";
    state.status = p.get("status") || "";
    state.min_price = p.get("min_price") || "";
    state.max_price = p.get("max_price") || "";
    state.ordering = p.get("ordering") || "name";
    state.inactive = p.get("inactive") === "1";
  }

  function pushStateToInputs() {
    els.filters.q.value = state.q;
    els.filters.category.value = state.category;
    els.filters.status.value = state.status;
    els.filters.min.value = state.min_price;
    els.filters.max.value = state.max_price;
    els.filters.order.value = state.ordering;
    els.filters.inactive.checked = state.inactive;
    els.dateInput.value = state.date;
  }

  /* ---------------------------------------------------------------- Réseau */
  async function api(url, body, method) {
    const opts = { method: method || (body ? "POST" : "GET"), headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const token = getCookie("csrftoken");
    if (token) opts.headers["X-CSRFToken"] = token;

    const res = await fetch(url, opts);
    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      /* réponse non JSON */
    }
    if (res.status === 401) {
      // Session expirée : on renvoie l'utilisateur vers la page de connexion.
      const next = encodeURIComponent(location.pathname + location.search);
      window.location.assign(`/connexion/?next=${next}`);
      throw new Error("Authentification requise.");
    }
    if (!res.ok) {
      throw new Error((data && data.error) || `Erreur HTTP ${res.status}`);
    }
    return data;
  }

  /* ------------------------------------------------------------- Rendu ---- */
  function dataKey(data) {
    return JSON.stringify([data.groups, data.articles, data.summary, data.categories]);
  }

  function captureFocus() {
    const ae = document.activeElement;
    if (!ae || !els.list.contains(ae)) return null;
    const row = ae.closest(".row");
    if (!row) return null;
    const cls = [...ae.classList].find((c) => c.startsWith("js-"));
    return cls ? { id: row.dataset.id, cls } : null;
  }

  function restoreFocus(info) {
    if (!info) return;
    const row = els.list.querySelector(`.row[data-id="${info.id}"]`);
    const el = row && row.querySelector(`.${info.cls}`);
    if (el) el.focus({ preventScroll: true });
  }

  function apply(data, { force = false } = {}) {
    if (!data) return;
    const focus = captureFocus();
    const key = dataKey(data);
    const changed = key !== lastDataKey;
    lastDataKey = key;

    currentCategories = data.categories || [];
    articlesById = new Map((data.articles || []).map((a) => [a.id, a]));

    renderSummary(data.summary);
    renderCategories(currentCategories);
    renderDay(data.date);
    renderInfo(data.summary);

    if (changed || force) {
      const groups =
        data.groups ||
        (data.articles && data.articles.length
          ? [{ name: null, count: data.articles.length, planned: "0", articles: data.articles }]
          : []);
      renderList(groups);
      restoreFocus(focus);
    }
  }

  function renderSummary(s) {
    if (!s) return;
    els.sum.count.textContent = fmt(s.count);
    els.sum.active.textContent = `${fmt(s.active_total)} article(s) actif(s)`;
    els.sum.todo.textContent = fmt(s.todo);
    els.sum.done.textContent = fmt(s.done);
    els.sum.planned.textContent = money(s.planned);
    els.sum.spent.textContent = money(s.spent);
    els.sum.remaining.textContent = money(s.remaining);
  }

  function renderInfo(s) {
    if (!s) return;
    const orderLabel = els.filters.order.options[els.filters.order.selectedIndex].text;
    els.resultInfo.textContent =
      s.count > 0 ? `${s.count} affiché(s) · tri : ${orderLabel}` : "aucun résultat";
    $("#check-all").disabled = s.count === 0;
    $("#uncheck-all").disabled = s.count === 0;
  }

  function renderDay(dateIso) {
    els.dateInput.value = dateIso;
    const label = dayLabel(dateIso, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    const isToday = dateIso === localToday();
    els.dayTitle.textContent =
      `${label.charAt(0).toUpperCase() + label.slice(1)}${isToday ? " · aujourd'hui" : ""}`;
  }

  /** Reconstruit les deux listes de catégories en conservant la valeur voulue. */
  function renderCategories(categories) {
    const fill = (select, firstLabel, wanted) => {
      select.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = firstLabel;
      select.appendChild(opt0);
      (categories || []).forEach((c) => {
        const o = document.createElement("option");
        o.value = String(c.id);
        o.textContent = `${c.name} (${c.count})`;
        select.appendChild(o);
      });
      const w = String(wanted || "");
      select.value = [...select.options].some((o) => o.value === w) ? w : "";
    };
    fill(els.filters.category, "Toutes catégories", state.category);
    fill(els.article.category, "— Sans catégorie —", els.article.category.value);
  }

  /* --------------------------------------------------------------- Lignes */
  const CHECKBOX =
    "flex h-5 w-5 shrink-0 items-center justify-center accent-emerald-600";
  const QTY_INPUT =
    "h-8 w-14 rounded-md border border-slate-200 bg-white text-center text-sm outline-none transition focus:border-indigo-500";
  const PRICE_INPUT =
    "h-8 w-24 rounded-md border border-slate-200 bg-white px-2 text-right text-sm tabular-nums outline-none transition focus:border-indigo-500";
  const ROW_BTN =
    "grid h-7 w-7 place-items-center rounded-md border border-slate-200 bg-white text-slate-500 transition hover:border-indigo-500 hover:text-indigo-600";

  function rowHTML(a) {
    const cls = [
      "row flex flex-wrap items-center gap-3 rounded-xl border px-3 py-2.5 transition sm:flex-nowrap",
      a.done ? "is-done border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50",
      a.is_active ? "" : "is-off",
    ]
      .filter(Boolean)
      .join(" ");

    return `
      <div class="${cls}" data-id="${a.id}">
        <input type="checkbox" class="js-toggle ${CHECKBOX}" ${a.done ? "checked" : ""}
               aria-label="Marquer ${esc(a.name)} comme fait">

        <div class="min-w-0 flex-1 basis-48">
          <div class="row-name truncate text-sm font-semibold" title="${esc(a.name)}">${esc(a.name)}</div>
          <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
            ${a.category
              ? `<span class="rounded-full bg-indigo-50 px-2 py-0.5 font-medium text-indigo-600">${esc(a.category)}</span>`
              : `<span class="rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-slate-400">Sans catégorie</span>`}
            ${a.is_active ? "" : `<span class="rounded-full bg-red-50 px-2 py-0.5 font-medium text-red-500">Inactif</span>`}
            <span class="text-slate-400">réf. ${money(a.base_price)} / ${esc(a.unit)}</span>
          </div>
        </div>

        <div class="hidden w-20 shrink-0 items-center gap-1 sm:flex">
          <input type="number" class="js-qty ${QTY_INPUT}" min="1" step="1" value="${a.quantity}"
                 aria-label="Quantité de ${esc(a.name)}">
        </div>

        <div class="w-36 shrink-0 sm:w-40">
          <div class="flex items-center justify-end gap-1.5">
            <input type="text" inputmode="decimal" class="js-price ${PRICE_INPUT}" value="${fmt(a.price)}"
                   aria-label="Prix du ${esc(a.name)}">
            <span class="w-7 shrink-0 text-[11px] text-slate-400">${esc(CFG.currency)}</span>
          </div>
        </div>

        <div class="w-28 shrink-0 text-right text-sm font-bold tabular-nums ${
          a.done ? "text-emerald-700" : "text-slate-400"
        }">${money(a.total)}</div>

        <div class="flex w-14 shrink-0 items-center justify-end gap-1">
          <button type="button" class="js-edit ${ROW_BTN}" title="Modifier" aria-label="Modifier ${esc(a.name)}">
            <i data-lucide="pencil" class="h-3.5 w-3.5"></i>
          </button>
          <button type="button" class="js-del ${ROW_BTN} hover:!border-red-500 hover:!text-red-500"
                  title="Supprimer" aria-label="Supprimer ${esc(a.name)}">
            <i data-lucide="trash-2" class="h-3.5 w-3.5"></i>
          </button>
        </div>
      </div>`;
  }

  const LIST_HEAD = `
    <div class="hidden items-center gap-3 px-3 pb-1 pt-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400 lg:flex">
      <span class="w-5"></span>
      <span class="flex-1">Article</span>
      <span class="w-20">Qté</span>
      <span class="w-40 text-right">Prix du jour</span>
      <span class="w-28 text-right">Total</span>
      <span class="w-14"></span>
    </div>`;

  /** Affiche les articles groupés par catégorie. */
  function renderList(groups) {
    const total = (groups || []).reduce((n, g) => n + g.articles.length, 0);

    if (total === 0) {
      const filtering =
        state.q || state.category || state.status || state.min_price || state.max_price;
      els.list.innerHTML = `
        <div class="grid justify-items-center gap-2 p-10 text-center">
          <i data-lucide="${filtering ? "search-x" : "shopping-basket"}" class="h-9 w-9 text-slate-300"></i>
          <p class="text-sm font-medium text-slate-500">
            ${filtering ? "Aucun article ne correspond à ces filtres." : "Aucun article pour l'instant."}
          </p>
          <p class="text-xs text-slate-400">
            ${filtering ? "Modifiez les filtres ci-dessus." : "Cliquez sur « Nouvel article » pour commencer."}
          </p>
        </div>`;
      icons();
      return;
    }

    els.list.innerHTML =
      LIST_HEAD +
      groups
        .map(
          (g) => `
        <div class="group">
          <div class="flex items-center gap-2 px-2 pb-1 pt-3">
            <i data-lucide="${g.name ? "folder" : "inbox"}" class="h-3.5 w-3.5 text-indigo-500"></i>
            <span class="text-[11px] font-bold uppercase tracking-wider text-slate-500">${esc(g.name || "Sans catégorie")}</span>
            <span class="text-[11px] font-normal text-slate-400">· ${g.count} article(s)</span>
            <span class="ml-auto text-[11px] font-semibold tabular-nums text-slate-500">${money(g.planned)}</span>
          </div>
          <div class="space-y-1.5">
            ${g.articles.map(rowHTML).join("")}
          </div>
        </div>`
        )
        .join("");

    icons();
  }

  function renderHistory(days) {
    if (!days || days.length === 0) {
      els.history.innerHTML = `
        <div class="grid justify-items-center gap-2 p-6 text-center">
          <i data-lucide="calendar-x" class="h-8 w-8 text-slate-300"></i>
          <p class="text-sm text-slate-400">Aucun marquage enregistré pour le moment.</p>
        </div>`;
      icons();
      return;
    }
    els.history.innerHTML = days
      .map((d) => {
        const active =
          d.date === state.date
            ? "border-indigo-500 bg-indigo-50 text-indigo-700"
            : "border-slate-200 bg-slate-50 hover:border-indigo-500";
        return `
        <button type="button" class="${active} hist-day min-w-[112px] flex-0 shrink-0 rounded-xl border px-3 py-2.5 text-center transition" data-date="${d.date}">
          <span class="block text-xs text-slate-500">${dayLabel(d.date, { weekday: "short", day: "2-digit", month: "short" })}</span>
          <span class="block text-sm font-bold tabular-nums">${money(d.total)}</span>
          <span class="block text-[11px] text-slate-400">${d.count} article(s)</span>
        </button>`;
      })
      .join("");
    icons();
  }

  /* ------------------------------------------------------- Chargement data */
  async function load({ force = false, silent = true } = {}) {
    try {
      const data = await api(`/api/articles/?${queryString()}`);
      apply(data, { force });
      return data;
    } catch (err) {
      if (!silent) toast(err.message, "err");
      return null;
    }
  }

  async function loadHistory() {
    try {
      const data = await api("/api/history/");
      renderHistory(data.days);
    } catch (_) {
      /* historique non critique */
    }
  }

  async function mutate(url, body, method) {
    try {
      const data = await api(url, body, method);
      apply(data, { force: true });
      loadHistory();
      return data;
    } catch (err) {
      toast(err.message, "err");
      await load({ force: true }); // resynchronise l'affichage
      return null;
    }
  }

  /* ------------------------------------------------------ Actions sur ligne */
  function rowPayload(row) {
    const qty = parseInt(row.querySelector(".js-qty").value, 10);
    return {
      article_id: Number(row.dataset.id),
      date: state.date,
      done: row.querySelector(".js-toggle").checked,
      price: row.querySelector(".js-price").value,
      quantity: Number.isFinite(qty) && qty > 0 ? qty : 1,
    };
  }

  els.list.addEventListener("change", (e) => {
    const row = e.target.closest(".row");
    if (!row) return;
    if (e.target.classList.contains("js-toggle")) {
      row.classList.toggle("is-done", e.target.checked); // rendu optimiste
      mutate("/api/entries/", rowPayload(row));
    } else if (e.target.classList.contains("js-price") || e.target.classList.contains("js-qty")) {
      mutate("/api/entries/", rowPayload(row));
    }
  });

  // Entrée dans un champ = validation
  els.list.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.target.classList.contains("js-price") || e.target.classList.contains("js-qty"))) {
      e.preventDefault();
      e.target.blur();
    }
  });

  els.list.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const row = btn.closest(".row");
    if (!row) return;
    const id = Number(row.dataset.id);

    if (btn.classList.contains("js-edit")) {
      openModal(articlesById.get(id));
    } else if (btn.classList.contains("js-del")) {
      openConfirmDelete(id);
    }
  });

  /* ------------------------------------------- Modale de confirmation ---- */
  /** Demande de suppression : ouvre la modale au lieu du confirm() natif. */
  function openConfirmDelete(id) {
    const art = articlesById.get(id);
    pendingDelete = id;
    els.confirmTitle.textContent = art
      ? `Supprimer « ${art.name} » ?`
      : "Supprimer cet article ?";
    els.confirmMessage.textContent =
      "Tous ses marquages journaliers (prix du jour, quantités, coches) seront " +
      "définitivement supprimés ainsi que ses entrées passées. Cette action est irréversible.";
    els.confirmModal.showModal();
    // Le focus démarre sur « Annuler » : la touche Entrée ne supprime pas.
    $("#confirm-cancel").focus();
  }

  function closeConfirm() {
    pendingDelete = null;
    if (els.confirmModal.open) els.confirmModal.close();
  }

  $("#confirm-cancel").addEventListener("click", closeConfirm);
  els.confirmModal.addEventListener("click", (e) => {
    if (e.target === els.confirmModal) closeConfirm(); // clic sur le fond
  });
  els.confirmModal.addEventListener("close", () => {
    pendingDelete = null;
  });

  els.confirmForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const id = pendingDelete;
    closeConfirm();
    if (id !== null) {
      mutate(`/api/articles/${id}/?${queryString()}`, undefined, "DELETE");
    }
  });

  /* ----------------------------------------------------------- Marquages */
  function setDate(newDate) {
    state.date = newDate;
    els.dateInput.value = newDate;
    syncUrl();
    load({ force: true });
    renderDay(newDate);
    loadHistory(); // repasse le jour actif sur l'historique
  }

  $("#prev-day").addEventListener("click", () => setDate(shiftDate(state.date, -1)));
  $("#next-day").addEventListener("click", () => setDate(shiftDate(state.date, 1)));
  $("#today-btn").addEventListener("click", () => setDate(localToday()));
  els.dateInput.addEventListener("change", () => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(els.dateInput.value)) setDate(els.dateInput.value);
  });

  $("#check-all").addEventListener("click", () =>
    mutate(`/api/entries/bulk/?${queryString()}`, { date: state.date, done: true })
  );
  $("#uncheck-all").addEventListener("click", () =>
    mutate(`/api/entries/bulk/?${queryString()}`, { date: state.date, done: false })
  );

  /* ------------------------------------------------------------- Filtres */
  let debounce;
  function onFiltersChanged(immediate = false) {
    syncUrl();
    clearTimeout(debounce);
    debounce = setTimeout(() => load({ force: true }), immediate ? 0 : 320);
  }

  els.filters.q.addEventListener("input", () => {
    state.q = els.filters.q.value.trim();
    onFiltersChanged();
  });
  els.filters.category.addEventListener("change", () => {
    state.category = els.filters.category.value;
    onFiltersChanged(true);
  });
  els.filters.status.addEventListener("change", () => {
    state.status = els.filters.status.value;
    onFiltersChanged(true);
  });
  els.filters.order.addEventListener("change", () => {
    state.ordering = els.filters.order.value;
    onFiltersChanged(true);
  });
  els.filters.inactive.addEventListener("change", () => {
    state.inactive = els.filters.inactive.checked;
    onFiltersChanged(true);
  });

  const priceFilter = (el, key) => {
    el.addEventListener("input", () => {
      const raw = el.value.trim();
      if (raw === "") {
        state[key] = "";
        el.style.borderColor = "";
        onFiltersChanged();
        return;
      }
      const n = parseNum(raw);
      if (Number.isNaN(n)) {
        el.style.borderColor = "#ef4444";
        return; // on attend une saisie valide
      }
      el.style.borderColor = "";
      state[key] = raw;
      onFiltersChanged();
    });
  };
  priceFilter(els.filters.min, "min_price");
  priceFilter(els.filters.max, "max_price");

  $("#clear-filters").addEventListener("click", () => {
    Object.assign(state, {
      q: "", category: "", status: "", min_price: "", max_price: "",
      ordering: "name", inactive: false,
    });
    pushStateToInputs();
    els.filters.min.style.borderColor = "";
    els.filters.max.style.borderColor = "";
    onFiltersChanged(true);
  });

  /* ------------------------------------------------------- Modale article */
  function openModal(article) {
    els.formError.classList.add("hidden");
    const a = article || {};
    els.article.id.value = a.id || "";
    els.article.name.value = a.name || "";
    els.article.price.value = a.id ? fmt(a.base_price) : "";
    els.article.unit.value = a.unit || "";
    els.article.newCategory.value = "";
    els.article.active.checked = a.id ? !!a.is_active : true;
    els.article.title.textContent = a.id ? "Modifier l'article" : "Nouvel article";
    renderCategories(currentCategories);
    els.article.category.value = a.category_id ? String(a.category_id) : "";
    els.modal.showModal();
    setTimeout(() => els.article.name.focus(), 30);
  }

  $("#add-btn").addEventListener("click", () => openModal(null));
  $("#modal-cancel").addEventListener("click", () => els.modal.close());
  els.modal.addEventListener("click", (e) => {
    if (e.target === els.modal) els.modal.close(); // clic sur le fond
  });

  els.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = els.article.name.value.trim();
    if (!name) {
      els.formError.textContent = "Le nom de l'article est obligatoire.";
      els.formError.classList.remove("hidden");
      els.article.name.focus();
      return;
    }
    const body = {
      name,
      base_price: els.article.price.value,
      unit: els.article.unit.value.trim(),
      category_id: els.article.category.value || "",
      category_name: els.article.newCategory.value.trim(),
      is_active: els.article.active.checked,
    };
    const id = els.article.id.value;
    try {
      const data = id
        ? await api(`/api/articles/${id}/?${queryString()}`, body, "PATCH")
        : await api(`/api/articles/?${queryString()}`, body, "POST");
      els.modal.close();
      apply(data, { force: true });
      loadHistory();
      toast(id ? "Article mis à jour." : "Article ajouté.", "ok");
    } catch (err) {
      els.formError.textContent = err.message;
      els.formError.classList.remove("hidden");
    }
  });

  /* ------------------------------------------------------ Modale catégorie */
  $("#add-cat-btn").addEventListener("click", () => {
    els.catError.classList.add("hidden");
    els.catName.value = "";
    els.catModal.showModal();
    setTimeout(() => els.catName.focus(), 30);
  });
  $("#cat-cancel").addEventListener("click", () => els.catModal.close());
  els.catModal.addEventListener("click", (e) => {
    if (e.target === els.catModal) els.catModal.close();
  });

  els.catForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = els.catName.value.trim();
    if (!name) {
      els.catError.textContent = "Le nom de la catégorie est obligatoire.";
      els.catError.classList.remove("hidden");
      return;
    }
    try {
      await api("/api/categories/", { name });
      els.catModal.close();
      toast(`Catégorie « ${name} » créée.`, "ok");
      await load({ force: true }); // met à jour les listes déroulantes
    } catch (err) {
      els.catError.textContent = err.message;
      els.catError.classList.remove("hidden");
    }
  });

  /* ----------------------------------------------------------- Historique */
  els.history.addEventListener("click", (e) => {
    const day = e.target.closest(".hist-day");
    if (!day) return;
    setDate(day.dataset.date);
  });

  /* -------------------------------------------------------------- Clavier */
  document.addEventListener("keydown", (e) => {
    const tag = (document.activeElement && document.activeElement.tagName) || "";
    if (e.key === "/" && !/INPUT|SELECT|TEXTAREA/.test(tag)) {
      e.preventDefault();
      els.filters.q.focus();
    }
  });

  /* ------------------------------------------------- Synchronisation auto */
  function poll() {
    if (document.hidden) return;
    const ae = document.activeElement;
    // On n'interrompt pas une saisie en cours dans la liste.
    if (ae && ae.tagName === "INPUT" && els.list.contains(ae)) return;
    load();
  }

  /* ----------------------------------------------------------------- Init */
  readUrl();
  pushStateToInputs();
  renderDay(state.date);
  icons();

  load({ force: true, silent: false });
  loadHistory();

  setInterval(poll, Math.max(2, Number(CFG.poll) || 5) * 1000);
  setInterval(loadHistory, 60_000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load();
  });
})();
