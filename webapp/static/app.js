/* ============================================
   🧠 LARIZINHA STORE — APP.JS
   ============================================
   Cérebro do Mini App.
   - Lê Telegram WebApp SDK
   - Autentica via initData
   - Carrega config + catálogo
   - Gerencia carrinho (localStorage)
   - Navegação entre telas
   - Checkout + Pix real
   ============================================ */

(function () {
    'use strict';

    // ============================================
    // 🌐 ESTADO GLOBAL
    // ============================================
    const State = {
        tg: null,
        initData: '',
        user: null,
        config: null,
        catalog: {
            categories: [],
            products: [],
            byId: new Map(),
        },
        cart: [], // [{product_id, quantity}]
        currentPage: 'store',
        currentCategory: 'all',
        searchQuery: '',
        loading: false,
        initialized: false,
    };

    // ============================================
    // 🎯 CONSTANTES
    // ============================================
    const API_BASE = '/api/webapp';
    const CART_STORAGE_KEY = 'larizinha_cart_v1';
    const CATEGORY_ALL = 'all';

    // ============================================
    // 🧰 HELPERS
    // ============================================
    function formatBRL(value) {
        const num = Number(value) || 0;
        return 'R$ ' + num.toFixed(2).replace('.', ',');
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    function debounce(fn, delay) {
        let t = null;
        return function (...args) {
            clearTimeout(t);
            t = setTimeout(() => fn.apply(this, args), delay);
        };
    }

    function haptic(type = 'light') {
        try {
            if (State.tg && State.tg.HapticFeedback) {
                if (type === 'light') State.tg.HapticFeedback.impactOccurred('light');
                else if (type === 'medium') State.tg.HapticFeedback.impactOccurred('medium');
                else if (type === 'heavy') State.tg.HapticFeedback.impactOccurred('heavy');
                else if (type === 'success') State.tg.HapticFeedback.notificationOccurred('success');
                else if (type === 'error') State.tg.HapticFeedback.notificationOccurred('error');
                else if (type === 'warning') State.tg.HapticFeedback.notificationOccurred('warning');
            }
        } catch (e) {
            /* silent */
        }
    }

    // ============================================
    // 🔔 TOASTS
    // ============================================
    function toast(message, type = 'info', duration = 3200) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const icons = {
            success: 'fa-check',
            error: 'fa-xmark',
            warning: 'fa-triangle-exclamation',
            info: 'fa-circle-info',
        };

        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.innerHTML = `
            <div class="toast-icon">
                <i class="fa-solid ${icons[type] || icons.info}"></i>
            </div>
            <div class="toast-text">${escapeHtml(message)}</div>
        `;

        container.appendChild(el);

        setTimeout(() => {
            el.classList.add('removing');
            setTimeout(() => el.remove(), 350);
        }, duration);
    }

    // ============================================
    // ⏳ LOADING
    // ============================================
    function showLoading(text = 'Carregando...') {
        const overlay = document.getElementById('loading-overlay');
        const textEl = document.getElementById('loading-text');
        if (overlay) overlay.style.display = 'flex';
        if (textEl) textEl.textContent = text;
    }

    function hideLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'none';
    }

    // ============================================
    // 📡 API
    // ============================================
    async function api(path, options = {}) {
        const url = `${API_BASE}${path}`;
        const headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': State.initData,
            ...(options.headers || {}),
        };

        const res = await fetch(url, {
            ...options,
            headers,
        });

        let data = null;
        try {
            data = await res.json();
        } catch (e) {
            data = null;
        }

        if (!res.ok) {
            const err = new Error(
                (data && data.detail && (data.detail.error || data.detail)) ||
                `HTTP ${res.status}`
            );
            err.status = res.status;
            err.data = data;
            throw err;
        }

        return data;
    }

    // ============================================
    // 🛒 CARRINHO (localStorage)
    // ============================================
    function loadCartFromStorage() {
        try {
            const raw = localStorage.getItem(CART_STORAGE_KEY);
            if (!raw) return;
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) {
                State.cart = parsed.filter(
                    (i) => i && Number.isInteger(i.product_id) && i.quantity > 0
                );
            }
        } catch (e) {
            State.cart = [];
        }
    }

    function saveCartToStorage() {
        try {
            localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(State.cart));
        } catch (e) {
            /* silent */
        }
    }

    function getCartCount() {
        return State.cart.reduce((sum, i) => sum + i.quantity, 0);
    }

    function getCartTotal() {
        return State.cart.reduce((sum, i) => {
            const p = State.catalog.byId.get(i.product_id);
            if (!p) return sum;
            return sum + p.price * i.quantity;
        }, 0);
    }

    function addToCart(productId, quantity = 1) {
        const p = State.catalog.byId.get(productId);
        if (!p) {
            toast('Produto não encontrado', 'error');
            return false;
        }

        if (!p.in_stock) {
            toast('Produto sem estoque', 'warning');
            return false;
        }

        const existing = State.cart.find((i) => i.product_id === productId);
        const currentQty = existing ? existing.quantity : 0;
        const newQty = currentQty + quantity;

        // Limites
        if (newQty > p.max_quantity) {
            toast(`Máximo ${p.max_quantity} por produto`, 'warning');
            return false;
        }
        if (newQty > p.stock) {
            toast(`Apenas ${p.stock} em estoque`, 'warning');
            return false;
        }

        if (existing) {
            existing.quantity = newQty;
        } else {
            State.cart.push({ product_id: productId, quantity });
        }

        saveCartToStorage();
        updateCartUI();
        haptic('success');
        toast(`${p.name} adicionado ao carrinho`, 'success');
        return true;
    }

    function removeFromCart(productId) {
        State.cart = State.cart.filter((i) => i.product_id !== productId);
        saveCartToStorage();
        updateCartUI();
        renderCartDrawer();
        haptic('light');
    }

    function updateCartQuantity(productId, delta) {
        const item = State.cart.find((i) => i.product_id === productId);
        if (!item) return;

        const p = State.catalog.byId.get(productId);
        if (!p) return;

        const newQty = item.quantity + delta;

        if (newQty <= 0) {
            removeFromCart(productId);
            return;
        }

        if (newQty > p.max_quantity) {
            toast(`Máximo ${p.max_quantity}`, 'warning');
            return;
        }
        if (newQty > p.stock) {
            toast(`Apenas ${p.stock} em estoque`, 'warning');
            return;
        }

        item.quantity = newQty;
        saveCartToStorage();
        updateCartUI();
        renderCartDrawer();
        haptic('light');
    }

    function clearCart() {
        State.cart = [];
        saveCartToStorage();
        updateCartUI();
        renderCartDrawer();
    }

    // ============================================
    // 🎨 UPDATE UI DO CARRINHO
    // ============================================
    function updateCartUI() {
        const count = getCartCount();

        // Header badge
        const headerBadge = document.getElementById('header-cart-badge');
        if (headerBadge) {
            if (count > 0) {
                headerBadge.textContent = count;
                headerBadge.style.display = 'flex';
            } else {
                headerBadge.style.display = 'none';
            }
        }

        // Bottom nav badge
        const navBadge = document.getElementById('nav-center-badge');
        if (navBadge) {
            if (count > 0) {
                navBadge.textContent = count;
                navBadge.style.display = 'flex';
            } else {
                navBadge.style.display = 'none';
            }
        }

        // Total no footer
        const totalEl = document.getElementById('cart-total');
        if (totalEl) totalEl.textContent = formatBRL(getCartTotal());

        const countEl = document.getElementById('cart-items-count');
        if (countEl) countEl.textContent = count;

        // Saldo
        const balanceEl = document.getElementById('cart-balance');
        if (balanceEl && State.user) {
            balanceEl.textContent = formatBRL(State.user.balance);
        }

        // Checkout button state
        const checkoutBtn = document.getElementById('cart-checkout-btn');
        if (checkoutBtn) {
            const hasItems = count > 0;
            const enoughBalance = State.user && State.user.balance >= getCartTotal();
            checkoutBtn.disabled = !hasItems || !enoughBalance;
        }

        // Atualiza cards de produto (botão "adicionado")
        document.querySelectorAll('[data-product-id]').forEach((card) => {
            const pid = Number(card.getAttribute('data-product-id'));
            const inCart = State.cart.some((i) => i.product_id === pid);
            const btn = card.querySelector('.product-add-btn');
            if (btn && inCart) {
                btn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Adicionado</span>`;
            }
        });
    }

    // ============================================
    // 🌐 NAVEGAÇÃO
    // ============================================
    function setActiveNav(name) {
        document.querySelectorAll('.nav-item').forEach((el) => {
            el.classList.remove('active');
        });
        const nav = document.getElementById(`nav-${name}`);
        if (nav) nav.classList.add('active');
    }

    function goToPage(page) {
        State.currentPage = page;
        setActiveNav(page === 'cart' ? 'cart' : page);

        if (page === 'store') {
            showStorePage();
        } else if (page === 'cart') {
            openCartDrawer();
        } else if (page === 'history') {
            showHistoryPage();
        } else if (page === 'profile') {
            showProfilePage();
        } else if (page === 'recharge') {
            showRechargePage();
        }
    }

    // ============================================
    // 🏪 PÁGINA DA LOJA
    // ============================================
    function showStorePage() {
        const main = document.getElementById('app-content');
        if (!main) return;

        // Se já tem catálogo, só renderiza
        if (State.catalog.products.length > 0) {
            renderCategories();
            renderProducts();
            return;
        }

        // Senão, mostra skeleton e carrega
        main.innerHTML = getStorePageHTML();
        attachStoreHandlers();
        loadCatalog();
    }

    function getStorePageHTML() {
        return `
            <div class="search-wrapper">
                <div class="search-box">
                    <i class="fa-solid fa-magnifying-glass search-icon"></i>
                    <input type="text" class="search-input" id="search-input" placeholder="Pesquisar produtos..." autocomplete="off">
                    <button class="search-clear" id="search-clear" style="display: none;"><i class="fa-solid fa-xmark"></i></button>
                </div>
            </div>

            <div class="categories-wrapper">
                <div class="categories-scroll" id="categories-scroll"></div>
            </div>

            <section class="section">
                <div class="section-header">
                    <h2 class="section-title">
                        <i class="fa-solid fa-fire"></i>
                        <span>Catálogo</span>
                    </h2>
                    <span class="section-count" id="section-count"></span>
                </div>

                <div class="products-grid" id="products-grid"></div>

                <div class="empty-state" id="empty-state" style="display: none;">
                    <div class="empty-icon"><i class="fa-solid fa-box-open"></i></div>
                    <div class="empty-title">Nenhum produto encontrado</div>
                    <div class="empty-text" id="empty-text">Tente pesquisar outro termo</div>
                </div>
            </section>
        `;
    }

    function attachStoreHandlers() {
        const input = document.getElementById('search-input');
        const clearBtn = document.getElementById('search-clear');

        if (input) {
            input.value = State.searchQuery;
            input.addEventListener('input', debounce((e) => {
                State.searchQuery = e.target.value.trim();
                if (clearBtn) clearBtn.style.display = State.searchQuery ? 'flex' : 'none';
                renderProducts();
            }, 200));
        }

        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (input) input.value = '';
                State.searchQuery = '';
                clearBtn.style.display = 'none';
                renderProducts();
            });
        }
    }

    function renderCategories() {
        const container = document.getElementById('categories-scroll');
        if (!container) return;

        container.innerHTML = '';

        // Chip "Todos"
        const allChip = document.createElement('button');
        allChip.className = 'category-chip' + (State.currentCategory === CATEGORY_ALL ? ' active' : '');
        allChip.innerHTML = `<span class="chip-emoji">🌐</span><span>Todos</span>`;
        allChip.addEventListener('click', () => selectCategory(CATEGORY_ALL));
        container.appendChild(allChip);

        // Categorias reais
        State.catalog.categories.forEach((cat) => {
            const chip = document.createElement('button');
            chip.className = 'category-chip' + (State.currentCategory === cat.id ? ' active' : '');
            chip.innerHTML = `<span class="chip-emoji">${escapeHtml(cat.emoji)}</span><span>${escapeHtml(cat.name)}</span>`;
            chip.addEventListener('click', () => selectCategory(cat.id));
            container.appendChild(chip);
        });
    }

    function selectCategory(catId) {
        State.currentCategory = catId;
        renderCategories();
        renderProducts();
        haptic('light');
    }

    function getFilteredProducts() {
        let list = State.catalog.products.slice();

        if (State.currentCategory !== CATEGORY_ALL) {
            list = list.filter((p) => p.category_id === State.currentCategory);
        }

        if (State.searchQuery) {
            const q = State.searchQuery.toLowerCase();
            list = list.filter(
                (p) =>
                    p.name.toLowerCase().includes(q) ||
                    (p.description || '').toLowerCase().includes(q)
            );
        }

        return list;
    }

    function renderProducts() {
        const grid = document.getElementById('products-grid');
        const emptyState = document.getElementById('empty-state');
        const countEl = document.getElementById('section-count');

        if (!grid) return;

        const list = getFilteredProducts();

        if (countEl) {
            countEl.textContent = list.length > 0 ? `${list.length} item(ns)` : '';
        }

        if (list.length === 0) {
            grid.innerHTML = '';
            if (emptyState) emptyState.style.display = 'block';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';

        grid.innerHTML = list.map(renderProductCard).join('');

        // Attach handlers
        grid.querySelectorAll('[data-product-id]').forEach((card) => {
            const pid = Number(card.getAttribute('data-product-id'));

            const addBtn = card.querySelector('.product-add-btn');
            if (addBtn && !addBtn.disabled) {
                addBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    addToCart(pid, 1);
                });
            }

            card.addEventListener('click', (e) => {
                if (e.target.closest('.product-add-btn')) return;
                openProductModal(pid);
            });
        });
    }

    function renderProductCard(p) {
        const inCart = State.cart.some((i) => i.product_id === p.id);
        const stockBadge = p.stock <= 0
            ? '<span class="product-badge badge-out">Esgotado</span>'
            : p.stock <= 3
                ? `<span class="product-badge badge-low">Últimas ${p.stock}</span>`
                : '<span class="product-badge badge-stock">Disponível</span>';

        const featuredBadge = p.is_featured ? '<span class="product-badge badge-featured">🔥 TOP</span>' : '';

        const thumbContent = p.image_url
            ? `<img class="product-thumb-img" src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}" loading="lazy">`
            : `<span class="product-emoji">${escapeHtml(p.emoji || '🎬')}</span>`;

        const addBtnContent = inCart
            ? `<i class="fa-solid fa-check"></i> <span>Adicionado</span>`
            : `<i class="fa-solid fa-plus"></i> <span>Adicionar</span>`;

        return `
            <div class="product-card" data-product-id="${p.id}">
                <div class="product-thumb">
                    ${thumbContent}
                    ${stockBadge}
                    ${featuredBadge}
                </div>
                <div class="product-info">
                    <div class="product-name">${escapeHtml(p.name)}</div>
                    <div class="product-stock-info">
                        <i class="fa-solid fa-box"></i>
                        <span>${p.stock} disponível(is)</span>
                    </div>
                    <div class="product-price">
                        <span class="currency">R$</span>
                        <span>${Number(p.price).toFixed(2).replace('.', ',')}</span>
                    </div>
                    <button class="product-add-btn" ${!p.in_stock ? 'disabled' : ''}>
                        ${addBtnContent}
                    </button>
                </div>
            </div>
        `;
    }

    // ============================================
    // 📡 CARREGAR CATÁLOGO
    // ============================================
    async function loadCatalog() {
        const grid = document.getElementById('products-grid');
        if (grid) {
            grid.innerHTML = renderSkeletons(6);
        }

        try {
            const data = await api('/catalog', { method: 'GET' });
            State.catalog.categories = data.categories || [];
            State.catalog.products = data.products || [];
            State.catalog.byId = new Map(
                State.catalog.products.map((p) => [p.id, p])
            );

            renderCategories();
            renderProducts();
        } catch (e) {
            console.error('Erro ao carregar catálogo:', e);
            if (grid) grid.innerHTML = '';
            toast('Erro ao carregar catálogo', 'error');
        }
    }

    function renderSkeletons(n) {
        let html = '';
        for (let i = 0; i < n; i++) {
            html += `
                <div class="skeleton-card">
                    <div class="skeleton-thumb"></div>
                    <div class="skeleton-info">
                        <div class="skeleton-line"></div>
                        <div class="skeleton-line short"></div>
                        <div class="skeleton-line"></div>
                    </div>
                </div>
            `;
        }
        return html;
    }

    // ============================================
    // 🔍 MODAL DE PRODUTO
    // ============================================
    function openProductModal(productId) {
        const p = State.catalog.byId.get(productId);
        if (!p) return;

        const modal = document.getElementById('product-modal');
        const body = document.getElementById('product-modal-body');
        const backdrop = document.getElementById('modal-backdrop');

        if (!modal || !body || !backdrop) return;

        const inCart = State.cart.find((i) => i.product_id === productId);
        const initialQty = inCart ? inCart.quantity : 1;

        const thumbContent = p.image_url
            ? `<img src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}">`
            : `<span>${escapeHtml(p.emoji || '🎬')}</span>`;

        const stockChipClass = p.stock > 5 ? 'success' : p.stock > 0 ? 'warning' : 'danger';
        const stockLabel = p.stock > 0 ? `${p.stock} em estoque` : 'Esgotado';

        body.innerHTML = `
            <div class="modal-product-header">
                <div class="modal-product-thumb">${thumbContent}</div>
                <div class="modal-product-meta">
                    <div class="modal-product-name">${escapeHtml(p.name)}</div>
                    <div class="modal-product-price">
                        <span class="currency">R$</span>
                        <span>${Number(p.price).toFixed(2).replace('.', ',')}</span>
                    </div>
                    <div class="modal-product-stats">
                        <span class="stat-chip ${stockChipClass}">
                            <i class="fa-solid fa-box"></i> ${stockLabel}
                        </span>
                        <span class="stat-chip">
                            <i class="fa-solid fa-shield-halved"></i> ${p.warranty_days}d garantia
                        </span>
                        ${p.total_sold > 0 ? `
                            <span class="stat-chip">
                                <i class="fa-solid fa-fire"></i> ${p.total_sold} vendidos
                            </span>
                        ` : ''}
                    </div>
                </div>
            </div>

            ${p.description ? `
                <div class="modal-section">
                    <div class="modal-section-title">
                        <i class="fa-solid fa-align-left"></i> Descrição
                    </div>
                    <div class="modal-description">${escapeHtml(p.description)}</div>
                </div>
            ` : ''}

            <div class="modal-qty-row">
                <div class="modal-qty-label">Quantidade</div>
                <div class="modal-qty-control">
                    <button class="modal-qty-btn" id="modal-qty-minus" ${initialQty <= 1 ? 'disabled' : ''}>
                        <i class="fa-solid fa-minus"></i>
                    </button>
                    <span class="modal-qty-value" id="modal-qty-value">${initialQty}</span>
                    <button class="modal-qty-btn" id="modal-qty-plus" ${initialQty >= p.max_quantity || initialQty >= p.stock ? 'disabled' : ''}>
                        <i class="fa-solid fa-plus"></i>
                    </button>
                </div>
            </div>

            <button class="btn btn-primary btn-block btn-lg" id="modal-add-btn" ${!p.in_stock ? 'disabled' : ''}>
                <i class="fa-solid fa-cart-plus"></i>
                <span>${!p.in_stock ? 'Esgotado' : inCart ? 'Atualizar Carrinho' : 'Adicionar ao Carrinho'}</span>
            </button>
        `;

        // Attach handlers
        let qty = initialQty;

        const minusBtn = document.getElementById('modal-qty-minus');
        const plusBtn = document.getElementById('modal-qty-plus');
        const qtyValue = document.getElementById('modal-qty-value');
        const addBtn = document.getElementById('modal-add-btn');

        if (minusBtn) {
            minusBtn.addEventListener('click', () => {
                if (qty > 1) {
                    qty--;
                    qtyValue.textContent = qty;
                    minusBtn.disabled = qty <= 1;
                    plusBtn.disabled = qty >= p.max_quantity || qty >= p.stock;
                    haptic('light');
                }
            });
        }

        if (plusBtn) {
            plusBtn.addEventListener('click', () => {
                if (qty < p.max_quantity && qty < p.stock) {
                    qty++;
                    qtyValue.textContent = qty;
                    minusBtn.disabled = qty <= 1;
                    plusBtn.disabled = qty >= p.max_quantity || qty >= p.stock;
                    haptic('light');
                }
            });
        }

        if (addBtn) {
            addBtn.addEventListener('click', () => {
                // Remove se já tinha, adiciona novo
                removeFromCartQuiet(productId);
                addToCart(productId, qty);
                closeModal();
            });
        }

        modal.classList.add('active');
        backdrop.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function removeFromCartQuiet(productId) {
        State.cart = State.cart.filter((i) => i.product_id !== productId);
        saveCartToStorage();
    }

    function closeModal() {
        const modal = document.getElementById('product-modal');
        const backdrop = document.getElementById('modal-backdrop');
        if (modal) modal.classList.remove('active');
        if (backdrop) backdrop.classList.remove('active');
        document.body.style.overflow = '';
    }

    // ============================================
    // 🛒 DRAWER DO CARRINHO
    // ============================================
    function openCartDrawer() {
        const drawer = document.getElementById('cart-drawer');
        const backdrop = document.getElementById('drawer-backdrop');
        if (!drawer || !backdrop) return;

        renderCartDrawer();
        drawer.classList.add('active');
        backdrop.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeCartDrawer() {
        const drawer = document.getElementById('cart-drawer');
        const backdrop = document.getElementById('drawer-backdrop');
        if (drawer) drawer.classList.remove('active');
        if (backdrop) backdrop.classList.remove('active');
        document.body.style.overflow = '';

        // Se estava na aba carrinho, volta pra loja
        if (State.currentPage === 'cart') {
            goToPage('store');
        }
    }

    function renderCartDrawer() {
        const body = document.getElementById('cart-body');
        const footer = document.getElementById('cart-footer');
        if (!body) return;

        if (State.cart.length === 0) {
            body.innerHTML = `
                <div class="cart-empty">
                    <i class="fa-solid fa-bag-shopping"></i>
                    <div class="cart-empty-title">Carrinho vazio</div>
                    <div class="cart-empty-text">Adicione produtos para começar</div>
                </div>
            `;
            if (footer) footer.style.display = 'none';
            return;
        }

        if (footer) footer.style.display = 'block';

        body.innerHTML = State.cart.map((item) => {
            const p = State.catalog.byId.get(item.product_id);
            if (!p) return '';

            const subtotal = p.price * item.quantity;
            const thumbContent = p.image_url
                ? `<img src="${escapeHtml(p.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:inherit;">`
                : escapeHtml(p.emoji || '🎬');

            return `
                <div class="cart-item" data-cart-id="${p.id}">
                    <div class="cart-item-thumb">${thumbContent}</div>
                    <div class="cart-item-info">
                        <div class="cart-item-name">${escapeHtml(p.name)}</div>
                        <div class="cart-item-price">${formatBRL(subtotal)}</div>
                        <div class="cart-item-controls">
                            <div class="qty-control">
                                <button class="qty-btn" data-action="minus" data-id="${p.id}">
                                    <i class="fa-solid fa-minus"></i>
                                </button>
                                <span class="qty-value">${item.quantity}</span>
                                <button class="qty-btn" data-action="plus" data-id="${p.id}">
                                    <i class="fa-solid fa-plus"></i>
                                </button>
                            </div>
                            <button class="cart-item-remove" data-action="remove" data-id="${p.id}">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Attach handlers
        body.querySelectorAll('[data-action]').forEach((btn) => {
            const action = btn.getAttribute('data-action');
            const id = Number(btn.getAttribute('data-id'));

            btn.addEventListener('click', () => {
                if (action === 'plus') updateCartQuantity(id, 1);
                else if (action === 'minus') updateCartQuantity(id, -1);
                else if (action === 'remove') removeFromCart(id);
            });
        });

        updateCartUI();
    }

    // ============================================
    // ✅ CHECKOUT
    // ============================================
    async function doCheckout() {
        if (State.cart.length === 0) {
            toast('Carrinho vazio', 'warning');
            return;
        }

        const btn = document.getElementById('cart-checkout-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> <span>Processando...</span>';
        }

        showLoading('Finalizando compra...');
        haptic('medium');

        try {
            const payload = {
                items: State.cart.map((i) => ({
                    product_id: i.product_id,
                    quantity: i.quantity,
                })),
            };

            const result = await api('/checkout', {
                method: 'POST',
                body: JSON.stringify(payload),
            });

            // Sucesso
            clearCart();
            closeCartDrawer();
            hideLoading();

            // Atualiza saldo
            if (result.new_balance !== undefined) {
                State.user.balance = result.new_balance;
                updateUserUI();
            }

            haptic('success');

            // Modal de sucesso
            showSuccessModal(
                '✅ Compra realizada!',
                `Você adquiriu ${result.orders.length} pedido(s). Confira os detalhes no Telegram!`
            );

            // Recarrega histórico
            setTimeout(() => {
                showHistoryPage();
            }, 2000);

        } catch (e) {
            hideLoading();
            haptic('error');

            let msg = 'Erro ao finalizar compra';

            if (e.status === 402) {
                // Saldo insuficiente
                const detail = e.data && e.data.detail;
                if (detail && typeof detail === 'object') {
                    msg = `Saldo insuficiente. Faltam ${detail.missing_formatted || formatBRL(detail.missing)}`;
                }
            } else if (e.data && e.data.detail) {
                msg = typeof e.data.detail === 'string'
                    ? e.data.detail
                    : e.data.detail.error || msg;
            }

            toast(msg, 'error', 5000);

            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-credit-card"></i> <span>Finalizar Compra</span>';
            }
        }
    }

    // ============================================
    // ✅ MODAL DE SUCESSO
    // ============================================
    function showSuccessModal(title, text) {
        const modal = document.getElementById('success-modal');
        const titleEl = document.getElementById('success-title');
        const textEl = document.getElementById('success-text');
        const backdrop = document.getElementById('modal-backdrop');

        if (!modal) return;

        if (titleEl) titleEl.textContent = title;
        if (textEl) textEl.textContent = text;

        modal.classList.add('active');
        if (backdrop) backdrop.classList.add('active');
    }

    function closeSuccessModal() {
        const modal = document.getElementById('success-modal');
        const backdrop = document.getElementById('modal-backdrop');
        if (modal) modal.classList.remove('active');
        if (backdrop) backdrop.classList.remove('active');
    }

    // ============================================
    // 📜 PÁGINA DE HISTÓRICO
    // ============================================
    async function showHistoryPage() {
        const main = document.getElementById('app-content');
        if (!main) return;

        main.innerHTML = `
            <div class="page-container">
                <div class="page-title">📜 Meus Pedidos</div>
                <div class="page-subtitle">Histórico de compras</div>
                <div id="history-list">
                    ${renderSkeletons(3)}
                </div>
            </div>
        `;

        try {
            const data = await api('/history', { method: 'GET' });
            const list = document.getElementById('history-list');
            if (!list) return;

            if (!data.orders || data.orders.length === 0) {
                list.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-icon"><i class="fa-solid fa-receipt"></i></div>
                        <div class="empty-title">Nenhum pedido ainda</div>
                        <div class="empty-text">Seus pedidos vão aparecer aqui</div>
                    </div>
                `;
                return;
            }

            list.innerHTML = data.orders.map((o) => `
                <div class="order-card">
                    <div class="order-header">
                        <div class="order-name">${escapeHtml(o.product_name)}</div>
                        <span class="order-status-badge ${o.is_active ? 'active' : 'expired'}">
                            ${o.is_active ? 'Ativo' : 'Expirado'}
                        </span>
                    </div>
                    <div class="order-row">
                        <span>Quantidade</span>
                        <span>${o.quantity}</span>
                    </div>
                    <div class="order-row">
                        <span>Valor</span>
                        <span>${o.total_price_formatted}</span>
                    </div>
                    <div class="order-row">
                        <span>Código</span>
                        <span class="order-code">${escapeHtml((o.order_code || '').slice(0, 12))}...</span>
                    </div>
                    <div class="order-row">
                        <span>Data</span>
                        <span>${o.created_at ? new Date(o.created_at).toLocaleDateString('pt-BR') : '—'}</span>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error('Erro histórico:', e);
            toast('Erro ao carregar histórico', 'error');
        }
    }

    // ============================================
    // 💰 PÁGINA DE RECARGA
    // ============================================
    function showRechargePage() {
        const main = document.getElementById('app-content');
        if (!main || !State.config) return;

        const pix = State.config.pix || {};
        const user = State.user || {};

        main.innerHTML = `
            <div class="page-container">
                <div class="page-title">💰 Recarregar Saldo</div>
                <div class="page-subtitle">Adicione saldo via Pix</div>

                <div class="card">
                    <div class="card-title"><i class="fa-solid fa-wallet"></i> Saldo atual</div>
                    <div class="card-value">${formatBRL(user.balance || 0)}</div>
                </div>

                ${pix.bonus_percent > 0 ? `
                    <div class="card">
                        <div class="card-title"><i class="fa-solid fa-gift"></i> Bônus de recarga</div>
                        <div class="card-value">+${pix.bonus_percent}%</div>
                        <div class="card-desc">Em recargas acima de ${formatBRL(pix.bonus_min)}</div>
                    </div>
                ` : ''}

                <div class="card">
                    <div class="card-title"><i class="fa-solid fa-coins"></i> Escolha o valor</div>
                    <div class="card-desc">Mínimo: ${formatBRL(pix.min)} · Máximo: ${formatBRL(pix.max)}</div>
                    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:14px;" id="recharge-quick">
                        ${[10, 20, 30, 50, 100, 200].map((v) => `
                            <button class="btn btn-ghost" data-recharge="${v}">R$ ${v}</button>
                        `).join('')}
                    </div>
                </div>

                <div class="card">
                    <div class="card-title"><i class="fa-solid fa-pen"></i> Valor personalizado</div>
                    <div style="display:flex;gap:8px;margin-top:10px;">
                        <input type="number" id="recharge-custom" class="search-input" style="background:var(--bg-base);padding:12px 14px;border-radius:12px;border:1px solid var(--border-subtle);width:100%;" placeholder="Ex: 25" min="${pix.min}" max="${pix.max}" step="0.01">
                        <button class="btn btn-primary" id="recharge-generate"><i class="fa-solid fa-bolt"></i></button>
                    </div>
                </div>

                <div id="pix-result"></div>
            </div>
        `;

        // Handlers
        main.querySelectorAll('[data-recharge]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const value = Number(btn.getAttribute('data-recharge'));
                generatePix(value);
            });
        });

        const customBtn = document.getElementById('recharge-generate');
        const customInput = document.getElementById('recharge-custom');
        if (customBtn && customInput) {
            customBtn.addEventListener('click', () => {
                const v = Number(customInput.value);
                if (!v || v <= 0) {
                    toast('Valor inválido', 'warning');
                    return;
                }
                generatePix(v);
            });
        }
    }

    async function generatePix(amount) {
        showLoading('Gerando Pix...');
        haptic('medium');

        try {
            const result = await api('/recharge', {
                method: 'POST',
                body: JSON.stringify({ amount }),
            });

            hideLoading();

            const pixResult = document.getElementById('pix-result');
            if (!pixResult) return;

            const qrImage = result.qr_code_base64
                ? `<img src="data:image/png;base64,${result.qr_code_base64}" alt="QR Code">`
                : '';

            pixResult.innerHTML = `
                <div class="pix-box">
                    <div class="pix-qr">${qrImage}</div>
                    <div class="card-title" style="justify-content:center;">
                        <i class="fa-solid fa-qrcode"></i> Escaneie o QR Code
                    </div>
                    <div class="card-desc">Valor: <strong>${result.amount_formatted}</strong>${result.bonus > 0 ? ` · Bônus: +${formatBRL(result.bonus)}` : ''}</div>

                    <div class="pix-code-box" style="margin-top:16px;">${escapeHtml(result.pix_code)}</div>

                    <button class="btn btn-primary btn-block" id="copy-pix-btn" style="margin-top:12px;">
                        <i class="fa-solid fa-copy"></i> Copiar código Pix
                    </button>

                    <button class="btn btn-ghost btn-block" id="check-pix-btn" style="margin-top:8px;">
                        <i class="fa-solid fa-rotate"></i> Já paguei · Verificar
                    </button>
                </div>
            `;

            // Handlers
            const copyBtn = document.getElementById('copy-pix-btn');
            if (copyBtn) {
                copyBtn.addEventListener('click', () => {
                    navigator.clipboard.writeText(result.pix_code).then(() => {
                        haptic('success');
                        toast('Código Pix copiado!', 'success');
                    });
                });
            }

            const checkBtn = document.getElementById('check-pix-btn');
            if (checkBtn) {
                checkBtn.addEventListener('click', () => checkPaymentStatus(result.payment_id));
            }

            haptic('success');
            toast('Pix gerado com sucesso!', 'success');

        } catch (e) {
            hideLoading();
            haptic('error');
            const msg = (e.data && e.data.detail) || 'Erro ao gerar Pix';
            toast(msg, 'error', 4000);
        }
    }

    async function checkPaymentStatus(paymentId) {
        showLoading('Verificando pagamento...');

        try {
            const result = await api(`/payment/${paymentId}`, { method: 'GET' });
            hideLoading();

            if (result.status === 'approved') {
                haptic('success');
                State.user.balance = result.balance;
                updateUserUI();
                showSuccessModal('✅ Pagamento aprovado!', `Seu novo saldo: ${result.balance_formatted}`);

                setTimeout(() => {
                    closeSuccessModal();
                    goToPage('store');
                }, 2500);
            } else if (result.status === 'expired') {
                haptic('error');
                toast('Pagamento expirado', 'warning');
            } else {
                haptic('warning');
                toast('Pagamento ainda pendente', 'info');
            }
        } catch (e) {
            hideLoading();
            toast('Erro ao verificar pagamento', 'error');
        }
    }

    // ============================================
    // 👤 PÁGINA DE PERFIL
    // ============================================
    async function showProfilePage() {
        const main = document.getElementById('app-content');
        if (!main) return;

        try {
            const data = await api('/me', { method: 'GET' });
            State.user = data;

            main.innerHTML = `
                <div class="page-container">
                    <div class="page-title">👤 Meu Perfil</div>
                    <div class="page-subtitle">Suas informações</div>

                    <div class="card">
                        <div class="card-title"><i class="fa-solid fa-user"></i> ${escapeHtml(data.first_name || 'Usuário')}</div>
                        <div class="card-desc">${data.username ? '@' + escapeHtml(data.username) : 'ID: ' + data.telegram_id}</div>
                    </div>

                    <div class="card">
                        <div class="card-title"><i class="fa-solid fa-wallet"></i> Saldo</div>
                        <div class="card-value">${formatBRL(data.balance)}</div>
                    </div>

                    <div class="card">
                        <div class="card-title"><i class="fa-solid fa-chart-line"></i> Estatísticas</div>
                        <div class="order-row"><span>Compras realizadas</span><span>${data.purchases_count}</span></div>
                        <div class="order-row"><span>Total gasto</span><span>${formatBRL(data.total_spent)}</span></div>
                        <div class="order-row"><span>Total recarregado</span><span>${formatBRL(data.total_recharged)}</span></div>
                    </div>

                    <button class="btn btn-ghost btn-block" id="profile-history" style="margin-top:12px;">
                        <i class="fa-solid fa-clock-rotate-left"></i> Ver pedidos
                    </button>
                </div>
            `;

            const histBtn = document.getElementById('profile-history');
            if (histBtn) {
                histBtn.addEventListener('click', () => goToPage('history'));
            }
        } catch (e) {
            console.error('Erro perfil:', e);
            main.innerHTML = `<div class="page-container"><div class="empty-state"><div class="empty-title">Erro ao carregar perfil</div></div></div>`;
        }
    }

    // ============================================
    // 🎨 UPDATE UI DO USUÁRIO
    // ============================================
    function updateUserUI() {
        const balanceEl = document.getElementById('header-balance-value');
        if (balanceEl && State.user) {
            balanceEl.textContent = formatBRL(State.user.balance);
        }

        const cartBalanceEl = document.getElementById('cart-balance');
        if (cartBalanceEl && State.user) {
            cartBalanceEl.textContent = formatBRL(State.user.balance);
        }
    }

    // ============================================
    // 🎨 APLICAR CONFIG VISUAL
    // ============================================
    function applyConfig(config) {
        State.config = config;

        const root = document.documentElement;

        if (config.colors) {
            const c = config.colors;
            if (c.primary) root.style.setProperty('--color-primary', c.primary);
            if (c.accent) root.style.setProperty('--color-accent', c.accent);
            if (c.success) root.style.setProperty('--color-success', c.success);
            if (c.warning) root.style.setProperty('--color-warning', c.warning);
            if (c.danger) root.style.setProperty('--color-danger', c.danger);
        }

        // Nome / Title
        if (config.site_title || config.bot_name) {
            const title = config.site_title || config.bot_name;
            document.title = title;
            const nameEl = document.getElementById('header-name');
            if (nameEl) nameEl.textContent = title;
            const splashNameEl = document.getElementById('splash-name');
            if (splashNameEl) splashNameEl.textContent = title;
        }

        // Logo
        if (config.logo_url) {
            const logoImg = document.getElementById('header-logo-img');
            const logoEmoji = document.getElementById('header-logo-emoji');
            if (logoImg && logoEmoji) {
                logoImg.src = config.logo_url;
                logoImg.style.display = 'block';
                logoEmoji.style.display = 'none';
            }
        }

        // Banner
        if (config.banner_text) {
            const banner = document.getElementById('banner');
            const bannerText = document.getElementById('banner-text');
            if (banner && bannerText) {
                bannerText.textContent = config.banner_text;
                banner.style.display = 'flex';
            }
        }
    }

    // ============================================
    // 🎯 INICIALIZAÇÃO
    // ============================================
    async function init() {
        if (State.initialized) return;

        // Telegram SDK
        State.tg = window.Telegram && window.Telegram.WebApp;

        if (State.tg) {
            try {
                State.tg.ready();
                State.tg.expand();

                if (State.tg.setHeaderColor) State.tg.setHeaderColor('#0a0a0f');
                if (State.tg.setBackgroundColor) State.tg.setBackgroundColor('#0a0a0f');

                State.initData = State.tg.initData || '';
            } catch (e) {
                console.warn('Erro ao configurar Telegram SDK:', e);
            }
        }

        // Se não tem initData, permite demo (você pode testar no navegador)
        if (!State.initData) {
            console.warn('initData vazio — usando modo demo');

            // Modo demo: cria um initData fake só pra testar visual
            // Em produção, isso nunca acontece porque só abre pelo Telegram
        }

        // Carrega config (não precisa de auth)
        try {
            const config = await api('/config', { method: 'GET' });
            applyConfig(config);
        } catch (e) {
            console.warn('Erro ao carregar config:', e);
        }

        // Carrega cart do storage
        loadCartFromStorage();

        // Autentica + carrega dados do usuário
        if (State.initData) {
            try {
                const auth = await api('/auth', { method: 'POST' });
                State.user = auth.user;
                updateUserUI();
            } catch (e) {
                console.error('Erro na autenticação:', e);
                toast('Erro ao autenticar', 'error');
            }
        } else {
            // Modo demo sem auth
            State.user = {
                telegram_id: 0,
                first_name: 'Visitante',
                username: null,
                balance: 0,
                points: 0,
            };
        }

        // Renderiza loja
        showStorePage();

        // Esconde splash
        const splash = document.getElementById('splash');
        const app = document.getElementById('app');
        if (app) app.style.display = 'block';

        setTimeout(() => {
            if (splash) splash.classList.add('hidden');
        }, 500);

        State.initialized = true;
        updateCartUI();
    }

    // ============================================
    // 🎯 EVENTOS GLOBAIS
    // ============================================
    function attachGlobalEvents() {
        // Bottom nav
        document.querySelectorAll('.nav-item').forEach((btn) => {
            btn.addEventListener('click', () => {
                const target = btn.getAttribute('data-nav');
                if (target) goToPage(target);
            });
        });

        // Header cart
        const headerCartBtn = document.getElementById('header-cart-btn');
        if (headerCartBtn) {
            headerCartBtn.addEventListener('click', openCartDrawer);
        }

        // Header balance → recarga
        const headerBalance = document.getElementById('header-balance');
        if (headerBalance) {
            headerBalance.addEventListener('click', () => goToPage('recharge'));
        }

        // Cart close
        const cartClose = document.getElementById('cart-close');
        if (cartClose) cartClose.addEventListener('click', closeCartDrawer);

        // Cart backdrop
        const drawerBackdrop = document.getElementById('drawer-backdrop');
        if (drawerBackdrop) drawerBackdrop.addEventListener('click', closeCartDrawer);

        // Modal backdrop
        const modalBackdrop = document.getElementById('modal-backdrop');
        if (modalBackdrop) {
            modalBackdrop.addEventListener('click', () => {
                closeModal();
                closeSuccessModal();
            });
        }

        // Cart checkout
        const checkoutBtn = document.getElementById('cart-checkout-btn');
        if (checkoutBtn) checkoutBtn.addEventListener('click', doCheckout);

        // Cart clear
        const clearBtn = document.getElementById('cart-clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                if (State.cart.length === 0) return;
                if (confirm('Limpar todo o carrinho?')) {
                    clearCart();
                    toast('Carrinho limpo', 'info');
                }
            });
        }

        // Success close
        const successClose = document.getElementById('success-close-btn');
        if (successClose) {
            successClose.addEventListener('click', () => {
                closeSuccessModal();
                goToPage('store');
            });
        }

        // Banner close
        const bannerClose = document.getElementById('banner-close');
        if (bannerClose) {
            bannerClose.addEventListener('click', () => {
                const banner = document.getElementById('banner');
                if (banner) banner.style.display = 'none';
            });
        }

        // Header scroll effect
        const header = document.getElementById('app-header');
        if (header) {
            window.addEventListener('scroll', () => {
                if (window.scrollY > 10) header.classList.add('scrolled');
                else header.classList.remove('scrolled');
            }, { passive: true });
        }
    }

    // ============================================
    // 🚀 BOOT
    // ============================================
    document.addEventListener('DOMContentLoaded', () => {
        attachGlobalEvents();
        init();
    });

    // Fecha modais com ESC
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal();
            closeSuccessModal();
            closeCartDrawer();
        }
    });

    // Expõe global (para debug)
    window.LarizinhaApp = {
        State,
        api,
        addToCart,
        removeFromCart,
        clearCart,
        goToPage,
        toast,
    };

})();
