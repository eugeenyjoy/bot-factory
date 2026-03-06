/**
 * Bot Factory — логика панели управления
 * Чистый JS, без библиотек
 */

// ====================================================
// СОСТОЯНИЕ
// ====================================================

let currentBotId = null;
let models = [];

// ====================================================
// ИНИЦИАЛИЗАЦИЯ
// ====================================================

document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    loadBots();
    setInterval(loadBots, 10000);
});

// ====================================================
// API
// ====================================================

async function api(method, url, body = null) {
    const options = {
        method: method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);

    try {
        const response = await fetch(url, options);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
        return data;
    } catch (error) {
        toast(error.message, 'error');
        throw error;
    }
}

// ====================================================
// МОДЕЛИ — с категориями и рейтингом
// ====================================================

async function loadModels() {
    try {
        models = await api('GET', '/api/models');
        fillModelSelects();
    } catch (e) {
        models = [{ id: 'mistralai/mistral-nemo', name: 'Mistral Nemo', category: 'psychology', rating: 6, price: '$0.13', censored: false }];
        fillModelSelects();
    }
}

function fillModelSelects() {
    /**
     * Заполняет <select> с группировкой по категориям
     * Формат: ★★★★★★★★☆☆ Claude Sonnet 4 · $3+$15 · БЕЗ ЦЕНЗУРЫ
     */
    const selects = ['newModel', 'editModel'];

    // порядок категорий
    const categoryOrder = [
        { key: 'uncensored', label: '🔥 Без цензуры (ZERO)' },
        { key: 'psychology', label: '💬 Собеседник / Психология / Самоанализ' },
        { key: 'code',       label: '💻 Код / Программирование' },
        { key: 'creative',   label: '🎭 Ролеплей / Креатив / Истории' },
        { key: 'analytics',  label: '📊 Аналитика / Документы / RAG' },
        { key: 'reasoning',  label: '🧮 Логика / Математика / Reasoning' },
    ];

    // группируем модели по категориям
    const grouped = {};
    models.forEach(m => {
        const cat = m.category || 'other';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(m);
    });

    // сортируем внутри категории по рейтингу (от высшего)
    Object.keys(grouped).forEach(cat => {
        grouped[cat].sort((a, b) => (b.rating || 0) - (a.rating || 0));
    });

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;
        select.innerHTML = '';

        categoryOrder.forEach(cat => {
            const items = grouped[cat.key];
            if (!items || items.length === 0) return;

            // <optgroup> — разделитель категории
            const group = document.createElement('optgroup');
            group.label = cat.label;

            items.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;

                // рейтинг звёздами: ★★★★★★★★☆☆
                const rating = model.rating || 5;
                const stars = '★'.repeat(rating) + '☆'.repeat(10 - rating);

                // цена: вход→выход
                const priceStr = model.price;
                
                // метка цензуры — крупно и понятно
                const censor = model.censored ? '' : ' ✦ БЕЗ ЦЕНЗУРЫ';

                // описание если есть
                const desc = model.description ? ` — ${model.description}` : '';

                option.textContent = `${stars} ${model.name} · ${priceStr}${censor}`;
                option.title = model.description || '';

                group.appendChild(option);
            });

            select.appendChild(group);
        });
    });
}

// ====================================================
// ЗАГРУЗКА БОТОВ
// ====================================================

async function loadBots() {
    try {
        const bots = await api('GET', '/api/bots');
        renderBots(bots);
    } catch (e) {}
}

