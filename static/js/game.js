/* CHECKMATE ARENA — klien permainan. Server adalah sumber kebenaran; browser hanya menampilkan. */
(function () {
  "use strict";

  var cfg = window.GAME_CONFIG;
  var MY = cfg.myColor;
  var FILES = "abcdefgh";
  var GLYPH = { k: "\u265A", q: "\u265B", r: "\u265C", b: "\u265D", n: "\u265E", p: "\u265F" };
  var TEXT_MODE = "\uFE0E"; // paksa tampil sebagai simbol, bukan emoji

  var REASONS = {
    checkmate: "Skakmat",
    stalemate: "Stalemate (tidak ada langkah sah)",
    insufficient_material: "Material tidak cukup untuk skakmat",
    seventyfive_moves: "Aturan 75 langkah",
    fifty_moves: "Aturan 50 langkah",
    fivefold_repetition: "Posisi berulang lima kali",
    threefold_repetition: "Posisi berulang tiga kali",
    resignation: "Lawan menyerah",
    timeout: "Waktu habis",
    timeout_insufficient: "Waktu habis, tetapi material lawan tidak cukup untuk skakmat",
    agreement: "Seri atas kesepakatan",
    disconnect: "Pemain terputus lebih dari 90 detik"
  };

  function $(id) { return document.getElementById(id); }

  var boardEl = $("board");
  var state = null;
  var recvAt = 0;
  var pieces = {};
  var selected = null;
  var moveInFlight = false;
  var pendingPromo = null;
  var drag = null;
  var resultShown = false;

  var socket = io({ reconnectionDelayMax: 3000 });

  // ===== Util =====
  function toast(message) {
    var el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    $("toast").appendChild(el);
    setTimeout(function () { el.remove(); }, 3500);
  }

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function formatClock(ms) {
    if (ms < 20000) {
      var s = Math.floor(ms / 1000);
      var tenth = Math.floor((ms % 1000) / 100);
      return pad(s) + "." + tenth;
    }
    var total = Math.ceil(ms / 1000);
    return pad(Math.floor(total / 60)) + ":" + pad(total % 60);
  }

  function parseFen(fen) {
    var map = {};
    var rows = fen.split(" ")[0].split("/");
    for (var r = 0; r < 8; r++) {
      var file = 0;
      for (var i = 0; i < rows[r].length; i++) {
        var ch = rows[r][i];
        if (/\d/.test(ch)) {
          file += parseInt(ch, 10);
        } else {
          map[FILES[file] + (8 - r)] = {
            color: ch === ch.toUpperCase() ? "white" : "black",
            type: ch.toLowerCase()
          };
          file++;
        }
      }
    }
    return map;
  }

  function canMove() {
    return !!state && state.status === "active" && !state.result &&
      state.clocks.running !== null && state.turn === MY &&
      !moveInFlight && !pendingPromo;
  }

  // ===== Papan =====
  function renderBoard() {
    if (!state) return;
    boardEl.textContent = "";

    var targets = selected && state.legal[selected] ? state.legal[selected] : [];
    var ranks = MY === "white" ? [8, 7, 6, 5, 4, 3, 2, 1] : [1, 2, 3, 4, 5, 6, 7, 8];
    var files = MY === "white" ? FILES.split("") : FILES.split("").reverse();

    ranks.forEach(function (rank, ri) {
      files.forEach(function (file, fi) {
        var sq = file + rank;
        var el = document.createElement("div");
        var light = (FILES.indexOf(file) + rank) % 2 === 0;
        var cls = "square " + (light ? "light" : "dark");

        if (state.last_move && (state.last_move.from === sq || state.last_move.to === sq)) cls += " last";
        if (selected === sq) cls += " selected";
        if (state.check === sq) cls += " check";
        if (targets.indexOf(sq) !== -1) cls += " target" + (pieces[sq] ? " capture" : "");
        if (drag && drag.moved && drag.from === sq) cls += " ghosted";

        el.className = cls;
        el.dataset.sq = sq;

        if (ri === ranks.length - 1) {
          var f = document.createElement("span");
          f.className = "coord coord-file";
          f.textContent = file;
          el.appendChild(f);
        }
        if (fi === 0) {
          var rk = document.createElement("span");
          rk.className = "coord coord-rank";
          rk.textContent = rank;
          el.appendChild(rk);
        }

        var p = pieces[sq];
        if (p) {
          var pe = document.createElement("span");
          pe.className = "piece " + (p.color === "white" ? "w" : "b");
          pe.textContent = GLYPH[p.type] + TEXT_MODE;
          el.appendChild(pe);
        }
        boardEl.appendChild(el);
      });
    });
  }

  // ===== Interaksi: klik & drag =====
  function makeGhost(piece) {
    var ghost = document.createElement("span");
    ghost.className = "piece-ghost " + (piece.color === "white" ? "w" : "b");
    ghost.textContent = GLYPH[piece.type] + TEXT_MODE;
    ghost.style.fontSize = (boardEl.clientWidth / 8) * 0.8 + "px";
    document.body.appendChild(ghost);
    return ghost;
  }

  function moveGhost(x, y) {
    if (drag && drag.ghost) {
      drag.ghost.style.left = x + "px";
      drag.ghost.style.top = y + "px";
    }
  }

  function cancelDrag() {
    if (drag && drag.ghost) drag.ghost.remove();
    drag = null;
  }

  boardEl.addEventListener("pointerdown", function (e) {
    if (e.button !== undefined && e.button !== 0) return;
    if (!canMove()) return;
    var sqEl = e.target.closest(".square");
    if (!sqEl) return;
    var sq = sqEl.dataset.sq;
    var legal = state.legal;

    if (selected && legal[selected] && legal[selected].indexOf(sq) !== -1) {
      e.preventDefault();
      attemptMove(selected, sq);
      return;
    }

    var p = pieces[sq];
    if (p && p.color === MY && legal[sq]) {
      e.preventDefault();
      var wasSelected = selected === sq;
      selected = sq;
      drag = {
        from: sq, startX: e.clientX, startY: e.clientY, moved: false,
        ghost: null, wasSelected: wasSelected, pointerId: e.pointerId
      };
      try { boardEl.setPointerCapture(e.pointerId); } catch (err) { /* abaikan */ }
      renderBoard();
    } else {
      selected = null;
      renderBoard();
    }
  });

  boardEl.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var dx = e.clientX - drag.startX;
    var dy = e.clientY - drag.startY;
    if (!drag.moved && Math.sqrt(dx * dx + dy * dy) > 6) {
      drag.moved = true;
      drag.ghost = makeGhost(pieces[drag.from]);
      renderBoard();
    }
    moveGhost(e.clientX, e.clientY);
  });

  function endDrag(e, cancelled) {
    if (!drag) return;
    var d = drag;
    drag = null;
    if (d.ghost) d.ghost.remove();
    try { boardEl.releasePointerCapture(d.pointerId); } catch (err) { /* abaikan */ }

    if (d.moved && !cancelled) {
      var el = document.elementFromPoint(e.clientX, e.clientY);
      var sqEl = el && el.closest ? el.closest(".square") : null;
      var to = sqEl ? sqEl.dataset.sq : null;
      if (to && state.legal[d.from] && state.legal[d.from].indexOf(to) !== -1) {
        attemptMove(d.from, to);
        return;
      }
      selected = null;
    } else if (!d.moved && d.wasSelected) {
      selected = null;
    }
    renderBoard();
  }

  boardEl.addEventListener("pointerup", function (e) { endDrag(e, false); });
  boardEl.addEventListener("pointercancel", function (e) { endDrag(e, true); });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      selected = null;
      cancelDrag();
      $("promo-modal").hidden = true;
      pendingPromo = null;
      renderBoard();
    }
  });

  function attemptMove(from, to) {
    var p = pieces[from];
    var needsPromo = p && p.type === "p" &&
      ((MY === "white" && to.charAt(1) === "8") || (MY === "black" && to.charAt(1) === "1"));
    selected = null;
    if (needsPromo) {
      askPromotion(from, to);
      renderBoard();
      return;
    }
    sendMove(from, to, "");
  }

  function sendMove(from, to, promo) {
    moveInFlight = true;
    socket.emit("make_move", { code: cfg.code, from: from, to: to, promotion: promo });
    renderBoard();
    setTimeout(function () { moveInFlight = false; }, 4000);
  }

  function askPromotion(from, to) {
    pendingPromo = { from: from, to: to };
    var buttons = $("promo-modal").querySelectorAll(".promo-btn");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].textContent = GLYPH[buttons[i].dataset.piece] + TEXT_MODE;
      buttons[i].className = "promo-btn " + (MY === "white" ? "w" : "b");
    }
    $("promo-modal").hidden = false;
  }

  $("promo-modal").addEventListener("click", function (e) {
    var btn = e.target.closest(".promo-btn");
    if (btn && pendingPromo) {
      var p = pendingPromo;
      pendingPromo = null;
      $("promo-modal").hidden = true;
      sendMove(p.from, p.to, btn.dataset.piece);
    } else if (e.target === $("promo-modal")) {
      pendingPromo = null;
      $("promo-modal").hidden = true;
      renderBoard();
    }
  });

  // ===== Tampilan panel =====
  function fillBar(pos, color) {
    var p = state.players[color];
    $(pos + "-name").textContent = p ? p.username + (color === MY ? " (kamu)" : "") : "Menunggu lawan…";
    $(pos + "-rating").textContent = p ? "Rating " + p.rating : "";
    var av = $(pos + "-avatar");
    av.textContent = p ? p.username.charAt(0).toUpperCase() : "?";
    av.style.background = p ? p.avatar_color : "";
    $(pos + "-presence").className = "presence" + (p && p.connected ? " on" : "");
    $(pos + "-presence").title = p && p.connected ? "Terhubung" : "Tidak terhubung";

    var cap = $(pos + "-captured");
    cap.textContent = "";
    state.captured[color].forEach(function (sym) {
      var s = document.createElement("span");
      s.className = "cap " + (color === "white" ? "b" : "w");
      s.textContent = GLYPH[sym] + TEXT_MODE;
      cap.appendChild(s);
    });
  }

  function renderPlayers() {
    var opp = MY === "white" ? "black" : "white";
    fillBar("top", opp);
    fillBar("bottom", MY);
  }

  function renderMoves() {
    var list = $("moves");
    list.textContent = "";
    if (!state.moves.length) {
      var empty = document.createElement("li");
      empty.className = "moves-empty";
      empty.textContent = "Belum ada langkah.";
      list.appendChild(empty);
      return;
    }
    for (var i = 0; i < state.moves.length; i += 2) {
      var li = document.createElement("li");
      var no = document.createElement("span");
      no.className = "mv-no";
      no.textContent = (i / 2 + 1) + ".";
      li.appendChild(no);
      for (var j = i; j < i + 2; j++) {
        var mv = document.createElement("span");
        mv.className = "mv" + (j === state.moves.length - 1 ? " last" : "");
        mv.textContent = state.moves[j] || "";
        li.appendChild(mv);
      }
      list.appendChild(li);
    }
    list.scrollTop = list.scrollHeight;
  }

  function renderBanners() {
    var banner = $("turn-banner");
    var text, mine = false;
    var activeGame = state.status === "active" && !state.result;

    if (state.status === "waiting") {
      text = "Menunggu lawan bergabung…";
    } else if (state.status === "abandoned") {
      text = "Room ini sudah ditutup.";
    } else if (state.result) {
      text = "Permainan selesai";
    } else if (state.clocks.running === null) {
      text = "Menunggu kedua pemain terhubung…";
    } else if (state.turn === MY) {
      text = "Giliranmu" + (state.check ? " — Skak!" : "");
      mine = true;
    } else {
      var opp = state.players[state.turn];
      text = "Giliran " + (opp ? opp.username : "lawan") + (state.check ? " — Skak!" : "");
    }
    banner.textContent = text;
    banner.className = "turn-banner" + (mine ? " mine" : "");

    var drawBtn = $("btn-draw");
    drawBtn.disabled = !activeGame || state.draw_offer_by === MY;
    drawBtn.textContent = state.draw_offer_by === MY ? "Tawaran terkirim" : "Tawarkan seri";
    $("btn-resign").disabled = !activeGame;

    $("draw-banner").hidden = !(activeGame && state.draw_offer_by && state.draw_offer_by !== MY);
  }

  function renderOverlay() {
    var show = state.status === "waiting" || state.status === "abandoned";
    $("waiting-overlay").hidden = !show;
    $("invite-card").hidden = state.status !== "waiting";
    $("closed-card").hidden = state.status !== "abandoned";
  }

  function showResult() {
    var r = state.result;
    var title = r.winner === "draw" ? "Seri" : (r.winner === MY ? "Kamu menang!" : "Kamu kalah");
    var h = $("result-title");
    h.textContent = title;
    h.className = r.winner === "draw" ? "" : (r.winner === MY ? "win" : "lose");

    var reason = REASONS[r.reason] || r.reason;
    if (r.reason === "resignation" && r.winner !== MY) reason = "Kamu menyerah";
    if (r.reason === "disconnect" && r.winner !== MY) reason = "Kamu terputus lebih dari 90 detik";
    $("result-reason").textContent = reason;

    var delta = r.rating_changes[MY];
    var me = state.players[MY];
    $("result-rating").textContent = "Rating " + (me ? me.rating : "") + " (" + (delta >= 0 ? "+" : "") + delta + ")";
    $("result-modal").hidden = false;
  }

  function updateClocks() {
    if (!state) return;
    ["white", "black"].forEach(function (c) {
      var ms = state.clocks[c + "_ms"];
      if (state.clocks.running === c) ms -= performance.now() - recvAt;
      ms = Math.max(0, ms);
      var el = $((c === MY ? "bottom" : "top") + "-clock");
      el.textContent = formatClock(ms);
      el.classList.toggle("active", state.clocks.running === c);
      el.classList.toggle("low", ms > 0 && ms < 20000);
    });
  }
  setInterval(updateClocks, 100);

  function renderAll() {
    renderBoard();
    renderPlayers();
    renderMoves();
    renderBanners();
    renderOverlay();
    updateClocks();
    if (state.result && !resultShown) {
      resultShown = true;
      showResult();
    }
  }

  // ===== Chat =====
  function addChat(m) {
    var log = $("chat-log");
    var box = document.createElement("div");
    box.className = "msg" + (m.username === (state && state.players[MY] ? state.players[MY].username : "") ? " me" : "");
    var head = document.createElement("div");
    head.className = "msg-head";
    var name = document.createElement("span");
    name.className = "msg-name";
    name.textContent = m.username;
    var time = document.createElement("span");
    time.className = "msg-time";
    var d = new Date(m.created_at);
    time.textContent = isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    head.appendChild(name);
    head.appendChild(time);
    var body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = m.body;
    box.appendChild(head);
    box.appendChild(body);
    log.appendChild(box);
    log.scrollTop = log.scrollHeight;
  }

  $("chat-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = $("chat-input");
    var text = input.value.trim();
    if (!text) return;
    socket.emit("chat_send", { code: cfg.code, text: text });
    input.value = "";
  });

  // ===== Tombol aksi =====
  $("btn-resign").addEventListener("click", function () {
    if (confirm("Yakin ingin menyerah?")) socket.emit("resign", { code: cfg.code });
  });
  $("btn-draw").addEventListener("click", function () {
    socket.emit("offer_draw", { code: cfg.code });
  });
  $("draw-accept").addEventListener("click", function () {
    socket.emit("respond_draw", { code: cfg.code, accept: true });
  });
  $("draw-decline").addEventListener("click", function () {
    socket.emit("respond_draw", { code: cfg.code, accept: false });
  });
  $("result-close").addEventListener("click", function () { $("result-modal").hidden = true; });

  // ===== Undangan =====
  $("invite-code").textContent = cfg.code;
  $("invite-link").value = cfg.inviteUrl;

  function copyText(text, btn) {
    function done() {
      var old = btn.textContent;
      btn.textContent = "Tersalin!";
      setTimeout(function () { btn.textContent = old; }, 1500);
    }
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (err) { toast("Salin manual ya."); }
      ta.remove();
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
  }
  $("copy-link").addEventListener("click", function () { copyText(cfg.inviteUrl, $("copy-link")); });
  $("copy-code").addEventListener("click", function () { copyText(cfg.code, $("copy-code")); });

  // ===== Socket =====
  function setConn(on) {
    $("conn-dot").classList.toggle("off", !on);
    $("conn-text").textContent = on ? "Terhubung" : "Menyambung ulang…";
  }

  socket.on("connect", function () {
    setConn(true);
    socket.emit("join_game", { code: cfg.code });
  });
  socket.on("disconnect", function () { setConn(false); });
  socket.on("connect_error", function () { setConn(false); });

  socket.on("game_state", function (s) {
    cancelDrag();
    state = s;
    recvAt = performance.now();
    pieces = parseFen(s.fen);
    selected = null;
    moveInFlight = false;
    renderAll();
  });

  socket.on("move_rejected", function (d) {
    moveInFlight = false;
    toast(d.message || "Langkah ditolak.");
  });
  socket.on("error_message", function (d) { toast(d.message || "Terjadi kesalahan."); });

  socket.on("chat_history", function (list) {
    $("chat-log").textContent = "";
    list.forEach(addChat);
  });
  socket.on("chat_message", addChat);
})();