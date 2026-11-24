/**
 * Interatividade local offline — Plataforma Concurso 2027
 * Cronômetro de estudo/simulado, menu lateral recolhível, flashcards e filtros rápidos.
 */
(function () {
  "use strict";

  // 1. Controle do menu lateral recolhível
  const shell = document.querySelector(".app-shell");
  const toggleBtn = document.getElementById("sidebar-toggle");
  if (shell && toggleBtn) {
    const savedState = localStorage.getItem("p2027_sidebar_collapsed");
    if (savedState === "true") {
      shell.classList.add("sidebar-collapsed");
    }
    toggleBtn.addEventListener("click", function () {
      shell.classList.toggle("sidebar-collapsed");
      localStorage.setItem(
        "p2027_sidebar_collapsed",
        shell.classList.contains("sidebar-collapsed") ? "true" : "false"
      );
    });
  }

  // 2. Cronômetro de Sessão de Estudo / Simulado no Cabeçalho
  let timerSeconds = parseInt(sessionStorage.getItem("p2027_timer_sec") || "0", 10);
  let timerRunning = sessionStorage.getItem("p2027_timer_run") === "true";
  let timerInterval = null;

  const timerDisplay = document.getElementById("study-timer-display");
  const timerStartBtn = document.getElementById("study-timer-toggle");
  const timerResetBtn = document.getElementById("study-timer-reset");

  function formatDuration(sec) {
    const h = String(Math.floor(sec / 3600)).padStart(2, "0");
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    return `${h}:${m}:${s}`;
  }

  function updateTimerUI() {
    if (timerDisplay) {
      timerDisplay.textContent = formatDuration(timerSeconds);
    }
    if (timerStartBtn) {
      timerStartBtn.textContent = timerRunning ? "Pausar" : "Iniciar";
    }
    // Preenche automaticamente inputs de minutos se a usuária desejar usar o tempo cronometrado
    const durationInput = document.getElementById("input-duracao-cronometrada");
    if (durationInput && timerSeconds >= 60) {
      durationInput.value = Math.max(1, Math.round(timerSeconds / 60));
    }
  }

  function tick() {
    timerSeconds += 1;
    sessionStorage.setItem("p2027_timer_sec", String(timerSeconds));
    updateTimerUI();
  }

  if (timerRunning) {
    timerInterval = setInterval(tick, 1000);
  }
  updateTimerUI();

  if (timerStartBtn) {
    timerStartBtn.addEventListener("click", function () {
      timerRunning = !timerRunning;
      sessionStorage.setItem("p2027_timer_run", timerRunning ? "true" : "false");
      if (timerRunning) {
        timerInterval = setInterval(tick, 1000);
      } else if (timerInterval) {
        clearInterval(timerInterval);
      }
      updateTimerUI();
    });
  }

  if (timerResetBtn) {
    timerResetBtn.addEventListener("click", function () {
      timerRunning = false;
      timerSeconds = 0;
      if (timerInterval) clearInterval(timerInterval);
      sessionStorage.setItem("p2027_timer_sec", "0");
      sessionStorage.setItem("p2027_timer_run", "false");
      updateTimerUI();
    });
  }

  // 3. Revelar resposta de Flashcards
  window.toggleFlashcard = function (cardId) {
    const el = document.getElementById("flashcard-" + cardId);
    if (el) {
      el.classList.toggle("revealed");
    }
  };
})();
