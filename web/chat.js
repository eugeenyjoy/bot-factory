/**
 * Логика веб-чата
 * Отправка сообщений, история, выбор и удаление, просмотр памяти
 */

// ====================================================
// СОСТОЯНИЕ
// ====================================================

// ID бота из URL: /chat/abc123 → abc123
const botId = window.location.pathname.split('/chat/')[1];

// уникальный ID юзера (сохраняется в браузере)
let userId = localStorage.getItem('web_user_id');
if (!userId) {
    userId = Math.floor(Math.random() * 900000000) + 100000000;
    localStorage.setItem('web_user_id', userId);
}
userId = parseInt(userId);

let isWaiting = false;       // ждём ответ от бота
let messages = [];            // [{msg_id, role, content, timestamp}]
let selectMode = false;       // режим выбора сообщений
let selectedIds = new Set();  // выбранные msg_id
let memoryViewOpen = false;   // просмотр памяти


// ====================================================
// ИНИЦИАЛИЗАЦИЯ
// ====================================================

document.addEventListener('DOMContentLoaded', () => {
    loadBotInfo();
    loadHistory();
    document.getElementById('chatInput').focus();
});


// ====================================================
// ЗАГРУЗКА ИНФО О БОТЕ
// ====================================================

async function loadBotInfo() {
    try {
        const res = await fetch(`/api/bots/${botId}`);
        const data = await res.json();
        if (data.config) {
            document.getElementById('chatBotName').textContent = data.config.name;
            document.getElementById('chatBotModel').textContent = data.config.model;
            document.title = `Чат — ${data.config.name}`;
        }
    } catch (e) {
        document.getElementById('chatBotName').textContent = 'Бот не найден';
    }
}


// ====================================================
// ИСТОРИЯ — загрузка и отрисовка
// ====================================================

async function loadHistory() {
    try {
        const res = await fetch(`/api/bots/${botId}/history/${userId}`);
        if (!res.ok) return;
        messages = await res.json();
        renderMessages();
        updateCounter();
    } catch (e) {}
}

function renderMessages() {
    // не перерисовываем если открыта память
    if (memoryViewOpen) return;

    const container = document.getElementById('chatMessages');
    container.innerHTML = '';

    // пустая история — приветствие
    if (messages.length === 0) {
        const w = document.createElement('div');
        w.className = 'chat-welcome';
        w.textContent = 'Привет! Напиши мне что-нибудь 👋';
        container.appendChild(w);
        return;
    }

    // рисуем каждое сообщение
    messages.forEach(msg => {
        const row = buildMsgRow(msg.msg_id, msg.role, msg.content, msg.timestamp);
        container.appendChild(row);
    });

    // скролл вниз
    container.scrollTop = container.scrollHeight;
}

function buildMsgRow(msgId, role, content, timestamp) {
    const isUser = (role === 'user');

    // строка-обёртка
    const row = document.createElement('div');
    row.className = `msg-row ${isUser ? 'user' : 'bot'}`;
    if (msgId) row.dataset.msgId = msgId;

    // в режиме выбора — кликабельная
    if (selectMode && msgId) {
        row.classList.add('selectable');
        if (selectedIds.has(msgId)) row.classList.add('selected');
        row.onclick = () => toggleSelect(msgId);
    }

    // чекбокс (виден только в режиме выбора)
    const checkbox = document.createElement('div');
    checkbox.className = 'msg-checkbox';
    row.appendChild(checkbox);

    // контейнер для пузыря + время
    const wrap = document.createElement('div');
    wrap.className = 'msg-content';

    // пузырь сообщения
    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${isUser ? 'user' : 'bot'}`;
    bubble.textContent = content;
    wrap.appendChild(bubble);

    // время
    if (timestamp) {
        const time = document.createElement('div');
        time.className = 'msg-time';
        time.textContent = formatTime(timestamp);
        wrap.appendChild(time);
    }

    row.appendChild(wrap);
    return row;
}

function updateCounter() {
    const el = document.getElementById('memoryCounter');
    el.textContent = messages.length > 0 ? `🧠 ${messages.length} сообщений в памяти` : '';
}

function formatTime(ts) {
    try {
        const d = new Date(ts + 'Z');
        return d.toLocaleString('ru', {
            hour: '2-digit',
            minute: '2-digit',
            day: 'numeric',
            month: 'short'
        });
    } catch (e) {
        return '';
    }
}


// ====================================================
// ОТПРАВКА СООБЩЕНИЯ
// ====================================================

async function sendMessage() {
    // нельзя отправлять пока ждём ответ или в режиме выбора
    if (isWaiting || selectMode) return;

    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    const container = document.getElementById('chatMessages');

    // убираем приветствие
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    // показываем сообщение юзера сразу
    const userRow = buildMsgRow(null, 'user', text, null);
    container.appendChild(userRow);
    container.scrollTop = container.scrollHeight;

    // показываем typing
    showTyping();
    isWaiting = true;

    try {
        const res = await fetch(`/api/bots/${botId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, user_id: userId })
        });
        const data = await res.json();

        removeTyping();

        if (res.ok && data.ok) {
            // добавляем ответ бота прямо в чат (без перезагрузки)
            const botRow = buildMsgRow(null, 'assistant', data.reply, null);
            container.appendChild(botRow);
            container.scrollTop = container.scrollHeight;

            // тихо обновляем массив messages в фоне (для памяти/выбора)
            loadHistory();

            // предупреждение о лимите
            if (data.remaining !== undefined && data.remaining < 5 && data.remaining > 0) {
                appendSystem(`Осталось сообщений: ${data.remaining}`);
            }
        } else if (data.error === 'limit') {
            // убираем сообщение юзера — оно не сохранилось
            userRow.remove();
            appendSystem('📭 Лимит сообщений исчерпан! Купите ещё через /buy');
        } else {
            appendSystem('⚠️ Ошибка. Попробуй ещё раз.');
        }
    } catch (e) {
        removeTyping();
        appendSystem('⚠️ Не удалось подключиться');
    }

    isWaiting = false;
    input.focus();
}

