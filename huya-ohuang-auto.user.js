// ==UserScript==
// @name         虎牙欧皇时刻自动点击
// @namespace    https://github.com/yazhuo-wyze/huya-oh
// @version      1.1.0
// @description  自动参与虎牙直播「欧皇时刻」活动：检测入口、选择限时免费、观看视频免费参与、循环累计幸运值
// @author       yazhuo-wyze
// @match        https://www.huya.com/*
// @match        https://*.huya.com/*
// @include      https://www.huya.com/*
// @include      https://*.huya.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

// ⚠️ 如果看到这行日志，说明脚本已被 Tampermonkey 注入
console.log('%c[虎牙欧皇] 脚本已注入！%c 版本 1.1.0', 'color: #ffd700; font-size: 16px; font-weight: bold', 'color: #aaa');

(function () {
    'use strict';

    // 二次确认：脚本入口被执行
    console.log('%c[虎牙欧皇] 主函数开始执行 %c' + new Date().toLocaleTimeString(), 'color: #0f0', 'color: #aaa');

    // ======================== 配置常量 ========================
    const CONFIG = {
        MAX_LUCKY_VALUE: 200,           // 幸运值累计上限
        COUNTDOWN_POLL_MS: 1000,        // 倒计时检测间隔（毫秒）
        FALLBACK_MAX_WAIT_MS: 45000,    // 奖励弹窗兜底等待时间
        RETRY_INTERVAL_MS: 3000,        // 元素查找重试间隔
        CLICK_DELAY_MIN_MS: 500,        // 点击最小延迟
        CLICK_DELAY_MAX_MS: 1500,       // 点击最大延迟
        CYCLE_COOLDOWN_MS: 2000,        // 每轮循环冷却时间
        NAV_CHECK_INTERVAL_MS: 3000,    // 导航栏轮询间隔（fallback）
        POPUP_CLOSE_DELAY_MS: 1000,     // 弹窗关闭后等待时间
    };

    const STATE_KEYS = {
        LUCKY: 'huya_oh_lucky',
        COMPLETED: 'huya_oh_completed',
    };

    // ======================== 日志工具 ========================
    const TAG = '[虎牙欧皇]';

    function log(msg) {
        console.log(`${TAG} ${msg}`);
    }

    function warn(msg) {
        console.warn(`${TAG} ⚠️ ${msg}`);
    }

    function error(msg) {
        console.error(`${TAG} ❌ ${msg}`);
    }

    // ======================== 工具函数 ========================

    /** 随机延迟（毫秒） */
    function randomDelay(min, max) {
        return new Promise(resolve => setTimeout(resolve, min + Math.random() * (max - min)));
    }

    /** 等待指定毫秒 */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /** 模拟人类点击的随机延迟后执行回调 */
    async function humanDelay(min, max) {
        const delay = min + Math.random() * (max - min);
        await sleep(Math.floor(delay));
    }

    /**
     * 在 DOM 中查找包含指定文本的可见元素
     * @param {string} text 要匹配的文本
     * @param {string} [tag='*'] 限定标签名
     * @param {Element} [root=document] 搜索根节点
     * @returns {Element|null}
     */
    function findByText(text, tag = '*', root = document) {
        const elements = root.querySelectorAll(tag);
        for (const el of elements) {
            // 跳过不可见元素
            if (el.offsetParent === null && !(el instanceof HTMLElement && el.style.display !== 'none')) {
                continue;
            }
            // 获取元素自身的文本（不包含子元素中与 text 无关的文本）
            const directText = Array.from(el.childNodes)
                .filter(n => n.nodeType === Node.TEXT_NODE)
                .map(n => n.textContent)
                .join('');
            const fullText = (el.textContent || '').trim();

            if (directText.includes(text) || fullText === text) {
                return el;
            }
        }
        return null;
    }

    /**
     * 通用文本查找（返回第一个匹配元素，适用于按钮等）
     * 支持跨层查找，只要 textContent 包含目标文本即可
     */
    function findElementContainingText(text, root = document) {
        console.log(`${TAG} findElementContainingText: 查找 "${text}"`);

        const scope = root && typeof root.createTreeWalker === 'function'
            ? root
            : (root?.ownerDocument || document);
        const walker = scope.createTreeWalker(
            root,
            NodeFilter.SHOW_ELEMENT,
            {
                acceptNode: function (node) {
                    // 跳过不可见和超大容器
                    if (node.offsetHeight === 0 && node.offsetWidth === 0) return NodeFilter.FILTER_SKIP;
                    if (node.tagName === 'HTML' || node.tagName === 'BODY') return NodeFilter.FILTER_SKIP;
                    // 放宽子元素数量限制，避免漏掉复杂结构的按钮
                    if (node.children.length > 50) return NodeFilter.FILTER_SKIP;
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        let node;
        while ((node = walker.nextNode())) {
            const txt = (node.textContent || '').trim();
            if (txt === text || (txt.includes(text) && txt.length < text.length + 10)) {
                // 找到最小的包含目标文本的元素
                let target = node;
                for (let child of target.children) {
                    if ((child.textContent || '').trim() === text) {
                        target = child;
                        break;
                    }
                }
                console.log(`${TAG} findElementContainingText: 找到匹配元素 ${target.tagName}, text="${txt.substring(0, 50)}"`);
                return target;
            }
        }
        console.log(`${TAG} findElementContainingText: 未找到匹配 "${text}"`);
        return null;
    }

    /**
     * 等待指定文本的元素出现
     * @param {string} text 目标文本
     * @param {number} [timeoutMs=15000] 超时时间
     * @param {number} [intervalMs=500] 检测间隔
     * @returns {Promise<Element|null>}
     */
    async function waitForText(text, timeoutMs = 15000, intervalMs = 500) {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const el = findElementContainingText(text);
            if (el) return el;
            await sleep(intervalMs);
        }
        return null;
    }

    /**
     * 安全点击元素（模拟真实用户点击，适配 React 渲染的元素）
     */
    function safeClick(el) {
        if (!el) {
            console.error(`${TAG} safeClick: 元素为空`);
            return false;
        }

        console.log(`${TAG} safeClick: 尝试点击元素 tag=${el.tagName}, text="${(el.textContent || '').substring(0, 30)}"`);

        const win = el.ownerDocument?.defaultView || window;
        const rect = el.getBoundingClientRect();
        console.log(`${TAG} safeClick: 元素位置 rect={left:${rect.left}, top:${rect.top}, width:${rect.width}, height:${rect.height}}`);

        // 检查元素是否可见
        if (rect.width === 0 || rect.height === 0) {
            console.warn(`${TAG} safeClick: 元素尺寸为0，尝试查找内部可点击子元素`);
            const innerClickable = el.querySelector('button, a, [role="button"], i, span');
            if (innerClickable) {
                return safeClick(innerClickable);
            }
            return false;
        }

        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;

        // 确保元素在视口内
        if (cx < 0 || cy < 0 || cx > win.innerWidth || cy > win.innerHeight) {
            console.warn(`${TAG} safeClick: 元素不在视口内，尝试滚动到可见区域`);
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            sleep(300); // 等待滚动完成
        }

        // 模拟完整鼠标事件序列（React 合成事件需要这些原生事件）
        const events = [
            new win.MouseEvent('mouseover', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: win }),
            new win.MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: win, button: 0 }),
            new win.MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: win, button: 0 }),
            new win.MouseEvent('click', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: win, button: 0, detail: 1 }),
        ];

        events.forEach(evt => {
            try {
                el.dispatchEvent(evt);
            } catch (e) {
                console.warn(`${TAG} safeClick: 派发事件失败 ${evt.type}:`, e.message);
            }
        });

        // 尝试原生 click
        try {
            el.click();
        } catch (e) {
            console.warn(`${TAG} safeClick: 原生 click 失败:`, e.message);
        }

        // 如果元素是 div 且没有被点击，尝试点击其父元素或子元素
        if (el.tagName === 'DIV') {
            // 尝试触发其内部可点击元素
            const inner = el.querySelector('i, span, a, button');
            if (inner) {
                try { inner.click(); } catch (e) { /* ignore */ }
            }
        }

        console.log(`${TAG} safeClick: 点击完成`);
        return true;
    }

    /** 获取随机点击延迟 */
    function getClickDelay() {
        return CONFIG.CLICK_DELAY_MIN_MS + Math.random() * (CONFIG.CLICK_DELAY_MAX_MS - CONFIG.CLICK_DELAY_MIN_MS);
    }

    function isTopFrame() {
        try {
            return window.top === window;
        } catch (e) {
            return true;
        }
    }

    function readCookie(name) {
        const cookies = document.cookie ? document.cookie.split('; ') : [];
        const prefix = `${name}=`;
        for (const item of cookies) {
            if (item.startsWith(prefix)) {
                return decodeURIComponent(item.slice(prefix.length));
            }
        }
        return null;
    }

    function writeCookie(name, value, maxAgeSeconds = 86400) {
        try {
            document.cookie = `${name}=${encodeURIComponent(String(value))}; domain=.huya.com; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`;
        } catch (e) {
            warn(`写入 Cookie 失败: ${name}`);
        }
    }

    function deleteCookie(name) {
        try {
            document.cookie = `${name}=; domain=.huya.com; path=/; max-age=0; SameSite=Lax`;
        } catch (e) {
            warn(`删除 Cookie 失败: ${name}`);
        }
    }

    function readLuckyState() {
        const raw = readCookie(STATE_KEYS.LUCKY);
        if (raw == null) return null;
        const val = parseInt(raw, 10);
        return Number.isFinite(val) ? val : null;
    }

    function syncLuckyState(nextLucky) {
        if (!Number.isFinite(nextLucky)) return;
        const normalized = Math.max(0, Math.floor(nextLucky));
        if (normalized === currentLuckyValue) return;
        const prev = currentLuckyValue;
        currentLuckyValue = normalized;
        writeCookie(STATE_KEYS.LUCKY, String(normalized));
        log(`📊 幸运值同步: ${prev} → ${normalized}`);
    }

    function markCompleted() {
        isCompleted = true;
        writeCookie(STATE_KEYS.COMPLETED, '1');
        writeCookie(STATE_KEYS.LUCKY, String(CONFIG.MAX_LUCKY_VALUE));
        log('🏁 幸运值已达到 200，任务完成！');
    }

    function isCompletedState() {
        return readCookie(STATE_KEYS.COMPLETED) === '1';
    }

    function clearCompletedState() {
        deleteCookie(STATE_KEYS.COMPLETED);
    }

    function getPageMode() {
        if (location.hostname === 'www.huya.com') return 'room';
        if (location.hostname.endsWith('huya.com')) return 'activity';
        return 'other';
    }

    function getFrameDocument(selector) {
        const frame = document.querySelector(selector);
        if (!frame) return null;
        try {
            return frame.contentDocument || frame.contentWindow?.document || null;
        } catch (e) {
            return null;
        }
    }

    async function waitForFrameDocument(selector, timeoutMs = CONFIG.FALLBACK_MAX_WAIT_MS, intervalMs = CONFIG.COUNTDOWN_POLL_MS) {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            const doc = getFrameDocument(selector);
            if (doc) return doc;
            await sleep(intervalMs);
        }
        return null;
    }

    function clickTextInRoot(text, root = document) {
        const el = findElementContainingText(text, root);
        if (!el) return null;
        safeClick(el);
        return el;
    }

    function closeRootByText(root = document, texts = ['关闭广告', '关闭', '×', '✕', 'X']) {
        for (const text of texts) {
            const el = findElementContainingText(text, root);
            if (el) {
                safeClick(el);
                return true;
            }
        }
        return false;
    }

    function parseLuckyValueFromRoot(root = document) {
        const candidates = [];
        const elements = root.querySelectorAll('div, span, p, strong, em, button, a');
        const patterns = [
            /累计幸运值\s*(\d+)/,
            /幸运值\s*[:：]?\s*(\d+)/,
            /幸运值[^0-9]{0,8}(\d+)/,
        ];

        for (const el of elements) {
            if (el.offsetParent === null) continue;

            const text = (el.innerText || el.textContent || '').trim();
            if (!text.includes('幸运值') && !text.includes('累计幸运值')) continue;

            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (!match) continue;

                const val = parseInt(match[1], 10);
                if (Number.isFinite(val) && val >= 0 && val <= 200) {
                    candidates.push(val);
                }
            }
        }

        return candidates.length > 0 ? Math.max(...candidates) : null;
    }

    function getSuperLuckyFrameDoc() {
        return getFrameDocument('iframe[src*="super_lucky_time"]');
    }

    function getTaskExtFrameDoc() {
        const direct = getFrameDocument('iframe[src*="task-ext"]');
        if (direct) return direct;

        const superDoc = getSuperLuckyFrameDoc();
        if (superDoc) {
            const frame = superDoc.querySelector('iframe[src*="task-ext"]');
            if (frame) {
                try {
                    return frame.contentDocument || frame.contentWindow?.document || null;
                } catch (e) {
                    return null;
                }
            }
        }

        return null;
    }

    async function waitForTaskFrame(timeoutMs = CONFIG.FALLBACK_MAX_WAIT_MS) {
        const direct = await waitForFrameDocument('iframe[src*="task-ext"]', timeoutMs);
        if (direct) return direct;

        const superDoc = getSuperLuckyFrameDoc();
        if (superDoc) {
            const frame = superDoc.querySelector('iframe[src*="task-ext"]');
            if (frame) {
                try {
                    return frame.contentDocument || frame.contentWindow?.document || null;
                } catch (e) {
                    return null;
                }
            }
        }

        return null;
    }

    async function closeActivityPopups() {
        const taskDoc = getTaskExtFrameDoc();
        if (taskDoc) {
            closeRootByText(taskDoc);
            await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
            closeRootByText(taskDoc);
        }

        const superDoc = getSuperLuckyFrameDoc();
        if (superDoc) {
            closeRootByText(superDoc);
            await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
            closeRootByText(superDoc);
        }

        closeRootByText(document);
        await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
    }

    // ======================== 业务逻辑 ========================

    /** 当前累计幸运值 */
    let currentLuckyValue = 0;

    /** 已执行的循环次数 */
    let cycleCount = 0;

    /** 最近一次点击房间入口的时间 */
    let lastRoomEntryClickAt = 0;

    /** 是否正在运行中（防止重入） */
    let isRunning = false;

    /** 当天是否已完成（达到200） */
    let isCompleted = false;

    /**
     * 解析页面显示的幸运值
     * 支持格式："12" 或 "幸运值：12" 等
     */
    function parseLuckyValue(root = document) {
        return parseLuckyValueFromRoot(root);
    }

    /**
     * 解析奖励弹窗里的幸运值增量
     * 例如："+10" 或 "幸运值+5"
     */
    function parseRewardLuckyGain(root = document) {
        const candidates = [];
        const elements = root.querySelectorAll('div, span, p, button, a');
        const patterns = [
            /[+＋]\s*(\d+)/,
            /幸运值\s*[+＋]\s*(\d+)/,
        ];

        for (const el of elements) {
            if (el.offsetParent === null) continue;

            const text = (el.innerText || el.textContent || '').trim();
            if (!text.includes('+') && !text.includes('＋')) continue;

            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (!match) continue;

                const gain = parseInt(match[1], 10);
                if (Number.isFinite(gain) && gain > 0 && gain <= 200) {
                    candidates.push(gain);
                }
            }
        }

        return candidates.length > 0 ? Math.max(...candidates) : null;
    }

    /**
     * 检测欧皇时刻入口按钮
     * 支持直播间消息里的真实入口和旧版兜底选择器
     */
    function detectOhuangEntry() {
        const selectors = [
            'span.J_msg_action[data-action*="super_lucky_time"]',
            'span.J_msg_action[data-action*="super-lucky-time"]',
            '.player-lucky-burst-icon',
            '[class*="lucky-burst"]',
            '[class*="ohuang"]',
            '[class*="burst"]',
        ];

        for (const selector of selectors) {
            const entries = document.querySelectorAll(selector);
            for (const entryBtn of entries) {
                if (entryBtn.offsetParent === null) continue;

                const actionText = (entryBtn.getAttribute('data-action') || '') + ' ' + (entryBtn.textContent || '');
                if (selector.includes('J_msg_action') && !actionText.includes('super_lucky_time')) {
                    continue;
                }

                console.log(`${TAG} detectOhuangEntry: 通过选择器 "${selector}" 找到入口`);
                return entryBtn;
            }
        }

        const fallbackTexts = ['去参与', '欧皇免费抽点券', '欧皇时刻'];
        for (const text of fallbackTexts) {
            const el = findElementContainingText(text);
            if (el) {
                console.log(`${TAG} detectOhuangEntry: 通过文本 "${text}" 找到入口`);
                return el;
            }
        }

        return null;
    }

    /**
     * 等待奖励弹窗出现
     * 返回 true 表示找到了可领取的奖励，false 表示超时
     */
    async function waitForRewardPopup(root = document) {
        log('⏳ 等待活动内容...');
        const startTime = Date.now();

        while (Date.now() - startTime < CONFIG.FALLBACK_MAX_WAIT_MS) {
            const gain = parseRewardLuckyGain(root);
            if (gain !== null) {
                log(`   已检测到增量 +${gain}`);
                return true;
            }

            const doneEl = findElementContainingText('看视频免费参与', root);
            if (doneEl) {
                log('✅ 检测到「看视频免费参与」按钮');
                return true;
            }

            const boostEl = findElementContainingText('累计幸运值', root);
            if (boostEl) {
                log('✅ 检测到幸运值显示');
                return true;
            }

            const legacyDoneEl = findElementContainingText('恭喜完成任务', root);
            if (legacyDoneEl) {
                log('✅ 检测到任务完成按钮');
                return true;
            }

            await sleep(CONFIG.COUNTDOWN_POLL_MS);
        }

        warn('活动内容等待超时');
        return false;
    }

    /**
     * 关闭奖励弹窗
     * 尝试多种关闭方式
     */
    async function closeRewardPopup() {
        log('❌ 关闭活动弹层...');
        await closeActivityPopups();
        return true;
    }

    /**
     * 主循环入口：根据当前页面类型执行一次动作
     * @returns {boolean} 是否成功完成
     */
    async function runOneCycle() {
        if (!isTopFrame()) {
            return false;
        }

        const mode = getPageMode();
        if (mode === 'room') {
            if (isCompletedState()) {
                isCompleted = true;
                return true;
            }

            if (Date.now() - lastRoomEntryClickAt < 5000) {
                return false;
            }

            const entry = detectOhuangEntry();
            if (!entry) {
                return false;
            }

            const timerText = (entry.textContent || '').trim();
            log(`🔔 检测到欧皇入口 ${timerText ? `(${timerText})` : ''}`);
            await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
            safeClick(entry);
            lastRoomEntryClickAt = Date.now();
            log('✅ 已点击直播间入口，等待活动页加载');
            await sleep(2500);
            return true;
        }

        if (mode !== 'activity') {
            return false;
        }

        const superDoc = getSuperLuckyFrameDoc();
        if (!superDoc) {
            return false;
        }

        cycleCount++;
        log(`🔄 第 ${cycleCount} 轮开始`);

        const luckyOnPage = parseLuckyValue(superDoc);
        if (luckyOnPage !== null) {
            syncLuckyState(luckyOnPage);
        } else if (currentLuckyValue === 0) {
            const luckyFromState = readLuckyState();
            if (luckyFromState !== null) {
                syncLuckyState(luckyFromState);
            }
        }

        if (currentLuckyValue >= CONFIG.MAX_LUCKY_VALUE) {
            markCompleted();
            await closeActivityPopups();
            return true;
        }

        if (!(await waitForRewardPopup(superDoc))) {
            return false;
        }

        const freeOption = findElementContainingText('限时免费', superDoc) || findElementContainingText('免费抽', superDoc);
        if (freeOption) {
            await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
            safeClick(freeOption);
            log('🎯 已选择「限时免费」');
            await sleep(400);
        }

        const participateBtn = findElementContainingText('看视频免费参与', superDoc);
        if (!participateBtn) {
            warn('未找到「看视频免费参与」按钮，等待下一次轮询');
            return false;
        }

        await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
        safeClick(participateBtn);
        log('▶️ 已点击「看视频免费参与」');

        const taskDoc = await waitForTaskFrame();
        if (!taskDoc) {
            warn('未检测到 task-ext 任务页');
            return false;
        }

        const doneBtn = findElementContainingText('恭喜完成任务', taskDoc) || findElementContainingText('直接领取', taskDoc);
        if (doneBtn) {
            await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
            safeClick(doneBtn);
            log('✅ 已点击「恭喜完成任务」');
            await sleep(1000);
        } else {
            warn('未找到「恭喜完成任务」按钮');
        }

        const rewardGain = parseRewardLuckyGain(superDoc) ?? parseRewardLuckyGain(taskDoc) ?? 10;
        await closeActivityPopups();
        await sleep(CONFIG.CYCLE_COOLDOWN_MS);

        const refreshedLucky = parseLuckyValue(superDoc);
        if (refreshedLucky !== null) {
            syncLuckyState(refreshedLucky);
        } else {
            syncLuckyState(currentLuckyValue + rewardGain);
            log(`📊 未读取到精确幸运值，按 +${rewardGain} 估算`);
        }

        if (currentLuckyValue >= CONFIG.MAX_LUCKY_VALUE) {
            markCompleted();
            await closeActivityPopups();
        } else {
            log(`✅ 第 ${cycleCount} 轮完成，当前幸运值 ${currentLuckyValue}`);
        }

        return true;
    }

    /**
     * 点击欧皇入口进入活动
     */
    async function enterActivity() {
        return runOneCycle();
    }

    /**
     * 主循环：根据当前页面类型持续执行入口点击 / 活动参与
     */
    async function mainLoop() {
        if (isRunning) return;
        if (!isTopFrame()) return;
        isRunning = true;

        try {
            if (isCompletedState()) {
                isCompleted = true;
                log('🎉 今日欧皇时刻已完成，停止自动点击');
                return;
            }

            const luckyFromState = readLuckyState();
            if (luckyFromState !== null) {
                syncLuckyState(luckyFromState);
            }

            log(`🚀 虎牙欧皇时刻自动脚本启动 (${getPageMode()})`);
            const done = await runOneCycle();
            if (!done) {
                await sleep(CONFIG.RETRY_INTERVAL_MS);
            }
        } catch (e) {
            error(`主循环异常: ${e.message}\n${e.stack}`);
            await sleep(CONFIG.RETRY_INTERVAL_MS);
        } finally {
            isRunning = false;
        }
    }

    // ======================== 入口触发 ========================

    /**
     * 使用 MutationObserver + 定时轮询监听欧皇入口
     */
    function startWatching() {
        if (!isTopFrame()) {
            return;
        }

        const banner = [
            '╔══════════════════════════════════╗',
            '║   🎰 虎牙欧皇时刻自动脚本 v1.1  ║',
            '║   监听中...                     ║',
            `║   页面: ${location.href.substring(0, 50)}`,
            '╚══════════════════════════════════╝',
        ];
        banner.forEach(line => console.log(line));

        // 立即检查（不延迟）
        function checkNow() {
            if (isRunning || isCompleted) return false;
            mainLoop();
            return true;
        }

        // 立即首次检查
        checkNow();

        // 1秒、2秒、3秒、5秒各检查一次（覆盖异步加载窗口）
        [1000, 2000, 3000, 5000].forEach(delay => {
            setTimeout(() => {
                if (!isRunning && !isCompleted) {
                    const found = checkNow();
                    if (!found && delay === 5000) {
                        log('👀 暂未检测到欧皇入口，持续监听中...');
                        // 输出页面结构信息以便调试
                        const anyPlayer = document.querySelector('[class*="player"]');
                        if (anyPlayer) {
                            log(`🔍 页面中有 player 相关元素: ${anyPlayer.className.substring(0, 100)}`);
                        }
                    }
                }
            }, delay);
        });

        // 回调防抖（减少到 500ms，更快响应）
        let debounceTimer = null;
        function onDomChange() {
            if (isRunning || isCompleted) return;
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(checkNow, 500);
        }

        // MutationObserver
        const observer = new MutationObserver(onDomChange);
        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });

        // 定时轮询（每 2 秒一次，更频繁）
        setInterval(checkNow, 2000);

        // 心跳日志：每 30 秒输出一次，证明脚本仍在运行
        setInterval(() => {
            if (!isRunning && !isCompleted) {
                const entry = detectOhuangEntry();
                const status = entry ? '检测到入口' : '等待活动开始';
                log(`💓 心跳: ${status} | 已运行 ${Math.floor((Date.now() - startTime) / 1000)}s`);
            }
        }, 30000);
    }

    /** 脚本启动时间 */
    const startTime = Date.now();

    // ======================== 启动 ========================
    // 虎牙是 SPA，即使 DOM 已加载完也可能还需要等异步组件
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        startWatching();
    } else {
        window.addEventListener('load', startWatching);
    }
})();
