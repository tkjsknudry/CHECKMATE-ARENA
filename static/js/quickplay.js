/* CHECKMATE ARENA — Quick Play (antrean matchmaking) di dashboard. */
(function () {
  "use strict";

  var btn = document.getElementById("quickplay-btn");
  if (!btn || typeof io === "undefined") return;

  var overlay = document.getElementById("qp-overlay");
  var timerEl = document.getElementById("qp-timer");
  var socket = null;
  var ticker = null;
  var seconds = 0;

  function stop() {
    if (socket) {
      socket.emit("queue_leave");
      socket.disconnect();
      socket = null;
    }
    clearInterval(ticker);
    overlay.hidden = true;
  }

  btn.addEventListener("click", function () {
    seconds = 0;
    timerEl.textContent = "0";
    overlay.hidden = false;
    ticker = setInterval(function () {
      seconds += 1;
      timerEl.textContent = String(seconds);
    }, 1000);

    socket = io({ reconnectionDelayMax: 3000 });
    socket.on("connect", function () { socket.emit("queue_join"); });
    socket.on("match_found", function (data) {
      clearInterval(ticker);
      window.location.href = "/game/" + encodeURIComponent(data.code);
    });
    socket.on("error_message", function (data) {
      alert(data.message || "Terjadi kesalahan.");
      stop();
    });
  });

  document.getElementById("qp-cancel").addEventListener("click", stop);
})();