/**
 * Bot Factory v2.0 — логика панели управления
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

    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
    return data;
}

// тихий API — не показывает ошибки (для фоновых запросов)
async function apiSilent(method, url, body = null) {
    try {
        return await api(method, url, body);
    } catch (e) {
        return null;
    }
}

// ====================================================
// МОДЕЛИ — автоматически с OpenRouter
// ====================================================

async function loadModels() {
    try {
        models = await api('GET', '/api/models');
        fillModelSelects();
    } catch (e) {
        models = [{ id: 'mistralai/mistral-nemo', name: 'Mistral Nemo', category: 'psychology', rating: 6, price: '$0.03→$0.03', censored: false, prompt_price: 0.03 }];
        fillModelSelects();
    }
}

function fillModelSelects() {
    const selects = ['newModel', 'editModel'];

    const categoryOrder = [
        { key: 'uncensored', label: '🔥 Без цензуры' },
        { key: 'psychology', label: '💬 Собеседник / Универсальная' },
        { key: 'code', label: '💻 Код / Программирование' },
        { key: 'creative', label: '🎭 Ролеплей / Креатив / Истории' },
        { key: 'analytics', label: '📊 Аналитика / Документы / RAG' },
        { key: 'reasoning', label: '🧮 Логика / Математика / Reasoning' },
    ];

    // группируем
    const grouped = {};
    models.forEach(m => {
        const cat = m.category || 'psychology';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(m);
    });

    // сортируем внутри категории
    Object.keys(grouped).forEach(cat => {
        grouped[cat].sort((a, b) => {
            if ((b.rating || 0) !== (a.rating || 0)) return (b.rating || 0) - (a.rating || 0);
            return (a.prompt_price || 0) - (b.prompt_price || 0);
        });
    });

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;

        const oldValue = select.value;
        select.innerHTML = '';

        categoryOrder.forEach(cat => {
            const items = grouped[cat.key];
            if (!items || items.length === 0) return;

            const group = document.createElement('optgroup');
            group.label = `${cat.label} (${items.length})`;

            items.forEach(model => {
                const option = document.createElement('option');
                option.value = model.id;

                const censor = model.censored ? '' : ' 🔓';
                option.textContent = `${model.name} · ${model.price}${censor}`;
                option.title = model.description || '';

                group.appendChild(option);
            });

            select.appendChild(group);
        });

        // восстанавливаем выбранное значение
        if (oldValue) select.value = oldValue;
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
        const provider = bot.provider || 'openrouter';

        return `
            <div class="bot-card" onclick="openEditModal('${bot.bot_id}')">
                <div class="bot-card-header">
                    <div class="bot-card-name">${escapeHtml(bot.name)}</div>
                    <div class="bot-status ${active ? 'online' : 'offline'}">
                        ${active ? '● Active' : '○ Off'}
                    </div>
                </div>
                <div class="bot-card-model">${escapeHtml(bot.model)}</div>
                <div class="bot-card-provider" style="font-size:11px; color:#555; margin-top:2px;">via ${provider}</div>
                <div class="bot-card-stats">
                    <span>👥 ${users}</span>
                    <span>💬 ${messages}</span>
                    <span>${tg ? '🔵 TG' : bot.has_token ? '⚪ TG' : ''}</span>
                </div>
                <div style="margin-top:12px; display:flex; gap:6px; flex-wrap:wrap;">
                    ${active
                        ? `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); stopBot('${bot.bot_id}')">⏹</button>
                           <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); openTerminal('${bot.bot_id}', '${escapeHtml(bot.name)}')">🖥️ Чат</button>
                           <a class="btn btn-ghost btn-sm" href="/chat/${bot.bot_id}" target="_blank" onclick="event.stopPropagation()">🔗</a>
                           <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openFiles('${bot.bot_id}', '${escapeHtml(bot.name)}')">📁</button>
                           <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openKnowledge('${bot.bot_id}')">📚</button>
                           ${bot.has_token && !tg
                               ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); startTelegram('${bot.bot_id}')">🔵</button>`
                               : ''}
                           ${tg
                               ? `<button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); stopTelegram('${bot.bot_id}')">⏹TG</button>`
                               : ''}`
                        : `<button class="btn btn-success btn-sm" onclick="event.stopPropagation(); startBot('${bot.bot_id}')">▶ Запустить</button>
                           <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); openFiles('${bot.bot_id}', '${escapeHtml(bot.name)}')">📁</button>`
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
    document.getElementById('newModelManual').value = '';
    document.getElementById('newPrompt').value = 'Ты — полезный AI ассистент.';
    document.getElementById('newProvider').value = 'openrouter';
    document.getElementById('newCustomUrl').value = '';
    onProviderChange('new');
    openModal('createModal');
}

async function createBot() {
    const name = document.getElementById('newName').value.trim();
    const token = document.getElementById('newToken').value.trim();
    const apiKey = document.getElementById('newApiKey').value.trim();
    const manualModel = document.getElementById('newModelManual').value.trim();
    const selectModel = document.getElementById('newModel').value;
    const model = manualModel || selectModel;
    const prompt = document.getElementById('newPrompt').value.trim();
    const provider = document.getElementById('newProvider').value;
    const customUrl = document.getElementById('newCustomUrl').value.trim();

    if (!name) return toast('Введите имя бота', 'error');
    if (!apiKey) return toast('Введите API ключ', 'error');

    try {
        await api('POST', '/api/bots', {
            name, bot_token: token, api_key: apiKey, model,
            system_prompt: prompt, provider, custom_base_url: customUrl
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
        document.getElementById('editPrompt').value = config.system_prompt || '';
        document.getElementById('editMaxHistory').value = config.max_history || 20;
        document.getElementById('editGroups').checked = config.enable_groups || false;
        document.getElementById('editWebChat').checked = config.enable_web_chat || false;
        document.getElementById('editFreeMessages').value = config.free_messages || 20;
        document.getElementById('editMsgPerPurchase').value = config.messages_per_purchase || 50;
        document.getElementById('editStarsPrice').value = config.stars_price || 50;
        document.getElementById('webChatLink').href = `/chat/${botId}`;

        // провайдер
        document.getElementById('editProvider').value = config.provider || 'openrouter';
        document.getElementById('editCustomUrl').value = config.custom_base_url || '';
        onProviderChange('edit');

        // модель из селекта
        const modelSelect = document.getElementById('editModel');
        modelSelect.value = config.model || '';

        // если модели нет в списке — вписываем в ручное поле
        if (modelSelect.value !== config.model) {
            document.getElementById('editModelManual').value = config.model || '';
        } else {
            document.getElementById('editModelManual').value = '';
        }

        // инструменты
        document.getElementById('editToolsEnabled').checked = config.tools_enabled !== false;
        document.getElementById('editAccessMode').value = config.access_mode || 'sandbox';
        document.getElementById('editWorkingDirectory').value = config.working_directory || '';
        document.getElementById('editMaxToolRounds').value = config.max_tool_rounds || 15;
        const perms = config.tool_permissions || {};
        const permDefaults = {execute_commands:true, write_files:true, delete_files:false, network:false, install_packages:false};
        ['execute_commands','write_files','delete_files','network','install_packages'].forEach(p => {
            const el = document.getElementById(`perm_${p}`);
            if (el) el.checked = perms[p] !== undefined ? perms[p] : (permDefaults[p] || false);
        });

        switchTab('settings');

        // загружаем табы тихо (не показываем ошибки если бот не запущен)
        loadUsersTab(botId);
        loadStatsTab(botId);
        loadPaymentsTab(botId);

        openModal('editModal');
    } catch (e) {
        toast('Не удалось загрузить бота', 'error');
    }
}

async function saveBot() {
    if (!currentBotId) return;

    const manualModel = document.getElementById('editModelManual').value.trim();
    const selectModel = document.getElementById('editModel').value;
    const model = manualModel || selectModel;

    const updates = {
        name: document.getElementById('editName').value.trim(),
        bot_token: document.getElementById('editToken').value.trim(),
        api_key: document.getElementById('editApiKey').value.trim(),
        model: model,
        system_prompt: document.getElementById('editPrompt').value.trim(),
        max_history: parseInt(document.getElementById('editMaxHistory').value) || 20,
        enable_groups: document.getElementById('editGroups').checked,
        enable_web_chat: document.getElementById('editWebChat').checked,
        free_messages: parseInt(document.getElementById('editFreeMessages').value) || 20,
        messages_per_purchase: parseInt(document.getElementById('editMsgPerPurchase').value) || 50,
        stars_price: parseInt(document.getElementById('editStarsPrice').value) || 50,
        provider: document.getElementById('editProvider').value,
        custom_base_url: document.getElementById('editCustomUrl').value.trim(),
        tools_enabled: document.getElementById('editToolsEnabled').checked,
        access_mode: document.getElementById('editAccessMode').value,
        working_directory: document.getElementById('editWorkingDirectory').value.trim(),
        max_tool_rounds: parseInt(document.getElementById('editMaxToolRounds').value) || 15,
        tool_permissions: {
            execute_commands: document.getElementById('perm_execute_commands').checked,
            write_files: document.getElementById('perm_write_files').checked,
            delete_files: document.getElementById('perm_delete_files').checked,
            network: document.getElementById('perm_network').checked,
            install_packages: document.getElementById('perm_install_packages').checked,
        },
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
// TELEGRAM
// ====================================================

async function startTelegram(botId) {
    try {
        await api('POST', `/api/bots/${botId}/telegram/start`);
        toast('Telegram подключён 🔵', 'success');
        loadBots();
    } catch (e) {}
}

async function stopTelegram(botId) {
    try {
        await api('POST', `/api/bots/${botId}/telegram/stop`);
        toast('Telegram отключён', 'info');
        loadBots();
    } catch (e) {}
}

// ====================================================
// ТАБ: ЮЗЕРЫ (тихая загрузка)
// ====================================================

async function loadUsersTab(botId) {
    const container = document.getElementById('usersContent');

    const users = await apiSilent('GET', `/api/bots/${botId}/users`);

    if (!users) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть юзеров</p>';
        return;
    }

    if (users.length === 0) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Пока нет юзеров</p>';
        return;
    }

    container.innerHTML = `
        <table class="users-table">
            <thead>
                <tr><th>ID</th><th>Сообщений</th><th>Куплено</th><th>VIP</th><th>Последний визит</th><th></th></tr>
            </thead>
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
                        <td><button class="btn btn-danger btn-sm" onclick="clearUser(${u.user_id})">🗑️</button></td>
                    </tr>
                `).join('')}
            </tbody>
        </table>`;
}

async function toggleVip(userId, isVip) {
    if (!currentBotId) return;
    try {
        await api('POST', `/api/bots/${currentBotId}/vip`, { user_id: userId, is_vip: isVip });
        toast(isVip ? 'VIP включён 👑' : 'VIP снят', 'success');
        loadUsersTab(currentBotId);
    } catch (e) {
        loadUsersTab(currentBotId);
    }
}

async function clearUser(userId) {
    if (!currentBotId) return;
    if (!confirm(`Удалить все данные юзера ${userId}?`)) return;
    try {
        await api('DELETE', `/api/bots/${currentBotId}/users/${userId}`);
        toast('Юзер сброшен 🗑️', 'success');
        loadUsersTab(currentBotId);
    } catch (e) {}
}

// ====================================================
// ТАБ: СТАТИСТИКА (тихая загрузка)
// ====================================================

async function loadStatsTab(botId) {
    const container = document.getElementById('statsGrid');

    const stats = await apiSilent('GET', `/api/bots/${botId}/stats`);

    if (!stats) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть статистику</p>';
        return;
    }

    container.innerHTML = `
        <div class="stat-card"><div class="stat-value">${stats.total_users || 0}</div><div class="stat-label">Юзеров</div></div>
        <div class="stat-card"><div class="stat-value">${stats.total_messages || 0}</div><div class="stat-label">Сообщений</div></div>
        <div class="stat-card"><div class="stat-value">${stats.paying_users || 0}</div><div class="stat-label">Платящих</div></div>
        <div class="stat-card"><div class="stat-value">${stats.total_revenue_stars || 0} ⭐</div><div class="stat-label">Доход</div></div>
        <div class="stat-card"><div class="stat-value">${stats.vip_count || 0}</div><div class="stat-label">VIP</div></div>`;
}

// ====================================================
// ТАБ: ПЛАТЕЖИ (тихая загрузка)
// ====================================================

async function loadPaymentsTab(botId) {
    const container = document.getElementById('paymentsTable');

    const payments = await apiSilent('GET', `/api/bots/${botId}/payments`);

    if (!payments) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Запустите бота чтобы увидеть платежи</p>';
        return;
    }

    if (payments.length === 0) {
        container.innerHTML = '<p style="color:#8b8b8b; font-size:13px;">Платежей пока нет</p>';
        return;
    }

    container.innerHTML = `
        <table class="users-table">
            <thead>
                <tr><th>Юзер</th><th>Сумма</th><th>Сообщений</th><th>Источник</th><th>Дата</th></tr>
            </thead>
            <tbody>
                ${payments.map(p => `
                    <tr>
                        <td>${p.user_id}</td>
                        <td>${p.amount} ⭐</td>
                        <td>+${p.messages}</td>
                        <td>${p.source}</td>
                        <td style="font-size:12px; color:#8b8b8b;">${p.timestamp}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>`;
}

// ====================================================
// ОПАСНЫЕ ДЕЙСТВИЯ
// ====================================================

async function clearHistory() {
    if (!currentBotId) return;
    if (!confirm('Удалить ВСЮ историю сообщений?')) return;
    try {
        await api('DELETE', `/api/bots/${currentBotId}/history`);
        toast('История очищена 🗑️', 'success');
    } catch (e) {}
}

async function resetBot() {
    if (!currentBotId) return;
    if (!confirm('ПОЛНЫЙ СБРОС: удалить историю, юзеров, платежи?')) return;
    if (!confirm('Вы уверены? Это необратимо!')) return;
    try {
        await api('DELETE', `/api/bots/${currentBotId}/reset`);
        toast('Бот сброшен 🗑️', 'success');
    } catch (e) {}
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

function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
    }
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    }
});

// ====================================================
// ТАБЫ
// ====================================================

function switchTab(tabName) {
    // деактивируем все табы и контент
    document.querySelectorAll('#editTabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));

    // активируем нужный контент
    const content = document.getElementById(`tab-${tabName}`);
    if (content) content.classList.add('active');

    // активируем кнопку таба
    document.querySelectorAll('#editTabs .tab').forEach(t => {
        if (t.dataset.tab === tabName) t.classList.add('active');
    });
}

// ====================================================
// ПРОВАЙДЕРЫ
// ====================================================

function onProviderChange(prefix) {
    const provider = document.getElementById(`${prefix}Provider`).value;
    const urlGroup = document.getElementById(`${prefix}CustomUrlGroup`);
    if (urlGroup) {
        urlGroup.style.display = (provider === 'custom') ? 'block' : 'none';
    }
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
    div.textContent = text || '';
    return div.innerHTML;
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
    const data = await apiSilent('GET', `/api/bots/${knowledgeBotId}/knowledge`);
    if (!data) {
        document.getElementById('knowledgeList').innerHTML = '<p style="color:#f85149;">Бот не активен. Сначала запустите.</p>';
        return;
    }
    renderKnowledge(data);
}

function renderKnowledge(data) {
    const list = document.getElementById('knowledgeList');
    if (!data.files || data.files.length === 0) {
        list.innerHTML = `<div style="text-align:center; color:#555; padding:20px;">
            <p>📭 База знаний пуста</p>
            <p style="font-size:12px; margin-top:8px;">Загрузите файлы или добавьте текст</p>
        </div>`;
        return;
    }
    list.innerHTML = `
        <div style="margin-bottom:8px; color:#8b8b8b; font-size:12px;">
            📊 ${data.total_files} файлов, ${data.total_chunks} чанков
        </div>
        ${data.files.map(f => `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#1a1a1a; border-radius:8px; margin-bottom:4px;">
                <div>
                    <span style="color:#e0e0e0; font-size:13px;">📄 ${escapeHtml(f.name)}</span>
                    <span style="color:#555; font-size:11px; margin-left:8px;">${formatFileSize(f.size)} · ${f.chunks} чанков</span>
                </div>
                <button class="btn btn-danger btn-sm" onclick="deleteKnowledgeFile('${escapeHtml(f.name)}')">✕</button>
            </div>
        `).join('')}`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function triggerFileUpload() {
    document.getElementById('knowledgeFileInput').click();
}

async function handleFileUpload(event) {
    const files = event.target.files;
    if (!files.length) return;
    for (const file of files) {
        const base64 = await fileToBase64(file);
        try {
            const result = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/file`, {
                filename: file.name, content_base64: base64
            });
            if (result.ok) toast(`✅ ${file.name}: ${result.chunks} чанков`, 'success');
            else toast(`❌ ${file.name}: ${result.error}`, 'error');
        } catch (e) {}
    }
    event.target.value = '';
    await loadKnowledge();
}

async function handleDrop(event) {
    event.preventDefault();
    const files = event.dataTransfer.files;
    if (!files.length) return;
    for (const file of files) {
        const base64 = await fileToBase64(file);
        try {
            const result = await api('POST', `/api/bots/${knowledgeBotId}/knowledge/file`, {
                filename: file.name, content_base64: base64
            });
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
        } else {
            toast(`❌ ${result.error}`, 'error');
        }
    } catch (e) {}
}

async function deleteKnowledgeFile(filename) {
    if (!confirm(`Удалить ${filename} из базы знаний?`)) return;
    try {
        await api('DELETE', `/api/bots/${knowledgeBotId}/knowledge/${filename}`);
        toast('Удалено', 'info');
        await loadKnowledge();
    } catch (e) {}
}

async function clearKnowledge() {
    if (!confirm('Очистить всю базу знаний?')) return;
    try {
        await api('DELETE', `/api/bots/${knowledgeBotId}/knowledge`);
        toast('База знаний очищена', 'info');
        await loadKnowledge();
    } catch (e) {}
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
                <div style="font-size:11px; color:#646cff; margin-bottom:4px;">
                    #${i + 1} · ${escapeHtml(r.source)} · score: ${r.score.toFixed(3)}
                </div>
                <div style="font-size:13px; color:#ccc;">
                    ${escapeHtml(r.text).substring(0, 200)}
                </div>
            </div>
        `).join('');
    } catch (e) {}
}

// ====================================================
// ТЕРМИНАЛ — чат с ботом в панели
// ====================================================

let terminalBotId = null;
let terminalUserId = Date.now(); // уникальный user_id для сессии

function openTerminal(botId, botName) {
    terminalBotId = botId;
    document.getElementById('terminalTitle').textContent = `🖥️ ${botName}`;
    document.getElementById('terminalMessages').innerHTML = `
        <div style="color:#3fb950; margin-bottom:12px;">
            ✨ Чат с ${escapeHtml(botName)} открыт
            <br><span style="color:#555;">Введите сообщение ниже</span>
        </div>`;
    document.getElementById('terminalInput').value = '';
    openModal('terminalModal');
    document.getElementById('terminalInput').focus();
}

async function terminalSend() {
    const input = document.getElementById('terminalInput');
    const msg = input.value.trim();
    if (!msg || !terminalBotId) return;

    input.value = '';
    const container = document.getElementById('terminalMessages');

    // добавляем сообщение юзера
    container.innerHTML += `<div style="color:#646cff; margin:8px 0;">▸ ${escapeHtml(msg)}</div>`;

    // индикатор
    const thinkId = 'think_' + Date.now();
    container.innerHTML += `<div id="${thinkId}" style="color:#555;">⏳ Думаю...</div>`;
    container.scrollTop = container.scrollHeight;

    try {
        const result = await api('POST', `/api/bots/${terminalBotId}/chat`, {
            message: msg,
            user_id: terminalUserId
        });

        // удаляем индикатор
        const thinkEl = document.getElementById(thinkId);
        if (thinkEl) thinkEl.remove();

        if (result.ok || result.reply) {
            const reply = result.reply || result.error || 'пустой ответ';
            container.innerHTML += `<div style="color:#e0e0e0; margin:4px 0 12px; white-space:pre-wrap;">${escapeHtml(reply)}</div>`;
        } else {
            container.innerHTML += `<div style="color:#f85149; margin:4px 0 12px;">❌ ${escapeHtml(result.error || 'Ошибка')}</div>`;
        }
    } catch (e) {
        const thinkEl = document.getElementById(thinkId);
        if (thinkEl) thinkEl.remove();
        container.innerHTML += `<div style="color:#f85149;">❌ ${escapeHtml(e.message)}</div>`;
    }

    container.scrollTop = container.scrollHeight;
    input.focus();
}

function terminalClear() {
    document.getElementById('terminalMessages').innerHTML = `
        <div style="color:#555;">🗑️ Экран очищен</div>`;
}


// ====================================================
// ФАЙЛОВЫЙ МЕНЕДЖЕР
// ====================================================

let filesBotId = null;
let filesCurrentPath = '';
let filesSystemMode = false;
let filesEditingPath = '';

function openFiles(botId, botName) {
    filesBotId = botId;
    filesCurrentPath = '';
    filesSystemMode = false;
    document.getElementById('filesTitle').textContent = `📁 ${botName}`;
    openModal('filesModal');
    filesLoad();
}

function filesToggleSystem() {
    filesSystemMode = !filesSystemMode;
    filesCurrentPath = '';
    document.getElementById('filesTitle').textContent = filesSystemMode ? '🔧 Системные файлы (read-only)' : '📁 Файлы бота';
    filesLoad();
}

async function filesLoad() {
    const list = document.getElementById('filesList');
    document.getElementById('filesPath').textContent = filesCurrentPath || '/';

    let url;
    if (filesSystemMode) {
        url = `/api/system/files?path=${encodeURIComponent(filesCurrentPath)}`;
    } else {
        url = `/api/bots/${filesBotId}/files?path=${encodeURIComponent(filesCurrentPath)}`;
    }

    const data = await apiSilent('GET', url);
    if (!data) {
        list.innerHTML = '<p style="color:#f85149; padding:16px;">Не удалось загрузить</p>';
        return;
    }

    if (data.type === 'file') {
        // открыли файл — показываем в редакторе
        fileEditorOpen(data.name, data.content, data.readonly || filesSystemMode);
        return;
    }

    const items = data.items || [];

    if (items.length === 0) {
        list.innerHTML = '<p style="color:#555; padding:16px; text-align:center;">📭 Пусто</p>';
        return;
    }

    list.innerHTML = items.map(item => {
        const icon = item.type === 'dir' ? '📁' : getFileIcon(item.ext);
        const size = item.type === 'file' ? `<span style="color:#555; font-size:11px;">${formatFileSize(item.size)}</span>` : '';
        const clickAction = item.type === 'dir'
            ? `filesNavigate('${escapeHtml(item.path)}')`
            : `filesOpenFile('${escapeHtml(item.path)}')`;

        return `
            <div onclick="${clickAction}" style="
                display:flex; justify-content:space-between; align-items:center;
                padding:10px 16px; border-bottom:1px solid #1a1a1a;
                cursor:pointer; transition:background 0.15s;
            " onmouseenter="this.style.background='#1a1a2a'" onmouseleave="this.style.background='transparent'">
                <div>
                    <span style="margin-right:8px;">${icon}</span>
                    <span style="color:#e0e0e0; font-size:13px;">${escapeHtml(item.name)}</span>
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    ${size}
                    ${!filesSystemMode && item.type === 'file' ? `<button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); filesDeleteFile('${escapeHtml(item.path)}', '${escapeHtml(item.name)}')">✕</button>` : ''}
                </div>
            </div>`;
    }).join('');
}

function getFileIcon(ext) {
    const icons = {
        '.py': '🐍', '.js': '📜', '.json': '📋', '.html': '🌐', '.css': '🎨',
        '.md': '📝', '.txt': '📄', '.csv': '📊', '.log': '📃', '.db': '💾',
        '.yml': '⚙️', '.yaml': '⚙️', '.sh': '🔧', '.bat': '🔧',
    };
    return icons[ext] || '📄';
}

function filesNavigate(path) {
    filesCurrentPath = path;
    filesLoad();
}

function filesGoUp() {
    if (!filesCurrentPath) return;
    const parts = filesCurrentPath.split('/');
    parts.pop();
    filesCurrentPath = parts.join('/');
    filesLoad();
}

async function filesOpenFile(path) {
    let url;
    if (filesSystemMode) {
        url = `/api/system/files?path=${encodeURIComponent(path)}`;
    } else {
        url = `/api/bots/${filesBotId}/files?path=${encodeURIComponent(path)}`;
    }

    const data = await apiSilent('GET', url);
    if (!data || data.type === 'binary') {
        toast('Бинарный файл — нельзя открыть', 'info');
        return;
    }

    filesEditingPath = path;
    fileEditorOpen(data.name, data.content, data.readonly || filesSystemMode);
}

function fileEditorOpen(name, content, readonly) {
    document.getElementById('fileEditor').style.display = 'block';
    document.getElementById('fileEditorName').textContent = readonly ? `${name} (только чтение)` : name;
    document.getElementById('fileEditorContent').value = content;
    document.getElementById('fileEditorContent').readOnly = readonly;
    document.getElementById('fileEditorSaveBtn').style.display = readonly ? 'none' : 'inline-flex';
}

function fileEditorClose() {
    document.getElementById('fileEditor').style.display = 'none';
    filesEditingPath = '';
}

async function fileEditorSave() {
    if (!filesEditingPath || !filesBotId) return;
    const content = document.getElementById('fileEditorContent').value;

    try {
        await api('PUT', `/api/bots/${filesBotId}/files`, {
            path: filesEditingPath,
            content: content
        });
        toast('Файл сохранён ✅', 'success');
    } catch (e) {}
}

async function filesDeleteFile(path, name) {
    if (!confirm(`Удалить ${name}?`)) return;
    try {
        await api('DELETE', `/api/bots/${filesBotId}/files`, { path });
        toast(`${name} удалён`, 'info');
        filesLoad();
    } catch (e) {}
}

function filesNewFile() {
    const name = prompt('Имя файла (например: notes.txt):');
    if (!name) return;
    const path = filesCurrentPath ? `${filesCurrentPath}/${name}` : name;
    filesEditingPath = path;
    fileEditorOpen(name, '', false);
}