function renderBots(bots) {
    const grid = document.getElementById('botsGrid');
    const empty = document.getElementById('emptyState');

    if (bots.length === 0) {
        grid.innerHTML = '';
        empty.style.display = 'block';
        return;
    }

    empty.style.display = 'none';

    grid.innerHTML = bots.map(bot => {
        const active = bot.is_active;
        const tg = bot.telegram_connected;
        const users = bot.stats?.total_users || 0;
        const messages = bot.stats?.total_messages || 0;

        return `
            <div class="bot-card" onclick="openEditModal('${bot.bot_id}')">
                <div class="bot-card-header">
                    <div class="bot-card-name">${escapeHtml(bot.name)}</div>
                    <div class="bot-status ${active ? 'online' : 'offline'}">
                        ${active ? '● Active' : '○ Off'}
                    </div>
                </div>
                <div class="bot-card-model">${escapeHtml(bot.model)}</div>
                <div class="bot-card-stats">
                    <span>👥 ${users}</span>
                    <span>💬 ${messages}</span>
                    <span>${tg ? '🔵 TG' : bot.has_token ? '⚪ TG' : ''}</span>
                </div>
                <div style="margin-top:12px; display:flex; gap:8px; flex-wrap:wrap;">
                    ${active
                        ? `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); stopBot('${bot.bot_id}')">⏹ Стоп</button>
                           <a class="btn btn-primary btn-sm" href="/chat/${bot.bot_id}" target="_blank" onclick="event.stopPropagation()">💬 Чат</a>
                           <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openKnowledge('${bot.bot_id}')">📚 Знания</button>
                           ${bot.has_token && !tg
                               ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); startTelegram('${bot.bot_id}')">🔵 TG</button>`
                               : ''
                           }
                           ${tg
                               ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); stopTelegram('${bot.bot_id}')">⏹ TG</button>`
                               : ''
                           }`
                        : `<button class="btn btn-success btn-sm" onclick="event.stopPropagation(); startBot('${bot.bot_id}')">▶ Запустить</button>`
                    }
                </div>
            </div>
        `;
    }).join('');
}

// ====================================================
// СОЗДАНИЕ БОТА
// ====================================================

function openCreateModal() {
    document.getElementById('newName').value = '';
    document.getElementById('newToken').value = '';
    document.getElementById('newApiKey').value = '';
    document.getElementById('newPrompt').value = 'Ты — полезный AI ассистент.';
    openModal('createModal');
}

async function createBot() {
    const name = document.getElementById('newName').value.trim();
    const token = document.getElementById('newToken').value.trim();
    const apiKey = document.getElementById('newApiKey').value.trim();
    const model = document.getElementById('newModel').value;
    const prompt = document.getElementById('newPrompt').value.trim();

    if (!name) return toast('Введите имя бота', 'error');
    if (!apiKey) return toast('Введите API ключ', 'error');

    try {
        await api('POST', '/api/bots', {
            name, bot_token: token, api_key: apiKey, model, system_prompt: prompt
        });
        toast('Бот создан! ✅', 'success');
        closeModal('createModal');
        loadBots();
    } catch (e) {}
}

// ====================================================
// РЕДАКТИРОВАНИЕ БОТА
// ====================================================

async function openEditModal(botId) {
    currentBotId = botId;
    try {
        const data = await api('GET', `/api/bots/${botId}`);
        const config = data.config;

        document.getElementById('editTitle').textContent = `✏️ ${config.name}`;
        document.getElementById('editName').value = config.name || '';
        document.getElementById('editToken').value = config.bot_token || '';
        document.getElementById('editApiKey').value = config.api_key || '';
        document.getElementById('editModel').value = config.model || '';
        document.getElementById('editPrompt').value = config.system_prompt || '';
        document.getElementById('editMaxHistory').value = config.max_history || 20;
        document.getElementById('editGroups').checked = config.enable_groups || false;
        document.getElementById('editWebChat').checked = config.enable_web_chat || false;
        document.getElementById('editFreeMessages').value = config.free_messages || 20;
        document.getElementById('editMsgPerPurchase').value = config.messages_per_purchase || 50;
        document.getElementById('editStarsPrice').value = config.stars_price || 50;
        document.getElementById('webChatLink').href = `/chat/${botId}`;

        switchTab('settings');
        loadUsersTab(botId);
        loadStatsTab(botId);
        loadPaymentsTab(botId);
        openModal('editModal');
    } catch (e) {}
}

