"use strict";
const $ = (id) => document.getElementById(id);

const stageEl = $("stage");
const lengthEl = $("length");
const lifeEl = $("life");
const wrongCountEl = $("wrongCount");
const hintCountEl = $("hintCount");

const maskedEl = $("masked");
const wrongLettersEl = $("wrongLetters");
const msgEl = $("message");

const imgEl = $("img");
const imgNoteEl = $("imgNote");

const lastEnEl = $("lastEn");
const lastThEl = $("lastTh");
const aboutEnEl = $("aboutEn");
const aboutThEl = $("aboutTh");

const guessInput = $("guess");
const btnGuess = $("btnGuess");
const btnHintLetter = $("btnHintLetter");
const btnStart = $("btnStart");
const btnReset = $("btnReset");

function setMessage(text){ msgEl.textContent = text || ""; }

function setImage(url){
  if (!url){
    imgEl.src = "";
    imgNoteEl.textContent = "No image thumbnail for this word.";
    return;
  }
  imgEl.src = url + (url.includes("?") ? "&" : "?") + "t=" + Date.now();
  imgNoteEl.textContent = "Image: Wikipedia thumbnail";
}

imgEl.onerror = () => {
  imgEl.src = "";
  imgNoteEl.textContent = "Image failed to load (no thumbnail / blocked).";
};

function render(state){
  if (!state || state.status === "no_game"){
    stageEl.textContent = "-";
    lengthEl.textContent = "-";
    lifeEl.textContent = "-";
    wrongCountEl.textContent = "-";
    hintCountEl.textContent = "-";
    maskedEl.textContent = "_ _ _ _";
    wrongLettersEl.innerHTML = "";
    setImage("");
    setMessage("Click Start.");
    lastEnEl.textContent = "-";
    lastThEl.textContent = "-";
    aboutEnEl.textContent = "-";
    aboutThEl.textContent = "-";
    guessInput.disabled = true;
    btnGuess.disabled = true;
    btnHintLetter.disabled = true;
    return;
  }

  stageEl.textContent = state.stage ?? "-";
  lengthEl.textContent = state.length ?? "-";
  lifeEl.textContent = state.life ?? "-";
  wrongCountEl.textContent = (state.wrong || []).length;

  const used = state.hint_letters_used ?? 0;
  const maxu = state.hint_letters_max ?? 2;
  hintCountEl.textContent = `${used}/${maxu}`;

  maskedEl.textContent = state.masked || "";

  wrongLettersEl.innerHTML = "";
  (state.wrong || []).forEach((ch) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = ch;
    wrongLettersEl.appendChild(span);
  });

  setImage(state.img || "");
  setMessage(state.message || "");

  lastEnEl.textContent = state.last_en || "-";
  lastThEl.textContent = state.last_th || "-";
  aboutEnEl.textContent = state.last_about_en || "-";
  aboutThEl.textContent = state.last_about_th || "-";

  const locked = state.status === "failed";
  guessInput.disabled = locked;
  btnGuess.disabled = locked;
  btnHintLetter.disabled = locked || used >= maxu;

  if (!locked) guessInput.focus();
}

async function postJSON(path, body){
  const res = await fetch(path, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body || {})
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); }
  catch { throw new Error("Bad JSON: " + text.slice(0, 160)); }
  if (!res.ok) throw new Error(data.message || data.error || `HTTP ${res.status}`);
  return data;
}

async function start(){
  const st = await postJSON("/api/start", {});
  render(st);
  guessInput.disabled = false;
  btnGuess.disabled = false;
  btnHintLetter.disabled = false;
  guessInput.focus();
}

async function reset(){
  await postJSON("/api/reset", {});
  render({status:"no_game"});
}

async function guess(){
  const g = (guessInput.value || "").trim().toLowerCase();
  guessInput.value = "";
  if (!g) return;
  const st = await postJSON("/api/guess", {guess: g});
  render(st);
}

async function hintLetter(){
  const st = await postJSON("/api/hint_letter", {});
  render(st);
}

btnStart.addEventListener("click", () => start().catch(e => setMessage("Error: " + e.message)));
btnReset.addEventListener("click", () => reset().catch(e => setMessage("Error: " + e.message)));
btnGuess.addEventListener("click", () => guess().catch(e => setMessage("Error: " + e.message)));
btnHintLetter.addEventListener("click", () => hintLetter().catch(e => setMessage("Error: " + e.message)));

guessInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") guess().catch(err => setMessage("Error: " + err.message));
});

(async function init(){
  const res = await fetch("/api/state");
  const state = await res.json();
  render(state);
})();