function appendSystem(text) {
    const container = document.getElementById('chatMessages');
    const el = document.createElement('div');
    el.className = 'chat-system';
    el.textContent = text;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}


// ====================================================
// TYPING ИНДИКАТОР
// ====================================================

let typingInterval = null;

function showTyping() {
    const container = document.getElementById('chatMessages');
    const el = document.createElement('div');
    el.className = 'msg-bubble bot';
    el.id = 'typingIndicator';
    el.textContent = '●●●';
    el.style.color = '#8b8b8b';
    el.style.margin = '0 16px';
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;

    let dots = 0;
    const frames = ['●○○', '●●○', '●●●', '○●●', '○○●', '○○○'];
    typingInterval = setInterval(() => {
        const t = document.getElementById('typingIndicator');
        if (!t) { clearInterval(typingInterval); return; }
        dots = (dots + 1) % frames.length;
        t.textContent = frames[dots];
    }, 300);
}

function removeTyping() {
    if (typingInterval) clearInterval(typingInterval);
    const el = document.getElementById('typingIndicator');
    if (el) el.remove();
}


// ====================================================
// РЕЖИМ ВЫБОРА (как в Telegram)
// ====================================================

function enterSelectMode() {
    selectMode = true;
    selectedIds.clear();
    document.getElementById('selectBar').classList.add('active');
    document.getElementById('btnSelect').style.display = 'none';
    renderMessages();
    updateSelectedCount();
}

function exitSelectMode() {
    selectMode = false;
    selectedIds.clear();
    document.getElementById('selectBar').classList.remove('active');
    document.getElementById('btnSelect').style.display = '';
    renderMessages();
}

function toggleSelect(msgId) {
    // добавить/убрать из выбранных
    if (selectedIds.has(msgId)) {
        selectedIds.delete(msgId);
    } else {
        selectedIds.add(msgId);
    }

    // обновляем визуально
    document.querySelectorAll('.msg-row').forEach(row => {
        const id = parseInt(row.dataset.msgId);
        row.classList.toggle('selected', selectedIds.has(id));
    });

    updateSelectedCount();
}

function selectAll() {
    messages.forEach(m => selectedIds.add(m.msg_id));
    document.querySelectorAll('.msg-row').forEach(row => row.classList.add('selected'));
    updateSelectedCount();
}

function updateSelectedCount() {
    document.getElementById('selectedCount').textContent = `Выбрано: ${selectedIds.size}`;
}

async function deleteSelected() {
    if (selectedIds.size === 0) return;
    if (!confirm(`Удалить ${selectedIds.size} сообщений из памяти?`)) return;

    try {
        const res = await fetch(`/api/bots/${botId}/messages/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ msg_ids: Array.from(selectedIds) })
        });
        if (res.ok) {
            exitSelectMode();
            await loadHistory();
        }
    } catch (e) {}
}


// ====================================================
// ОЧИСТКА ВСЕЙ ИСТОРИИ
// ====================================================

function showClearConfirm() {
    document.getElementById('confirmBar').classList.add('active');
}

function hideClearConfirm() {
    document.getElementById('confirmBar').classList.remove('active');
}

async function clearAllHistory() {
    try {
        const res = await fetch(`/api/bots/${botId}/history/${userId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            messages = [];
            renderMessages();
            updateCounter();
            hideClearConfirm();
        }
    } catch (e) {}
}


// ====================================================
// ПРОСМОТР ПАМЯТИ
// ====================================================

function toggleMemoryView() {
    memoryViewOpen = !memoryViewOpen;

    // подсвечиваем кнопку
    document.getElementById('btnMemory').classList.toggle('active', memoryViewOpen);

    if (memoryViewOpen) {
        showMemoryView();
    } else {
        renderMessages();
    }
}

async function showMemoryView() {
    await loadHistory();

    const container = document.getElementById('chatMessages');
    container.innerHTML = '';

    // заголовок
    const header = document.createElement('div');
    header.className = 'memory-header';
    header.textContent = '🧠 ПАМЯТЬ БОТА — нажми 🧠 чтобы вернуться';
    container.appendChild(header);

    // пусто
    if (messages.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'memory-empty';
        empty.textContent = 'Память пуста';
        container.appendChild(empty);
        return;
    }

    // список сообщений
    messages.forEach(msg => {
        const row = document.createElement('div');
        row.className = 'memory-row';

        // роль
        const role = document.createElement('div');
        role.className = `memory-role ${msg.role}`;
        role.textContent = msg.role;

        // контент
        const content = document.createElement('div');
        content.className = 'memory-content';
        content.textContent = msg.content.length > 300
            ? msg.content.substring(0, 300) + '...'
            : msg.content;

        // удалить
        const del = document.createElement('button');
        del.className = 'memory-delete';
        del.textContent = '✕';
        del.onclick = async () => {
            await fetch(`/api/bots/${botId}/messages/${msg.msg_id}`, { method: 'DELETE' });
            showMemoryView();
        };

        row.appendChild(role);
        row.appendChild(content);
        row.appendChild(del);
        container.appendChild(row);
    });
}