async function saveBot() {
    if (!currentBotId) return;

    const updates = {
        name: document.getElementById('editName').value.trim(),
        bot_token: document.getElementById('editToken').value.trim(),
        api_key: document.getElementById('editApiKey').value.trim(),
        model: document.getElementById('editModel').value,
        system_prompt: document.getElementById('editPrompt').value.trim(),
        max_history: parseInt(document.getElementById('editMaxHistory').value) || 20,
        enable_groups: document.getElementById('editGroups').checked,
        enable_web_chat: document.getElementById('editWebChat').checked,
        free_messages: parseInt(document.getElementById('editFreeMessages').value) || 20,
        messages_per_purchase: parseInt(document.getElementById('editMsgPerPurchase').value) || 50,
        stars_price: parseInt(document.getElementById('editStarsPrice').value) || 50
    };

    try {
        await api('PUT', `/api/bots/${currentBotId}`, updates);
        toast('Сохранено! ✅', 'success');
        loadBots();
    } catch (e) {}
}

// ====================================================
// УПРАВЛЕНИЕ БОТОМ
// ====================================================

async function startBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/start`);
        toast('Бот запущен! 🟢', 'success');
        loadBots();
    } catch (e) {}
}

async function stopBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/stop`);
        toast('Бот остановлен 🔴', 'info');
        loadBots();
    } catch (e) {}
}

async function restartBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/restart`);
        toast('Бот перезапущен 🔄', 'success');
        loadBots();
    } catch (e) {}
}

// ====================================================
// ТАБ: ЮЗЕРЫ
// ====================================================

async function loadUsersTab(botId) {
    const container = document.getElementById('usersContent');
    try {
        const users = await api('GET', `/api/bots/${botId}/users`);
        if (users.length === 0) {
            container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Пока нет юзеров</p>';
            return;
        }

        // сохраняем botId в глобальную переменную для тумблеров
        window._usersBotId = botId;

        container.innerHTML = `
            <table class="users-table">
                <thead><tr><th>ID</th><th>Сообщений</th><th>Куплено</th><th>VIP</th><th>Последний визит</th><th></th></tr></thead>
                <tbody>
                    ${users.map(u => `
                        <tr>
                            <td>${u.user_id}</td>
                            <td>${u.messages_used}</td>
                            <td>${u.messages_bought}</td>
                            <td>
                                <label class="toggle">
                                    <input type="checkbox" ${u.is_vip ? 'checked' : ''}
                                           onchange="toggleVip(${u.user_id}, this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </td>
                            <td style="font-size:12px; color:#8b8b8b;">${u.last_seen || '—'}</td>
                            <td><button class="btn btn-danger btn-sm"
                                        onclick="clearUser(${u.user_id})">🗑️</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
    } catch (e) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть юзеров</p>';
    }
}

async function toggleVip(userId, isVip) {
    // берём botId из currentBotId (модалка редактирования)
    const botId = currentBotId;
    if (!botId) return toast('Нет активного бота', 'error');

    try {
        await api('POST', `/api/bots/${botId}/vip`, { user_id: userId, is_vip: isVip });
        toast(isVip ? 'VIP включён 👑' : 'VIP снят', 'success');
        loadUsersTab(botId);
    } catch (e) {
        loadUsersTab(botId);
    }
}

async function clearUser(userId) {
    const botId = currentBotId;
    if (!botId) return;
    if (!confirm(`Удалить все данные юзера ${userId}?`)) return;

    try {
        await api('DELETE', `/api/bots/${botId}/users/${userId}`);
        toast('Юзер сброшен 🗑️', 'success');
        loadUsersTab(botId);
    } catch (e) {}
}

// ====================================================
// ТАБ: СТАТИСТИКА
// ====================================================

async function loadStatsTab(botId) {
    const container = document.getElementById('statsGrid');
    try {
        const stats = await api('GET', `/api/bots/${botId}/stats`);
        container.innerHTML = `
            <div class="stat-card"><div class="stat-value">${stats.total_users}</div><div class="stat-label">Юзеров</div></div>
            <div class="stat-card"><div class="stat-value">${stats.total_messages}</div><div class="stat-label">Сообщений</div></div>
            <div class="stat-card"><div class="stat-value">${stats.paying_users}</div><div class="stat-label">Платящих</div></div>
            <div class="stat-card"><div class="stat-value">${stats.total_revenue_stars} ⭐</div><div class="stat-label">Доход</div></div>
            <div class="stat-card"><div class="stat-value">${stats.vip_count}</div><div class="stat-label">VIP</div></div>`;
    } catch (e) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть статистику</p>';
    }
}

// ====================================================
// ТАБ: ПЛАТЕЖИ
// ====================================================

async function loadPaymentsTab(botId) {
    const container = document.getElementById('paymentsTable');
    try {
        const payments = await api('GET', `/api/bots/${botId}/payments`);
        if (payments.length === 0) {
            container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Платежей пока нет</p>';
            return;
        }
        container.innerHTML = `
            <table class="users-table">
                <thead><tr><th>Юзер</th><th>Сумма</th><th>Сообщений</th><th>Источник</th><th>Дата</th></tr></thead>
                <tbody>
                    ${payments.map(p => `
                        <tr>
                            <td>${p.user_id}</td><td>${p.amount} ⭐</td><td>+${p.messages}</td>
                            <td>${p.source}</td><td style="font-size:12px; color:#8b8b8b;">${p.timestamp}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>`;
    } catch (e) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть платежи</p>';
    }
}

// ====================================================
// ОПАСНЫЕ ДЕЙСТВИЯ
// ====================================================

async function clearHistory() {
    if (!currentBotId) return;
    if (!confirm('Удалить ВСЮ историю сообщений?')) return;
    try { await api('DELETE', `/api/bots/${currentBotId}/history`); toast('История очищена 🗑️', 'success'); } catch (e) {}
}

async function resetBot() {
    if (!currentBotId) return;
    if (!confirm('ПОЛНЫЙ СБРОС: удалить историю, юзеров, платежи?')) return;
    if (!confirm('Вы уверены? Это необратимо!')) return;
    try { await api('DELETE', `/api/bots/${currentBotId}/reset`); toast('Бот сброшен 🗑️', 'success'); } catch (e) {}
}

async function deleteBot() {
    if (!currentBotId) return;
    if (!confirm('УДАЛИТЬ бота и ВСЕ его данные навсегда?')) return;
    if (!confirm('Точно удалить? Это необратимо!')) return;
    try {
        await api('DELETE', `/api/bots/${currentBotId}`);
        toast('Бот удалён 🗑️', 'success');
        closeModal('editModal');
        loadBots();
    } catch (e) {}
}

// ====================================================
// МОДАЛКИ
// ====================================================

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) e.target.classList.remove('active');
});
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
});

