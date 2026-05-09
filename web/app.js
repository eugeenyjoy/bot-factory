/**
 * Bot Factory v2.1 — панель управления
 * Фичи: searchable модели, избранное, локальные модели (Ollama)
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
        method,
        headers: { 'Content-Type': 'application/json' }
    };
    if (body) options.body = JSON.stringify(body);
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
    return data;
}

async function apiSilent(method, url, body = null) {
    try { return await api(method, url, body); }
    catch (e) { return null; }
}

// ====================================================
// МОДЕЛИ — searchable dropdown + избранное + локальные
// ====================================================

const CATEGORY_ORDER = [
    { key: '_favorites',  label: '⭐ Избранное' },
    { key: '_local',      label: '🖥️ Локальные (Ollama)' },
    { key: 'uncensored',  label: '🔥 Без цензуры' },
    { key: 'psychology',  label: '💬 Собеседник / Универсальная' },
    { key: 'code',        label: '💻 Код / Программирование' },
    { key: 'creative',    label: '🎭 Ролеплей / Креатив / Истории' },
    { key: 'analytics',   label: '📊 Аналитика / Документы / RAG' },
    { key: 'reasoning',   label: '🧮 Логика / Математика / Reasoning' },
];

// каталог загружается с сервера динамически
let ollamaCatalog = [];
let ollamaCatalogLoading = false;
let ollamaCatalogTimeout = null;

let modelSearchHighlight = -1;
let modelSearchFiltered = [];
let modelSearchActivePrefix = null;
let favoriteModels = new Set();
let localModels = [];        // скачанные модели Ollama
let ollamaAvailable = null;  // null = не проверяли, true/false
let ollamaPulling = {};       // { modelId: progress% }
let hfSearchResults = [];    // результаты поиска HuggingFace
let hfSearchLoading = false;
let hfSearchQuery = '';
let hfSearchTimeout = null;

function loadFavorites() {
    try {
        const saved = localStorage.getItem('bf_favorite_models');
        if (saved) {
            const arr = JSON.parse(saved);
            if (Array.isArray(arr)) favoriteModels = new Set(arr);
        }
    } catch (e) { favoriteModels = new Set(); }
}

function saveFavorites() {
    try { localStorage.setItem('bf_favorite_models', JSON.stringify([...favoriteModels])); }
    catch (e) {}
}

function toggleFavorite(modelId) {
    if (favoriteModels.has(modelId)) favoriteModels.delete(modelId);
    else favoriteModels.add(modelId);
    saveFavorites();
    if (modelSearchActivePrefix) {
        const input = document.getElementById(`${modelSearchActivePrefix}ModelSearch`);
        const query = (input.value || '').toLowerCase().trim();
        renderModelDropdown(modelSearchActivePrefix, query);
    }
}

async function loadModels() {
    loadFavorites();
    try { models = await api('GET', '/api/models'); }
    catch (e) {
        models = [{ id: 'mistralai/mistral-nemo', name: 'Mistral Nemo',
                     category: 'psychology', rating: 6, price: '$0.03→$0.03',
                     censored: false, prompt_price: 0.03 }];
    }
    models.sort((a, b) => {
        if ((b.rating || 0) !== (a.rating || 0)) return (b.rating || 0) - (a.rating || 0);
        return (a.prompt_price || 0) - (b.prompt_price || 0);
    });
    // проверяем Ollama в фоне
    checkOllama();
}

// ====================================================
// OLLAMA — локальные модели
// ====================================================

async function checkOllama() {
    try {
        const data = await apiSilent('GET', '/api/local/status');
        if (data && data.available) {
            ollamaAvailable = true;
            localModels = data.models || [];
        } else {
            ollamaAvailable = false;
            localModels = [];
        }
    } catch (e) {
        ollamaAvailable = false;
        localModels = [];
    }
}

function isLocalModelInstalled(modelId) {
    return localModels.some(m =>
        m.name === modelId ||
        m.name === modelId.split(':')[0] ||
        m.name.startsWith(modelId)
    );
}

async function pullLocalModel(modelId) {
    if (ollamaPulling[modelId]) return;
    ollamaPulling[modelId] = 0;
    toast(`⬇️ Скачивание ${modelId}...`, 'info');

    // перерисовываем
    if (modelSearchActivePrefix) {
        const input = document.getElementById(`${modelSearchActivePrefix}ModelSearch`);
        renderModelDropdown(modelSearchActivePrefix, (input.value || '').toLowerCase().trim());
    }

    try {
        const result = await api('POST', '/api/local/pull', { model: modelId });
        if (result.ok) {
            toast(`✅ ${modelId} скачана!`, 'success');
            await checkOllama();
        } else {
            toast(`❌ Ошибка: ${result.error || 'unknown'}`, 'error');
        }
    } catch (e) {
        toast(`❌ Ошибка скачивания: ${e.message}`, 'error');
    }

    delete ollamaPulling[modelId];
    if (modelSearchActivePrefix) {
        const input = document.getElementById(`${modelSearchActivePrefix}ModelSearch`);
        renderModelDropdown(modelSearchActivePrefix, (input.value || '').toLowerCase().trim());
    }
}

async function deleteLocalModel(modelId) {
    if (!confirm(`Удалить локальную модель ${modelId}?`)) return;
    try {
        const result = await api('DELETE', '/api/local/model', { model: modelId });
        if (result.ok) {
            toast(`🗑️ ${modelId} удалена`, 'info');
            await checkOllama();
        } else {
            toast(`❌ ${result.error}`, 'error');
        }
    } catch (e) {
        toast(`❌ ${e.message}`, 'error');
    }
    if (modelSearchActivePrefix) {
        const input = document.getElementById(`${modelSearchActivePrefix}ModelSearch`);
        renderModelDropdown(modelSearchActivePrefix, (input.value || '').toLowerCase().trim());
    }
}

// ====================================================
// DROPDOWN — открытие/закрытие/фильтр
// ====================================================

let dropdownCloseTimer = null;
let dropdownInteracting = false;
let dropdownPendingRefresh = null;

function modelSearchOpen(prefix) {
    if (dropdownCloseTimer) { clearTimeout(dropdownCloseTimer); dropdownCloseTimer = null; }
    modelSearchActivePrefix = prefix;
    modelSearchHighlight = -1;
    modelSearchFilter(prefix);
    document.getElementById(`${prefix}ModelDropdown`).classList.add('open');
}

function modelSearchClose(prefix) {
    document.getElementById(`${prefix}ModelDropdown`).classList.remove('open');
    if (modelSearchActivePrefix === prefix) {
        modelSearchActivePrefix = null;
    }
}

function modelSearchCloseDelayed(prefix) {
    dropdownCloseTimer = setTimeout(() => modelSearchClose(prefix), 300);
}

function modelSearchCancelClose() {
    if (dropdownCloseTimer) { clearTimeout(dropdownCloseTimer); dropdownCloseTimer = null; }
}

function modelSearchFilter(prefix) {
    const input = document.getElementById(`${prefix}ModelSearch`);
    const query = (input.value || '').toLowerCase().trim();

    // облачные модели
    let allModels = [...models];

    // добавляем скачанные локальные
    if (ollamaAvailable) {
        localModels.forEach(lm => {
            const name = lm.name || lm.model;
            if (!allModels.find(m => m.id === name)) {
                allModels.push({
                    id: name, name: name,
                    category: '_local', rating: 5,
                    price: 'бесплатно', censored: false,
                    prompt_price: 0, _local: true,
                    _localInfo: { size: lm.size ? (lm.size/1e9).toFixed(1)+'GB' : '?', ram: '?', vram: '?' }
                });
            }
        });
    }

    // добавляем результаты поиска из каталога Ollama
    if (ollamaAvailable || ollamaAvailable === null) {
        ollamaCatalog.forEach(cat => {
            // tags — это объект { tag: {size, ram, vram, ctx} }
            const tagEntries = cat.tags ? Object.entries(cat.tags) : [];
            tagEntries.forEach(([tag, info]) => {
                const modelId = tag === 'latest' ? cat.model : `${cat.model}:${tag}`;
                if (!allModels.find(m => m.id === modelId)) {
                    const sizeStr = formatSizeCompact(info.size);
                    const ramStr = formatSizeCompact(info.ram);
                    const vramStr = formatSizeCompact(info.vram);
                    allModels.push({
                        id: modelId,
                        name: `${cat.model}:${tag}`,
                        category: '_local',
                        rating: 5,
                        price: 'бесплатно',
                        censored: false,
                        prompt_price: 0,
                        _local: true,
                        _localInfo: {
                            size: sizeStr,
                            ram: ramStr,
                            vram: vramStr,
                            ctx: info.ctx || 0,
                            use: `${cat.total_tags} вариантов`
                        },
                        _catalogModel: cat.model,
                    });
                }
            });
        });
    }

    if (query.length === 0) {
        modelSearchFiltered = allModels;
    } else {
        const terms = query.split(/\s+/);
        modelSearchFiltered = allModels.filter(m => {
            const haystack = `${m.id} ${m.name} ${m.category || ''} ${m.description || ''}`.toLowerCase();
            return terms.every(t => haystack.includes(t));
        });
    }

    modelSearchHighlight = -1;
    renderModelDropdown(prefix, query);

    // запускаем поиск по каталогу Ollama с debounce
    if (query.length >= 2) {
        if (ollamaCatalogTimeout) clearTimeout(ollamaCatalogTimeout);
        ollamaCatalogTimeout = setTimeout(() => searchOllamaCatalog(prefix, query), 300);
    } else if (query.length === 0) {
        // при пустом запросе — загружаем популярные
        if (ollamaCatalog.length === 0) {
            searchOllamaCatalog(prefix, '');
        }
    }
}

async function searchOllamaCatalog(prefix, query) {
    if (ollamaCatalogLoading) return;
    ollamaCatalogLoading = true;

    try {
        const url = query
            ? `/api/local/catalog?q=${encodeURIComponent(query)}&limit=30`
            : `/api/local/catalog?limit=20`;
        const data = await apiSilent('GET', url);
        if (data && data.models) {
            ollamaCatalog = data.models;
            // перерисовываем только если dropdown ещё открыт
            if (modelSearchActivePrefix === prefix) {
                modelSearchFilter(prefix);
            }
        }
    } catch (e) {
        console.error('Ollama catalog search error:', e);
    }

    ollamaCatalogLoading = false;
}

function formatSizeCompact(gb) {
    if (!gb || gb <= 0) return '?';
    if (gb < 1) return Math.round(gb * 1024) + 'MB';
    return gb.toFixed(1) + 'GB';
}

function renderModelDropdown(prefix, query) {
    // Если пользователь кликает — не перерисовывать, отложить
    if (dropdownInteracting) {
        dropdownPendingRefresh = { prefix, query };
        return;
    }
    const dd = document.getElementById(`${prefix}ModelDropdown`);

    if (modelSearchFiltered.length === 0) {
        dd.innerHTML = `<div class="model-search-empty">
            Ничего не найдено для «${escapeHtml(query)}»
            ${!ollamaAvailable ? '<br><br><span style="color:#f0883e;">💡 Установите <a href="https://ollama.com" target="_blank" style="color:#646cff;">Ollama</a> для локальных моделей</span>' : ''}
        </div>`;
        dd.classList.add('open');
        return;
    }

    const grouped = {};

    // избранные
    const favModels = modelSearchFiltered.filter(m => favoriteModels.has(m.id));
    if (favModels.length > 0) grouped['_favorites'] = favModels;

    // локальные
    const localCatalogModels = modelSearchFiltered.filter(m => m._local || m.category === '_local');
    if (localCatalogModels.length > 0) grouped['_local'] = localCatalogModels;

    // остальные
    modelSearchFiltered.forEach(m => {
        if (m._local || m.category === '_local') return;
        const cat = m.category || 'psychology';
        if (!grouped[cat]) grouped[cat] = [];
        grouped[cat].push(m);
    });

    let html = '';
    let globalIdx = 0;

    // Ollama статус-бар
    if (ollamaAvailable === false && !query) {
        html += `<div style="padding:10px 14px; background:#1a1508; border-bottom:1px solid #332a10; font-size:12px;">
            <span style="color:#f0883e;">🖥️ Ollama не найдена</span> ·
            <a href="https://ollama.com" target="_blank" style="color:#646cff;">Установить →</a>
            <span style="color:#555; margin-left:8px;">curl -fsSL https://ollama.com/install.sh | sh</span>
        </div>`;
    } else if (ollamaAvailable === true && !query) {
        html += `<div style="padding:6px 14px; background:#0a1a0a; border-bottom:1px solid #1a331a; font-size:11px; color:#3fb950;">
            🖥️ Ollama ✅ · ${localModels.length} моделей скачано
        </div>`;
    }

    CATEGORY_ORDER.forEach(cat => {
        const items = grouped[cat.key];
        if (!items || items.length === 0) return;

        const isFav = cat.key === '_favorites';
        const isLocal = cat.key === '_local';
        let catClass = '';
        if (isFav) catClass = ' favorites';
        else if (isLocal) catClass = ' local-cat';

        html += `<div class="model-search-category${catClass}">${cat.label} (${items.length})</div>`;

        items.forEach(model => {
            const highlighted = globalIdx === modelSearchHighlight ? ' highlighted' : '';
            const name = highlightMatch(model.name, query);
            const id = highlightMatch(model.id, query);
            const censor = model.censored ? '' : '<span class="uncensored"> 🔓</span>';
            const isFavorite = favoriteModels.has(model.id);
            const starClass = isFavorite ? ' active' : '';
            const starIcon = isFavorite ? '⭐' : '☆';

            // локальная модель — другой рендер
            if (model._local) {
                const lm = model._localInfo || {};
                const installed = isLocalModelInstalled(model.id);
                const pulling = ollamaPulling[model.id] !== undefined;

                let actionHtml = '';
                if (pulling) {
                    actionHtml = `<span style="color:#f0883e; font-size:11px;">⏳ Скачивание...</span>`;
                } else if (installed) {
                    actionHtml = `<span style="color:#3fb950; font-size:11px;">✅ Скачана</span>
                        <button class="btn-local-action delete" data-local-delete="${escapeAttr(model.id)}" title="Удалить">🗑️</button>`;
                } else {
                    actionHtml = `<button class="btn-local-action download" data-local-pull="${escapeAttr(model.id)}" title="Скачать">⬇️ ${lm.size || ''}</button>`;
                }

                html += `
                    <div class="model-search-item${highlighted}"
                         data-idx="${globalIdx}"
                         data-model-id="${escapeAttr(model.id)}"
                         onmouseenter="modelSearchHighlight=${globalIdx}; highlightModelItem('${prefix}')">
                        <button class="model-search-fav-btn${starClass}"
                                data-fav-id="${escapeAttr(model.id)}"
                                title="${isFavorite ? 'Убрать из избранного' : 'В избранное'}">${starIcon}</button>
                        <div class="model-search-item-content">
                            <div class="model-search-item-name">${name} <span style="color:#555; font-size:11px;">🖥️</span></div>
                            <div class="model-search-item-meta">
                                <span style="color:#3fb950;">бесплатно</span>
                                <span style="color:#666; margin-left:6px;">RAM ${lm.ram || '?'} · VRAM ${lm.vram || '?'}</span>
                                ${lm.use ? `<br><span style="color:#888;">${escapeHtml(lm.use)}</span>` : ''}
                            </div>
                        </div>
                        <div style="flex-shrink:0; display:flex; align-items:center; gap:6px;">
                            ${actionHtml}
                        </div>
                    </div>`;
            } else {
                // облачная модель
                html += `
                    <div class="model-search-item${highlighted}"
                         data-idx="${globalIdx}"
                         data-model-id="${escapeAttr(model.id)}"
                         onmouseenter="modelSearchHighlight=${globalIdx}; highlightModelItem('${prefix}')">
                        <button class="model-search-fav-btn${starClass}"
                                data-fav-id="${escapeAttr(model.id)}"
                                title="${isFavorite ? 'Убрать из избранного' : 'В избранное'}">${starIcon}</button>
                        <div class="model-search-item-content">
                            <div class="model-search-item-name">${name}${censor}</div>
                            <div class="model-search-item-meta">
                                <span style="color:#888;">${id}</span>
                                <span class="price" style="margin-left:8px;">${model.price || ''}</span>
                            </div>
                        </div>
                    </div>`;
            }
            globalIdx++;
        });
    });

    // HuggingFace результаты
    if (hfSearchResults.length > 0) {
        html += `<div class="model-search-category local-cat">🤗 HuggingFace GGUF (${hfSearchResults.length})</div>`;
        hfSearchResults.forEach(hf => {
            const highlighted = globalIdx === modelSearchHighlight ? ' highlighted' : '';
            const installed = isLocalModelInstalled(hf.ollama_id);
            const pulling = ollamaPulling[hf.ollama_id] !== undefined;
            const uncensor = hf.uncensored ? ' 🔓🔥' : '';
            const dlk = hf.downloads > 1000 ? Math.round(hf.downloads/1000)+'k' : hf.downloads;

            let actionHtml = '';
            if (pulling) {
                actionHtml = `<span style="color:#f0883e; font-size:11px;">⏳ Скачивание...</span>`;
            } else if (installed) {
                actionHtml = `<span style="color:#3fb950; font-size:11px;">✅ Скачана</span>
                    <button class="btn-local-action delete" data-local-delete="${escapeAttr(hf.ollama_id)}" title="Удалить">🗑️</button>`;
            } else {
                actionHtml = `<button class="btn-local-action download" data-local-pull="${escapeAttr(hf.ollama_id)}" title="Скачать через Ollama">⬇️ ${hf.size_hint || 'GGUF'}</button>`;
            }

            html += `
                <div class="model-search-item${highlighted}"
                     data-idx="${globalIdx}"
                     data-model-id="${escapeAttr(hf.ollama_id)}"
                     onmouseenter="modelSearchHighlight=${globalIdx}; highlightModelItem('${prefix}')">
                    <div class="model-search-item-content">
                        <div class="model-search-item-name">${escapeHtml(hf.name)}${uncensor} <span style="color:#555; font-size:11px;">🤗</span></div>
                        <div class="model-search-item-meta">
                            <span style="color:#3fb950;">бесплатно</span>
                            <span style="color:#666; margin-left:6px;">${hf.size_hint || '?'} · ⬇${dlk}</span>
                        </div>
                    </div>
                    <div style="flex-shrink:0; display:flex; align-items:center; gap:6px;">
                        ${actionHtml}
                    </div>
                </div>`;
            globalIdx++;
            // добавляем в filtered для навигации
            modelSearchFiltered.push({ id: hf.ollama_id, name: hf.name, _local: true, _localInfo: { size: hf.size_hint, ram: '?', vram: '?', use: 'HuggingFace GGUF' } });
        });
    }

    // кнопка поиска HF
    if (query && query.length >= 2) {
        if (hfSearchLoading) {
            html += `<div class="model-search-count">⏳ Поиск на HuggingFace...</div>`;
        } else {
            html += `<div class="model-search-count" style="cursor:pointer; color:#58a6ff;" onclick="searchHuggingFace('${prefix}', '${escapeAttr(query)}')">🤗 Искать «${escapeHtml(query)}» на HuggingFace →</div>`;
        }
    }

    html += `<div class="model-search-count">${modelSearchFiltered.length} моделей · ⭐ ${favoriteModels.size} избранных${ollamaAvailable ? ` · 🖥️ ${localModels.length} локальных` : ''}</div>`;

    dd.innerHTML = html;
    dd.classList.add('open');
}

async function searchHuggingFace(prefix, query) {
    if (hfSearchLoading || !query || query.length < 2) return;
    hfSearchLoading = true;
    hfSearchQuery = query;

    // показываем "загрузка..." — перерисовываем dropdown
    renderModelDropdown(prefix);

    try {
        const resp = await fetch(`/api/hf/search?q=${encodeURIComponent(query)}&limit=15`);
        const data = await resp.json();

        if (data.models) {
            const catalogIds = new Set(ollamaCatalog.flatMap(c => Object.keys(c.tags || {}).map(t => t === 'latest' ? c.model : `${c.model}:${t}`)));
            hfSearchResults = data.models.filter(m => !catalogIds.has(m.ollama_id));
        } else {
            hfSearchResults = [];
        }
    } catch (e) {
        console.error('HF search error:', e);
        hfSearchResults = [];
    }

    hfSearchLoading = false;
    // перерисовываем с результатами
    renderModelDropdown(prefix);
}

function highlightMatch(text, query) {
    if (!query || query.length < 2) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const terms = query.split(/\s+/).filter(t => t.length >= 2);
    let result = escaped;
    terms.forEach(term => {
        const regex = new RegExp(`(${escapeRegex(term)})`, 'gi');
        result = result.replace(regex, '<mark>$1</mark>');
    });
    return result;
}

function escapeRegex(str) { return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
function escapeAttr(str) { return str.replace(/'/g, "\\'").replace(/"/g, '\\"'); }

function modelSearchSelect(prefix, modelId) {
    console.log("SELECT:", prefix, modelId);
    const allModels = [...models];
    // каталог Ollama — берём из результатов поиска
    ollamaCatalog.forEach(cat => {
        const tagEntries = cat.tags ? Object.entries(cat.tags) : [];
        tagEntries.forEach(([tag, info]) => {
            const catModelId = tag === 'latest' ? cat.model : `${cat.model}:${tag}`;
            if (!allModels.find(m => m.id === catModelId)) {
                allModels.push({ id: catModelId, name: `${cat.model}:${tag}`, price: 'бесплатно', censored: false, _local: true });
            }
        });
    });
    localModels.forEach(lm => {
        const name = lm.name || lm.model;
        if (!allModels.find(m => m.id === name)) {
            allModels.push({ id: name, name: name, price: 'бесплатно', censored: false, _local: true });
        }
    });

    const model = allModels.find(m => m.id === modelId);
    if (!model) return;

    document.getElementById(`${prefix}ModelValue`).value = modelId;
    document.getElementById(`${prefix}ModelSearch`).value = '';

    const censor = model.censored ? '' : ' 🔓';
    const favStar = favoriteModels.has(modelId) ? '⭐ ' : '';
    const localTag = model._local ? ' 🖥️' : '';
    document.getElementById(`${prefix}ModelSelected`).innerHTML =
        `✅ ${favStar}<strong>${escapeHtml(model.name)}</strong> · ${model.price || ''}${censor}${localTag}` +
        `<br><span style="color:#888; font-size:11px;">${escapeHtml(model.id)}</span>`;

    // если локальная модель — автоматически ставим провайдер local
    if (model._local) {
        const providerEl = document.getElementById(`${prefix}Provider`);
        if (providerEl) {
            providerEl.value = 'local';
            onProviderChange(prefix);
        }
    }

    modelSearchClose(prefix);
}

function highlightModelItem(prefix) {
    const dd = document.getElementById(`${prefix}ModelDropdown`);
    dd.querySelectorAll('.model-search-item').forEach((el, i) => {
        el.classList.toggle('highlighted', i === modelSearchHighlight);
    });
}

function scrollToHighlighted(prefix) {
    const dd = document.getElementById(`${prefix}ModelDropdown`);
    const item = dd.querySelector(`.model-search-item[data-idx="${modelSearchHighlight}"]`);
    if (item) item.scrollIntoView({ block: 'nearest' });
}

// ====================================================
// КЛАВИАТУРА + КЛИКИ (единый обработчик)
// ====================================================

document.addEventListener('keydown', (e) => {
    if (!modelSearchActivePrefix) return;
    const prefix = modelSearchActivePrefix;
    const dd = document.getElementById(`${prefix}ModelDropdown`);
    if (!dd || !dd.classList.contains('open')) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        modelSearchHighlight = Math.min(modelSearchHighlight + 1, modelSearchFiltered.length - 1);
        highlightModelItem(prefix);
        scrollToHighlighted(prefix);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        modelSearchHighlight = Math.max(modelSearchHighlight - 1, 0);
        highlightModelItem(prefix);
        scrollToHighlighted(prefix);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (modelSearchHighlight >= 0 && modelSearchHighlight < modelSearchFiltered.length) {
            modelSearchSelect(prefix, modelSearchFiltered[modelSearchHighlight].id);
        }
    } else if (e.key === 'Escape') {
        modelSearchClose(prefix);
    }
});

// mousedown на dropdown — только предотвращаем потерю фокуса, НЕ обрабатываем клик
document.addEventListener('mousedown', (e) => {
    const item = e.target.closest('.model-search-item');
    const dd = e.target.closest('.model-search-dropdown');
    console.log('MOUSEDOWN:', e.target.tagName, e.target.className, 'item:', !!item, 'dd:', !!dd);
    if (dd) {
        e.preventDefault();
        dropdownInteracting = true;
    }
});

document.addEventListener('mouseup', () => {
    if (dropdownInteracting) {
        dropdownInteracting = false;
        // Если была отложенная перерисовка — выполняем
        if (dropdownPendingRefresh && modelSearchActivePrefix) {
            const prefix = modelSearchActivePrefix;
            dropdownPendingRefresh = null;
            modelSearchFilter(prefix);
        }
    }
});

// единый click handler
document.addEventListener('click', (e) => {
    // кнопка скачивания локальной модели
    const pullBtn = e.target.closest('[data-local-pull]');
    if (pullBtn) {
        e.preventDefault();
        e.stopPropagation();
        pullLocalModel(pullBtn.dataset.localPull);
        return;
    }

    // кнопка удаления локальной модели
    const delBtn = e.target.closest('[data-local-delete]');
    if (delBtn) {
        e.preventDefault();
        e.stopPropagation();
        deleteLocalModel(delBtn.dataset.localDelete);
        return;
    }

    // звёздочка
    const favBtn = e.target.closest('.model-search-fav-btn');
    if (favBtn) {
        e.preventDefault();
        e.stopPropagation();
        const modelId = favBtn.dataset.favId;
        if (modelId) toggleFavorite(modelId);
        return;
    }

    // выбор модели
    const item = e.target.closest('.model-search-item');
    console.log('CLICK check item:', !!item, 'prefix:', modelSearchActivePrefix, 'target:', e.target.tagName, e.target.className);
    if (item && modelSearchActivePrefix) {
        e.preventDefault();
        e.stopPropagation();
        const modelId = item.dataset.modelId;
        if (modelId) modelSearchSelect(modelSearchActivePrefix, modelId);
        return;
    }

    // клик снаружи — закрываем
    ['new', 'edit'].forEach(pfx => {
        const wrap = document.getElementById(`${pfx}ModelWrap`);
        const dd = document.getElementById(`${pfx}ModelDropdown`);
        const inWrap = wrap && wrap.contains(e.target);
        const inDd = dd && dd.contains(e.target);
        console.log('OUTSIDE CHECK:', pfx, 'inWrap:', inWrap, 'inDd:', inDd, 'activePrefix:', modelSearchActivePrefix);
        if (wrap && !inWrap && !inDd) {
            modelSearchClose(pfx);
        }
    });
});

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
    document.getElementById('newModelValue').value = '';
    document.getElementById('newModelSelected').innerHTML = '';
    document.getElementById('newModelSearch').value = '';
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
    const selectedModel = document.getElementById('newModelValue').value;
    const model = manualModel || selectedModel;
    const prompt = document.getElementById('newPrompt').value.trim();
    const provider = document.getElementById('newProvider').value;
    const customUrl = document.getElementById('newCustomUrl').value.trim();

    if (!name) return toast('Введите имя бота', 'error');
    if (!model) return toast('Выберите модель', 'error');
    if (provider !== 'local' && !apiKey) return toast('Введите API ключ', 'error');

    try {
        await api('POST', '/api/bots', {
            name, bot_token: token, api_key: apiKey || 'local', model,
            system_prompt: prompt, provider, custom_base_url: customUrl
        });
        toast('Бот создан! ✅', 'success');
        closeModal('createModal');
        loadBots();
    } catch (e) {
        toast(`Ошибка: ${e.message}`, 'error');
    }
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

        // модель
        const currentModel = config.model || '';
        document.getElementById('editModelValue').value = currentModel;
        document.getElementById('editModelSearch').value = '';

        // ищем модель во всех списках
        let modelData = models.find(m => m.id === currentModel);
        if (!modelData) {
            // ищем в каталоге Ollama
            for (const cat of ollamaCatalog) {
                const tagEntries = Object.entries(cat.tags || {});
                for (const [tag, info] of tagEntries) {
                    const mId = tag === 'latest' ? cat.model : `${cat.model}:${tag}`;
                    if (mId === currentModel) {
                        modelData = { id: mId, name: `${cat.model}:${tag}`, price: 'бесплатно', censored: false, _local: true };
                        break;
                    }
                }
                if (modelData) break;
            }
        }

        if (modelData) {
            const censor = modelData.censored ? '' : ' 🔓';
            const localTag = modelData._local ? ' 🖥️' : '';
            document.getElementById('editModelSelected').innerHTML =
                `✅ <strong>${escapeHtml(modelData.name)}</strong> · ${modelData.price || ''}${censor}${localTag}` +
                `<br><span style="color:#888; font-size:11px;">${escapeHtml(modelData.id)}</span>`;
            document.getElementById('editModelManual').value = '';
        } else {
            document.getElementById('editModelSelected').innerHTML =
                `<span style="color:#f0883e;">⚠️ ${escapeHtml(currentModel)}</span>`;
            document.getElementById('editModelManual').value = currentModel;
        }

        // инструменты
        document.getElementById('editToolsEnabled').checked = config.tools_enabled !== false;
        document.getElementById('editAccessMode').value = config.access_mode || 'sandbox';
        document.getElementById('editWorkingDirectory').value = config.working_directory || '';
        document.getElementById('editMaxToolRounds').value = config.max_tool_rounds || 15;
        const perms = config.tool_permissions || {};
        const permDefaults = {
            execute_commands: true, write_files: true, delete_files: false,
            network: false, install_packages: false,
            user_can_clear_history: true, user_can_add_prompt: false, user_can_add_knowledge: false
        };
        ['execute_commands', 'write_files', 'delete_files', 'network', 'install_packages',
         'user_can_clear_history', 'user_can_add_prompt', 'user_can_add_knowledge'].forEach(p => {
            const el = document.getElementById(`perm_${p}`);
            if (el) el.checked = perms[p] !== undefined ? perms[p] : (permDefaults[p] || false);
        });

        switchTab('settings');
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
    const selectedModel = document.getElementById('editModelValue').value;
    const model = manualModel || selectedModel;

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
            user_can_clear_history: document.getElementById('perm_user_can_clear_history').checked,
            user_can_add_prompt: document.getElementById('perm_user_can_add_prompt').checked,
            user_can_add_knowledge: document.getElementById('perm_user_can_add_knowledge').checked,
        },
    };

    try {
        await api('PUT', `/api/bots/${currentBotId}`, updates);
        toast('Сохранено! ✅', 'success');
        loadBots();
    } catch (e) {
        toast(`Ошибка: ${e.message}`, 'error');
    }
}

// ====================================================
// УПРАВЛЕНИЕ БОТОМ
// ====================================================

async function startBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/start`);
        toast('Бот запущен! 🟢', 'success');
        loadBots();
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
}

async function stopBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/stop`);
        toast('Бот остановлен 🔴', 'info');
        loadBots();
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
}

async function restartBot(botId) {
    try {
        await api('POST', `/api/bots/${botId}/restart`);
        toast('Бот перезапущен 🔄', 'success');
        loadBots();
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
}

// ====================================================
// TELEGRAM
// ====================================================

async function startTelegram(botId) {
    try {
        await api('POST', `/api/bots/${botId}/telegram/start`);
        toast('Telegram подключён 🔵', 'success');
        loadBots();
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
}

async function stopTelegram(botId) {
    try {
        await api('POST', `/api/bots/${botId}/telegram/stop`);
        toast('Telegram отключён', 'info');
        loadBots();
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
}

// ====================================================
// ТАБ: ЮЗЕРЫ
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
    } catch (e) { loadUsersTab(currentBotId); }
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
// ТАБ: СТАТИСТИКА
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
// ТАБ: ПЛАТЕЖИ
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

// ====================================================
// ТАБЫ
// ====================================================

function switchTab(tabName) {
    document.querySelectorAll('#editTabs .tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const content = document.getElementById(`tab-${tabName}`);
    if (content) content.classList.add('active');
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
    const apiKeyGroup = document.getElementById(`${prefix}ApiKeyGroup`);
    const localInfo = document.getElementById(`${prefix}LocalInfo`);

    if (urlGroup) urlGroup.style.display = (provider === 'custom') ? 'block' : 'none';
    if (apiKeyGroup) apiKeyGroup.style.display = (provider === 'local') ? 'none' : 'block';
    if (localInfo) {
        localInfo.style.display = (provider === 'local') ? 'block' : 'none';
        if (provider === 'local') {
            refreshOllamaPanel(prefix);
        }
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

    const adminFiles = data.admin_files || [];
    const userFiles = data.user_files || [];

    let html = `<div style="margin-bottom:8px; color:#8b8b8b; font-size:12px;">
        📊 ${data.total_files} файлов, ${data.total_chunks} чанков
    </div>`;

    if (adminFiles.length > 0) {
        html += `<div style="color:#646cff; font-size:12px; margin:10px 0 6px;">📋 Загружено из панели (${adminFiles.length})</div>`;
        html += adminFiles.map(f => knowledgeFileRow(f)).join('');
    }
    if (userFiles.length > 0) {
        html += `<div style="color:#d29922; font-size:12px; margin:10px 0 6px;">👤 Загружено пользователями (${userFiles.length})</div>`;
        html += userFiles.map(f => knowledgeFileRow(f)).join('');
    }
    list.innerHTML = html;
}

function knowledgeFileRow(f) {
    return `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#1a1a1a; border-radius:8px; margin-bottom:4px;">
            <div>
                <span style="color:#e0e0e0; font-size:13px;">${escapeHtml(f.name)}</span>
                <span style="color:#555; font-size:11px; margin-left:8px;">${formatFileSize(f.size)} · ${f.chunks} чанков</span>
            </div>
            <button class="btn btn-danger btn-sm" onclick="deleteKnowledgeFile('${escapeHtml(f.name)}')">✕</button>
        </div>`;
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
        } else toast(`❌ ${result.error}`, 'error');
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
                <div style="font-size:13px; color:#ccc;">${escapeHtml(r.text).substring(0, 200)}</div>
            </div>
        `).join('');
    } catch (e) {}
}

// ====================================================
// ТЕРМИНАЛ
// ====================================================

let terminalBotId = null;
let terminalUserId = Date.now();

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
    container.innerHTML += `<div style="color:#646cff; margin:8px 0;">▸ ${escapeHtml(msg)}</div>`;

    const thinkId = 'think_' + Date.now();
    container.innerHTML += `<div id="${thinkId}" style="color:#555;">⏳ Думаю...</div>`;
    container.scrollTop = container.scrollHeight;

    try {
        const result = await api('POST', `/api/bots/${terminalBotId}/chat`, {
            message: msg,
            user_id: terminalUserId
        });

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
        await api('PUT', `/api/bots/${filesBotId}/files`, { path: filesEditingPath, content: content });
        toast('Файл сохранён ✅', 'success');
    } catch (e) { toast(`Ошибка: ${e.message}`, 'error'); }
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

// ====================================================
// OLLAMA — управление из панели
// ====================================================

let ollamaChecking = false;

async function refreshOllamaPanel(prefix) {
    if (ollamaChecking) return;
    ollamaChecking = true;

    const container = document.getElementById(`${prefix}OllamaStatus`);
    if (!container) { ollamaChecking = false; return; }

    container.innerHTML = '<span style="color:#555;">⏳ Проверка...</span>';

    const status = await apiSilent('GET', '/api/local/status');
    const installed = status && status.installed;
    const running = status && status.running;
    const binary = status ? status.binary : null;

    if (!installed) {
        // НЕ УСТАНОВЛЕНА
        container.innerHTML = `
            <div class="ollama-status-row">
                <span class="ollama-status-badge missing">⬜ Не установлена</span>
            </div>
            <div class="ollama-actions">
                <button class="btn-ollama install" onclick="installOllama('${prefix}')">
                    📦 Установить Ollama
                </button>
            </div>
            <div class="ollama-info">
                Ollama — движок для запуска AI на вашем ПК.<br>
                Бесплатно, данные не уходят в интернет.<br>
                ~100MB. Модели 1-10GB каждая.
            </div>`;
        ollamaChecking = false;
        return;
    }

    if (!running) {
        // УСТАНОВЛЕНА НО НЕ ЗАПУЩЕНА
        container.innerHTML = `
            <div class="ollama-status-row">
                <span class="ollama-status-badge offline">🟠 Остановлена</span>
                <span style="color:#555; font-size:11px;">${escapeHtml(binary || '')}</span>
            </div>
            <div class="ollama-actions">
                <button class="btn-ollama start" onclick="startOllama('${prefix}')">
                    ▶️ Запустить
                </button>
                <button class="btn-ollama uninstall" onclick="uninstallOllama('${prefix}')">
                    🗑️ Удалить
                </button>
            </div>`;
        ollamaChecking = false;
        return;
    }

    // РАБОТАЕТ
    const modelCount = (status.models || []).length;
    ollamaAvailable = true;
    localModels = status.models || [];

    const modelsList = localModels.map(m => {
        const sizeGB = m.size ? (m.size / 1024 / 1024 / 1024).toFixed(1) + 'GB' : '';
        return `<span style="color:#e0e0e0;">${m.name}</span> <span style="color:#555;">${sizeGB}</span>`;
    }).join(' · ');

    container.innerHTML = `
        <div class="ollama-status-row">
            <span class="ollama-status-badge online">🟢 Работает</span>
            <span style="color:#555; font-size:12px;">${modelCount} моделей</span>
        </div>
        ${modelCount > 0 ? `<div class="ollama-models-count">📦 ${modelsList}</div>` : '<div class="ollama-info">💡 Скачайте модель в поиске выше — локальные отмечены 🖥️</div>'}
        <div class="ollama-actions">
            <button class="btn-ollama stop" onclick="stopOllama('${prefix}')">
                ⏹ Остановить
            </button>
            <button class="btn-ollama uninstall" onclick="uninstallOllama('${prefix}')">
                🗑️ Удалить
            </button>
        </div>`;

    ollamaChecking = false;
}



async function installOllama(prefix) {
    const container = document.getElementById(`${prefix}OllamaStatus`);
    container.innerHTML = `
        <div class="ollama-progress">
            ⏳ Установка Ollama... Это может занять 1-3 минуты.<br>
            Не закрывайте страницу.
        </div>`;

    try {
        const result = await api('POST', '/api/local/install');
        if (result.ok) {
            toast(result.message || 'Ollama установлена! ✅', 'success');
            await checkOllama();
            await refreshOllamaPanel(prefix);
        } else {
            // показываем ошибку с инструкцией прямо в панели
            const errorMsg = result.error || 'Неизвестная ошибка';
            container.innerHTML = `
                <div style="padding:12px; background:#1a0a0a; border:1px solid #4a1a1a; border-radius:8px;">
                    <p style="color:#f85149; margin-bottom:10px;">❌ Не удалось установить автоматически</p>
                    <pre style="color:#e0e0e0; font-size:12px; white-space:pre-wrap; background:#0a0a0a; padding:10px; border-radius:6px; margin-bottom:10px;">${escapeHtml(errorMsg)}</pre>
                    <p style="color:#f0883e; font-size:13px; margin-bottom:8px;">📋 Установите вручную — одна команда:</p>
                    <div style="display:flex; gap:8px; align-items:center;">
                        <code style="flex:1; padding:10px; background:#1a1a2a; border:1px solid #333; border-radius:6px; color:#646cff; font-size:13px; user-select:all;">curl -fsSL https://ollama.com/install.sh | sudo sh</code>
                        <button class="btn btn-ghost btn-sm" onclick="navigator.clipboard.writeText('curl -fsSL https://ollama.com/install.sh | sudo sh'); toast('Скопировано!', 'success')">📋</button>
                    </div>
                    <p style="color:#555; font-size:11px; margin-top:8px;">Выполните в терминале, затем нажмите «Проверить»</p>
                    <button class="btn-ollama start" onclick="refreshOllamaPanel('${prefix}')" style="margin-top:10px;">
                        🔄 Проверить
                    </button>
                </div>`;
        }
    } catch (e) {
        toast(`❌ ${e.message}`, 'error');
        await refreshOllamaPanel(prefix);
    }
}
async function startOllama(prefix) {
    const container = document.getElementById(`${prefix}OllamaStatus`);
    container.innerHTML = '<div class="ollama-progress">⏳ Запуск Ollama...</div>';

    try {
        const result = await api('POST', '/api/local/start');
        if (result.ok) {
            toast('Ollama запущена ✅', 'success');
            await checkOllama();
            await refreshOllamaPanel(prefix);
        } else {
            toast(`❌ ${result.error}`, 'error');
            await refreshOllamaPanel(prefix);
        }
    } catch (e) {
        toast(`❌ ${e.message}`, 'error');
        await refreshOllamaPanel(prefix);
    }
}

async function stopOllama(prefix) {
    try {
        const result = await api('POST', '/api/local/stop');
        if (result.ok) {
            toast('Ollama остановлена', 'info');
            ollamaAvailable = false;
            localModels = [];
            await refreshOllamaPanel(prefix);
        } else {
            toast(`❌ ${result.error}`, 'error');
        }
    } catch (e) {
        toast(`❌ ${e.message}`, 'error');
    }
}

async function uninstallOllama(prefix) {
    if (!confirm('Удалить Ollama и ВСЕ скачанные модели?')) return;
    if (!confirm('Точно удалить? Модели придётся качать заново.')) return;

    const container = document.getElementById(`${prefix}OllamaStatus`);
    container.innerHTML = '<div class="ollama-progress">⏳ Удаление Ollama...</div>';

    try {
        const result = await api('DELETE', '/api/local/uninstall');
        if (result.ok) {
            toast(result.message || 'Ollama удалена', 'success');
            ollamaAvailable = false;
            localModels = [];
            await refreshOllamaPanel(prefix);
        } else {
            toast(`❌ ${result.error}`, 'error');
            await refreshOllamaPanel(prefix);
        }
    } catch (e) {
        toast(`❌ ${e.message}`, 'error');
        await refreshOllamaPanel(prefix);
    }
}