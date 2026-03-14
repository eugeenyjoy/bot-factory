/**
 * Chat — логика веб-чата бота
 * GUI панели: промпт, знания
 */

const BOT_ID = location.pathname.split('/chat/')[1]?.split('/')[0] || '';
const API_BASE = `/api/bots/${BOT_ID}`;

let chatUserId = parseInt(localStorage.getItem(`chat_uid_${BOT_ID}`) || '0');
if (!chatUserId) {
    chatUserId = Date.now();
    localStorage.setItem(`chat_uid_${BOT_ID}`, chatUserId);
}

let selectMode = false;
let memoryViewOpen = false;
let activeChatPanel = null;
let botConfig = null;

// хранилище промптов (локально)
let userPrompts = JSON.parse(localStorage.getItem(`prompts_${BOT_ID}_${chatUserId}`) || '[]');

// ====================================================
// ИНИТ
// ====================================================

document.addEventListener('DOMContentLoaded', async () => {
    await loadBotInfo();
    await loadChatHistory();
});

async function loadBotInfo() {
    try {
        const resp = await fetch(`${API_BASE}`);
        if (!resp.ok) throw new Error('Bot not found');
        const data = await resp.json();
        botConfig = data.config || data;

        document.getElementById('chatBotName').textContent = botConfig.name || 'Бот';
        document.getElementById('chatBotModel').textContent = botConfig.model || '';
        document.title = botConfig.name || 'Чат';

        // показываем кнопки тулбара по правам
        const perms = botConfig.tool_permissions || {};
        if (perms.user_can_add_prompt) {
            document.getElementById('tbPrompt').style.display = '';
        }
        if (perms.user_can_add_knowledge) {
            document.getElementById('tbKnowledge').style.display = '';
        }

        // скрываем тулбар если нет ни одной кнопки
        const toolbar = document.getElementById('chatToolbar');
        const visibleBtns = toolbar.querySelectorAll('button:not([style*="display: none"])');
        if (visibleBtns.length === 0) {
            toolbar.style.display = 'none';
        }

    } catch (e) {
        document.getElementById('chatBotName').textContent = '❌ Бот не найден';
    }
}

async function loadChatHistory() {
    try {
        const resp = await fetch(`${API_BASE}/history/${chatUserId}`);
        if (!resp.ok) return;
        const messages = await resp.json();

        if (messages && messages.length > 0) {
            document.getElementById('chatMessages').innerHTML = '';
            messages.forEach(m => {
                addMessageBubble(m.role === 'user' ? 'user' : 'bot', m.content, m.index);
            });
            scrollToBottom();
            updateMemoryCounter(messages.length);
        }
    } catch (e) {}
}

// ====================================================
// ОТПРАВКА СООБЩЕНИЙ
// ====================================================

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    addMessageBubble('user', text);
    const thinkEl = addMessageBubble('bot', '⏳ Думаю...');
    scrollToBottom();

    try {
        const resp = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: text, user_id: chatUserId})
        });
        const data = await resp.json();
        thinkEl.remove();

        if (data.ok !== false && data.reply) {
            addMessageBubble('bot', data.reply);

            // показываем выполненные команды
            if (data.tools_used && data.tools_used.length > 0) {
                const cmds = data.tools_used.map(t => t.command || '').filter(Boolean);
                if (cmds.length > 0) {
                    addSystemMessage(`🔧 Выполнено: ${cmds.join(', ')}`);
                }
            }
        } else {
            addMessageBubble('bot', `❌ ${data.error || 'Ошибка'}`);
        }
    } catch (e) {
        thinkEl.remove();
        addMessageBubble('bot', `❌ ${e.message}`);
    }
    scrollToBottom();
}

// ====================================================
// ПУЗЫРИ СООБЩЕНИЙ
// ====================================================