// ====================================================
// ТАБЫ
// ====================================================

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelectorAll('.tab').forEach(t => {
        if (t.onclick && t.onclick.toString().includes(tabName)) t.classList.add('active');
    });
}

// ====================================================
// ТОСТЫ
// ====================================================

function toast(message, type = 'info') {
    const container = document.getElementById('toasts');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.3s';
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

// ====================================================
// УТИЛИТЫ
// ====================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ====================================================
// TELEGRAM
// ====================================================

async function startTelegram(botId) {
    try { await api('POST', `/api/bots/${botId}/telegram/start`); toast('Telegram подключён 🔵', 'success'); loadBots(); } catch (e) {}
}
async function stopTelegram(botId) {
    try { await api('POST', `/api/bots/${botId}/telegram/stop`); toast('Telegram отключён', 'info'); loadBots(); } catch (e) {}
}

// ====================================================
// БАЗА ЗНАНИЙ (RAG)
// ====================================================

let knowledgeBotId = null;

async function openKnowledge(botId) {
    knowledgeBotId = botId;
    document.getElementById('knowledgeTitle').textContent = '📚 База знаний';
    openModal('knowledgeModal');
    await loadKnowledge();
}

async function loadKnowledge() {
    if (!knowledgeBotId) return;
    try {
        const data = await api('GET', `/api/bots/${knowledgeBotId}/knowledge`);
        renderKnowledge(data);
    } catch (e) {
        document.getElementById('knowledgeList').innerHTML = '<p style="color:#f85149;">Бот не активен. Сначала запустите.</p>';
    }
}

function renderKnowledge(data) {
    const list = document.getElementById('knowledgeList');
    if (!data.files || data.files.length === 0) {
        list.innerHTML = `<div style="text-align:center; color:#555; padding:20px;"><p>📭 База знаний пуста</p><p style="font-size:12px; margin-top:8px;">Загрузите файлы или добавьте текст</p></div>`;
        return;
    }
    list.innerHTML = `
        <div style="margin-bottom:8px; color:#8b8b8b; font-size:12px;">📊 ${data.total_files} файлов, ${data.total_chunks} чанков</div>
        ${data.files.map(f => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#1a1a1a; border-radius:8px; margin-bottom:4px;">
                <div><span style="color:#e0e0e0; font-size:13px;">📄 ${escapeHtml(f.name)}</span><span style="color:#555; font-size:11px; margin-left:8px;">${formatFileSize(f.size)} · ${f.chunks} чанков</span></div>
                <button class="btn btn-danger btn-sm" onclick="deleteKnowledgeFile('${escapeHtml(f.name)}')">✕</button>
            </div>
        `).join('')}`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function triggerFileUpload() { document.getElementById('knowledgeFileInput').click(); }

async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files.length) return;
    for (const file of files) {
        const base64 = await fileToBase64(file);
        try {
            const result = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/file`, { filename: file.name, content_base64: base64 });
            if (result.ok) toast(`✅ ${file.name}: ${result.chunks} чанков`, 'success');
            else toast(`❌ ${file.name}: ${result.error}`, 'error');
        } catch (e) {}
    }
    event.target.value = '';
    await loadKnowledge();
}

