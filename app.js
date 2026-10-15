const STORAGE_KEY = 'listy-v1';
const PLACEHOLDERS = { zadania: 'Dodaj zadanie…', zakupy: 'Dodaj produkt…' };

const form = document.getElementById('add-form');
const input = document.getElementById('add-input');
const list = document.getElementById('items');
const empty = document.getElementById('empty');
const counter = document.getElementById('counter');
const clearDone = document.getElementById('clear-done');
const tabs = document.querySelectorAll('.tab');

let state = load();

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && saved.lists) return saved;
  } catch (e) {}
  return { current: 'zadania', lists: { zadania: [], zakupy: [] } };
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {}
}

function items() {
  return state.lists[state.current];
}

function render() {
  tabs.forEach((tab) => {
    tab.setAttribute('aria-selected', String(tab.dataset.list === state.current));
  });
  input.placeholder = PLACEHOLDERS[state.current];

  list.replaceChildren(...items().map(renderItem));

  const total = items().length;
  const done = items().filter((item) => item.done).length;
  empty.hidden = total > 0;
  counter.textContent = total ? `Zrobione: ${done} z ${total}` : '';
  clearDone.disabled = done === 0;
}

function renderItem(item) {
  const li = document.createElement('li');
  li.className = 'item' + (item.done ? ' done' : '');

  const label = document.createElement('label');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.checked = item.done;
  checkbox.addEventListener('change', () => {
    item.done = checkbox.checked;
    save();
    render();
  });
  const text = document.createElement('span');
  text.textContent = item.text;
  label.append(checkbox, text);

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'delete';
  remove.setAttribute('aria-label', `Usuń: ${item.text}`);
  remove.textContent = '✕';
  remove.addEventListener('click', () => {
    state.lists[state.current] = items().filter((other) => other.id !== item.id);
    save();
    render();
  });

  li.append(label, remove);
  return li;
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  items().push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), text, done: false });
  input.value = '';
  save();
  render();
});

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    state.current = tab.dataset.list;
    save();
    render();
  });
});

clearDone.addEventListener('click', () => {
  state.lists[state.current] = items().filter((item) => !item.done);
  save();
  render();
});

render();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('sw.js');
}