function addMessageBubble(role, text, index) {
    const container = document.getElementById('chatMessages');

    // убираем welcome
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const row = document.createElement('div');
    row.className = `msg-row ${role === 'user' ? 'user' : 'bot'}`;
    if (index !== undefined) row.dataset.index = index;

    if (selectMode) {
        row.onclick = () => toggleSelectMessage(row);
        row.style.cursor = 'pointer';
    }

    const content = document.createElement('div');
    content.className = 'msg-content';

    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${role === 'user' ? 'user' : 'bot'}`;
    bubble.textContent = text;

    content.appendChild(bubble);
    row.appendChild(content);
    container.appendChild(row);
    return row;
}

function addSystemMessage(text) {
    const container = document.getElementById('chatMessages');
    const el = document.createElement('div');
    el.style.cssText = 'text-align:center; color:#555; font-size:11px; padding:4px; margin:2px 0;';
    el.textContent = text;
    container.appendChild(el);
}

function scrollToBottom() {
    const c = document.getElementById('chatMessages');
    setTimeout(() => { c.scrollTop = c.scrollHeight; }, 50);
}

function updateMemoryCounter(count) {
    const el = document.getElementById('memoryCounter');
    if (count > 0) {
        el.textContent = `🧠 ${count} сообщений в памяти`;
        el.style.display = 'block';
    } else {
        el.style.display = 'none';
    }
}

// ====================================================
// ВЫБОР СООБЩЕНИЙ
// ====================================================

function enterSelectMode() {
    selectMode = true;
    document.getElementById('selectBar').style.display = 'flex';
    document.querySelectorAll('.msg-row').forEach(r => {
        r.style.cursor = 'pointer';
        r.onclick = () => toggleSelectMessage(r);
    });
}

function exitSelectMode() {
    selectMode = false;
    document.getElementById('selectBar').style.display = 'none';
    document.querySelectorAll('.msg-row').forEach(r => {
        r.classList.remove('selected');
        r.style.cursor = '';
        r.onclick = null;
    });
    document.getElementById('selectedCount').textContent = 'Выбрано: 0';
}

function toggleSelectMessage(row) {
    row.classList.toggle('selected');
    const count = document.querySelectorAll('.msg-row.selected').length;
    document.getElementById('selectedCount').textContent = `Выбрано: ${count}`;
}

function selectAll() {
    document.querySelectorAll('.msg-row').forEach(r => r.classList.add('selected'));
    const count = document.querySelectorAll('.msg-row.selected').length;
    document.getElementById('selectedCount').textContent = `Выбрано: ${count}`;
}

async function deleteSelected() {
    const selected = document.querySelectorAll('.msg-row.selected');
    const indices = [];
    selected.forEach(r => {
        if (r.dataset.index !== undefined) indices.push(parseInt(r.dataset.index));
    });

    if (indices.length === 0) return;

    try {
        await fetch(`${API_BASE}/history/${chatUserId}`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({indices})
        });
        selected.forEach(r => r.remove());
        exitSelectMode();
    } catch (e) {}
}

// ====================================================
// ОЧИСТКА
// ====================================================

function showClearConfirm() {
    document.getElementById('confirmBar').style.display = 'flex';
}

function hideClearConfirm() {
    document.getElementById('confirmBar').style.display = 'none';
}

async function clearAllHistory() {
    hideClearConfirm();
    try {
        await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: '/clear', user_id: chatUserId})
        });
        document.getElementById('chatMessages').innerHTML =
            '<div class="chat-welcome">🗑️ История очищена!</div>';
        updateMemoryCounter(0);
    } catch (e) {}
}

// ====================================================
// ПАМЯТЬ
// ====================================================

function toggleMemoryView() {
    memoryViewOpen = !memoryViewOpen;
    document.getElementById('btnMemory').classList.toggle('active', memoryViewOpen);
    // пока просто перезагружаем историю
    if (memoryViewOpen) loadChatHistory();
}

// ====================================================
// ПАНЕЛИ: ПРОМПТ + ЗНАНИЯ
// ====================================================

function toggleChatPanel(name) {
    const panels = ['prompt', 'knowledge'];
    const buttons = {prompt: 'tbPrompt', knowledge: 'tbKnowledge'};

    if (activeChatPanel === name) {
        document.getElementById(`panel${cap(name)}`).classList.remove('active');
        document.getElementById(buttons[name]).classList.remove('active');
        activeChatPanel = null;
        return;
    }

    panels.forEach(p => {
        document.getElementById(`panel${cap(p)}`).classList.remove('active');
        if (buttons[p]) document.getElementById(buttons[p]).classList.remove('active');
    });

    document.getElementById(`panel${cap(name)}`).classList.add('active');
    document.getElementById(buttons[name]).classList.add('active');
    activeChatPanel = name;

    if (name === 'prompt') renderPromptList();
    if (name === 'knowledge') loadKnowledgePanel();
}

function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ============================
// ПРОМПТ GUI
// ============================

function renderPromptList() {
    const list = document.getElementById('promptList');
    if (userPrompts.length === 0) {
        list.innerHTML = '<div class="chat-panel-empty">Нет дополнений. Добавьте инструкцию для бота.</div>';
        return;
    }
    list.innerHTML = userPrompts.map((p, i) => `
        <div class="chat-panel-item">
            <div class="chat-panel-item-text">${escapeHtml(p)}</div>
            <button class="chat-panel-item-delete" onclick="removePromptGUI(${i})">✕</button>
        </div>
    `).join('');
}

async function addPromptGUI() {
    const input = document.getElementById('promptInput');
    const text = input.value.trim();
    if (!text) return;

    try {
        const resp = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: `/prompt ${text}`, user_id: chatUserId})
        });
        const data = await resp.json();

        if (data.reply && data.reply.includes('✅')) {
            userPrompts.push(text);
            localStorage.setItem(`prompts_${BOT_ID}_${chatUserId}`, JSON.stringify(userPrompts));
            input.value = '';
            renderPromptList();
            addSystemMessage(`📝 Промпт: ${text.substring(0, 60)}...`);
            scrollToBottom();
        } else {
            addMessageBubble('bot', data.reply || 'Ошибка');
            scrollToBottom();
        }
    } catch (e) {
        addMessageBubble('bot', `❌ ${e.message}`);
    }
}

async function removePromptGUI(index) {
    userPrompts.splice(index, 1);
    localStorage.setItem(`prompts_${BOT_ID}_${chatUserId}`, JSON.stringify(userPrompts));

    // синхронизируем с сервером
    await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: '/prompt_clear', user_id: chatUserId})
    });

    for (const p of userPrompts) {
        await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: `/prompt ${p}`, user_id: chatUserId})
        });
    }

    renderPromptList();
    addSystemMessage('📝 Промпт удалён');
    scrollToBottom();
}

// ============================
// ЗНАНИЯ GUI
// ============================

// ============================
// ЗНАНИЯ GUI
// ============================

async function loadKnowledgePanel() {
    const container = document.getElementById('knowledgeInfoPanel');
    container.innerHTML = '<div class="chat-panel-empty">Загрузка...</div>';

    try {
        const resp = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: '/knowledge', user_id: chatUserId})
        });
        const data = await resp.json();
        if (data.reply) {
            container.innerHTML = `<div style="color:#8b8b8b; font-size:13px; white-space:pre-wrap; margin-bottom:4px;">${escapeHtml(data.reply)}</div>`;
        } else {
            container.innerHTML = '<div class="chat-panel-empty">📚 База знаний пуста</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="chat-panel-empty">Не удалось загрузить</div>';
    }
}

// --- загрузка файлов ---

document.addEventListener('DOMContentLoaded', () => {
    const zone = document.getElementById('knowledgeDropZone');
    if (zone) {
        zone.addEventListener('click', () => {
            document.getElementById('knowledgeFileUpload').click();
        });
    }
});

function handleKnowledgeDrop(event) {
    event.preventDefault();
    event.currentTarget.classList.remove('dragover');
    const files = event.dataTransfer.files;
    if (files.length > 0) handleKnowledgeFiles(files);
}

async function handleKnowledgeFiles(files) {
    const progress = document.getElementById('knowledgeUploadProgress');
    progress.style.display = 'block';
    progress.innerHTML = '';

    for (const file of files) {
        const itemId = 'upload_' + Date.now() + '_' + Math.random();
        progress.innerHTML += `
            <div class="knowledge-upload-item" id="${itemId}">
                <span class="name">📄 ${escapeHtml(file.name)}</span>
                <span class="status loading">⏳</span>
            </div>`;

        try {
            const base64 = await fileToBase64(file);
            const resp = await fetch(`${API_BASE}/knowledge/file`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    filename: file.name,
                    content_base64: base64,
                    source: "user"
                })
            });
            const data = await resp.json();

            const el = document.getElementById(itemId);
            if (el) {
                const statusEl = el.querySelector('.status');
                if (data.ok) {
                    statusEl.className = 'status ok';
                    statusEl.textContent = `✅ ${data.chunks} чанков`;
                    addSystemMessage(`📚 ${file.name}: ${data.chunks} чанков`);
                } else {
                    statusEl.className = 'status err';
                    statusEl.textContent = `❌ ${data.error}`;
                }
            }
        } catch (e) {
            const el = document.getElementById(itemId);
            if (el) {
                const statusEl = el.querySelector('.status');
                statusEl.className = 'status err';
                statusEl.textContent = `❌ ${e.message}`;
            }
        }
    }

    setTimeout(() => loadKnowledgePanel(), 500);
    scrollToBottom();

    const fileInput = document.getElementById('knowledgeFileUpload');
    if (fileInput) fileInput.value = '';
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// --- текст вручную ---

async function addKnowledgeGUI() {
    const title = document.getElementById('learnTitleInput').value.trim();
    const text = document.getElementById('learnTextInput').value.trim();
    if (!text) return;

    const fullText = title ? `${title}: ${text}` : text;

    try {
        const resp = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: `/learn ${fullText}`, user_id: chatUserId})
        });
        const data = await resp.json();

        if (data.reply && data.reply.includes('✅')) {
            document.getElementById('learnTitleInput').value = '';
            document.getElementById('learnTextInput').value = '';
            loadKnowledgePanel();
            addSystemMessage(`📚 Знания добавлены`);
        } else {
            addMessageBubble('bot', data.reply || 'Ошибка');
        }
    } catch (e) {
        addMessageBubble('bot', `❌ ${e.message}`);
    }
    scrollToBottom();
}
// ====================================================
// УТИЛИТЫ
// ====================================================

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}