async function handleDrop(event) {
    const files = event.dataTransfer.files;
    if (!files.length) return;
    for (const file of files) {
        const base64 = await fileToBase64(file);
        try {
            const result = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/file`, { filename: file.name, content_base64: base64 });
            if (result.ok) toast(`✅ ${file.name}: ${result.chunks} чанков`, 'success');
            else toast(`❌ ${file.name}: ${result.error}`, 'error');
        } catch (e) {}
    }
    await loadKnowledge();
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function addKnowledgeText() {
    const name = document.getElementById('knowledgeTextName').value.trim();
    const text = document.getElementById('knowledgeTextContent').value.trim();
    if (!name) return toast('Введите название', 'error');
    if (!text) return toast('Введите текст', 'error');
    try {
        const result = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/text`, { name, text });
        if (result.ok) {
            toast(`✅ ${name}: ${result.chunks} чанков`, 'success');
            document.getElementById('knowledgeTextName').value = '';
            document.getElementById('knowledgeTextContent').value = '';
            await loadKnowledge();
        } else toast(`❌ ${result.error}`, 'error');
    } catch (e) {}
}

async function deleteKnowledgeFile(filename) {
    if (!confirm(`Удалить ${filename} из базы знаний?`)) return;
    try { await api('DELETE', `/api/bots/${knowledgeBotId}/knowledge/${filename}`); toast('Удалено', 'info'); await loadKnowledge(); } catch (e) {}
}

async function clearKnowledge() {
    if (!confirm('Очистить всю базу знаний?')) return;
    try { await api('DELETE', `/api/bots/${knowledgeBotId}/knowledge`); toast('База знаний очищена', 'info'); await loadKnowledge(); } catch (e) {}
}

async function testSearch() {
    const query = document.getElementById('knowledgeSearchQuery').value.trim();
    if (!query) return;
    try {
        const data = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/search`, { query });
        const results = document.getElementById('knowledgeSearchResults');
        if (!data.results || data.results.length === 0) {
            results.innerHTML = '<p style="color:#555;">Ничего не найдено</p>';
            return;
        }
        results.innerHTML = data.results.map((r, i) => `
            <div style="padding:8px; background:#1a1a1a; border-radius:8px; margin-bottom:4px;">
                <div style="font-size:11px; color:#646cff; margin-bottom:4px;">#${i + 1} · ${escapeHtml(r.source)} · score: ${r.score.toFixed(3)}</div>
                <div style="font-size:13px; color:#ccc;">${escapeHtml(r.text).substring(0, 200)}</div>
            </div>
        `).join('');
    } catch (e) {}
}