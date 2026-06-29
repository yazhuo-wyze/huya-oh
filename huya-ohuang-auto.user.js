// ==UserScript==
// @name         虎牙欧皇时刻自动点击
// @namespace    https://github.com/yazhuo-wyze/huya-oh
// @version      1.0.1
// @description  自动参与虎牙直播「欧皇时刻」活动：检测入口、选择免费抽+10、看视频、领取奖励、循环累计幸运值
// @author       yazhuo-wyze
// @match        https://www.huya.com/*
// @match        https://*.huya.com/*
// @include      https://www.huya.com/*
// @include      https://*.huya.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

// ⚠️ 如果看到这行日志，说明脚本已被 Tampermonkey 注入
console.log('%c[虎牙欧皇] 脚本已注入！%c 版本 1.0.1', 'color: #ffd700; font-size: 16px; font-weight: bold', 'color: #aaa');

(function () {
    'use strict';

    // 二次确认：脚本入口被执行
    console.log('%c[虎牙欧皇] 主函数开始执行 %c' + new Date().toLocaleTimeString(), 'color: #0f0', 'color: #aaa');

    // ======================== 配置常量 ========================
    const CONFIG = {
        MAX_LUCKY_VALUE: 200,           // 幸运值累计上限
        COUNTDOWN_POLL_MS: 1000,        // 倒计时检测间隔（毫秒）
        FALLBACK_MAX_WAIT_MS: 45000,    // 视频倒计时兜底等待时间
        RETRY_INTERVAL_MS: 3000,        // 元素查找重试间隔
        CLICK_DELAY_MIN_MS: 500,        // 点击最小延迟
        CLICK_DELAY_MAX_MS: 1500,       // 点击最大延迟
        CYCLE_COOLDOWN_MS: 2000,        // 每轮循环冷却时间
        NAV_CHECK_INTERVAL_MS: 3000,    // 导航栏轮询间隔（fallback）
        POPUP_CLOSE_DELAY_MS: 1000,     // 弹窗关闭后等待时间
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

        const walker = document.createTreeWalker(
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
        if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) {
            console.warn(`${TAG} safeClick: 元素不在视口内，尝试滚动到可见区域`);
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            sleep(300); // 等待滚动完成
        }

        // 模拟完整鼠标事件序列（React 合成事件需要这些原生事件）
        const events = [
            new MouseEvent('mouseover', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: window }),
            new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: window, button: 0 }),
            new MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: window, button: 0 }),
            new MouseEvent('click', { bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: window, button: 0, detail: 1 }),
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

    // ======================== 业务逻辑 ========================

    /** 当前累计幸运值 */
    let currentLuckyValue = 0;

    /** 已执行的循环次数 */
    let cycleCount = 0;

    /** 是否正在运行中（防止重入） */
    let isRunning = false;

    /** 当天是否已完成（达到200） */
    let isCompleted = false;

    /**
     * 解析页面显示的幸运值
     * 支持格式："12" 或 "幸运值：12" 等
     */
    function parseLuckyValue() {
        // 尝试多种可能的显示位置
        const candidates = [];

        // 方案1: 查找包含"幸运值"的元素（使用更高效的查询）
        const luckyLabelElements = [];
        // 只搜索特定类名的元素，而不是全部 *
        const possibleElements = document.querySelectorAll('[class*="lucky"], [class*="luck"], [class*="ohuang"], [class*="oh"]');
        
        // 也搜索文本节点中包含"幸运"的元素
        const allDivs = document.querySelectorAll('div, span, p');
        for (const el of allDivs) {
            const text = (el.textContent || '').trim();
            if (text.includes('幸运值') || text.includes('幸运')) {
                luckyLabelElements.push(el);
            }
        }

        // 从找到的元素中提取数字
        for (const el of luckyLabelElements) {
            const text = el.textContent || '';
            const match = text.match(/(\d+)/);
            if (match) {
                const val = parseInt(match[1], 10);
                if (val >= 0 && val <= 200) {
                    candidates.push(val);
                }
            }
        }

        // 方案2: 查找纯数字显示（可能是大号字体显示幸运值）
        if (candidates.length === 0) {
            for (const el of allDivs) {
                const text = (el.textContent || '').trim();
                if (/^\d{1,3}$/.test(text)) {
                    const val = parseInt(text, 10);
                    if (val >= 0 && val <= 200) {
                        // 取最合理的值（排除时间、倒计时等）
                        const parentText = (el.parentElement?.textContent || '').trim();
                        if (parentText.includes('幸运') || parentText.includes('欧皇')) {
                            candidates.push(val);
                        }
                    }
                }
            }
        }

        return candidates.length > 0 ? Math.max(...candidates) : null;
    }

    /**
     * 检测欧皇时刻入口按钮
     * 支持多种可能的 CSS 选择器
     */
    function detectOhuangEntry() {
        // 候选选择器列表（按优先级排序）
        const selectors = [
            '.player-lucky-burst-icon',    // 原始选择器
            '[class*="lucky-burst"]',       // 模糊匹配
            '[class*="ohuang"]',            // 欧皇相关
            '[class*="burst"]',             // burst 相关
        ];

        for (const selector of selectors) {
            const entryBtn = document.querySelector(selector);
            if (!entryBtn) continue;

            // 验证：检查是否包含倒计时 span（格式 HH:MM:SS）
            const countdownSpan = entryBtn.querySelector('span');
            if (countdownSpan) {
                const text = (countdownSpan.textContent || '').trim();
                if (/\d{1,2}:\d{2}:\d{2}/.test(text)) {
                    console.log(`${TAG} detectOhuangEntry: 通过选择器 "${selector}" 找到入口`);
                    return entryBtn;
                }
            }

            // 备选：检查自身文本
            const selfText = (entryBtn.textContent || '').trim();
            if (/\d{1,2}:\d{2}:\d{2}/.test(selfText)) {
                console.log(`${TAG} detectOhuangEntry: 通过选择器 "${selector}" 找到入口（自身文本匹配）`);
                return entryBtn;
            }
        }

        return null;
    }

    /**
     * 检测视频倒计时
     * 查找格式如 "13s后领取" 或 "13" 秒的数字
     */
    function detectCountdown() {
        // 首先尝试精确匹配倒计时文字
        const patterns = [
            /(\d+)\s*s\s*后领取/,    // "13s后领取"
            /(\d+)\s*秒后/,           // "13秒后"
            /(\d+)\s*s/,              // "13s"
            /剩余\s*(\d+)\s*秒/,       // "剩余13秒"
        ];

        // 只搜索弹窗/模态框内的元素，而不是全部 *
        const modalElements = document.querySelectorAll('.modal, .popup, .dialog, [class*="modal"], [class*="popup"], [class*="dialog"], [class*="overlay"], [class*="mask"]');
        const elementsToCheck = modalElements.length > 0 ? modalElements : document.querySelectorAll('*');
        
        for (const el of elementsToCheck) {
            const text = (el.textContent || '').trim();
            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match) {
                    const seconds = parseInt(match[1], 10);
                    if (seconds >= 0 && seconds <= 60) {
                        return { element: el, seconds };
                    }
                }
            }
        }

        // 查找视频播放器内的倒计时元素
        const videoContainers = document.querySelectorAll('[class*="video"], [class*="player"], [class*="ad"], iframe');
        for (const container of videoContainers) {
            if (container.tagName === 'IFRAME') {
                // 跨域 iframe 无法访问，跳过
                continue;
            }
            const text = (container.textContent || '').trim();
            for (const pattern of patterns) {
                const match = text.match(pattern);
                if (match) {
                    return { element: container, seconds: parseInt(match[1], 10) };
                }
            }
        }

        return null;
    }

    /**
     * 等待视频倒计时完成
     * 返回 true 表示倒计时完成，false 表示超时
     */
    async function waitForCountdown() {
        log('⏳ 等待视频倒计时...');
        const startTime = Date.now();

        while (Date.now() - startTime < CONFIG.FALLBACK_MAX_WAIT_MS) {
            const cd = detectCountdown();
            if (cd) {
                const waitTime = Math.min(cd.seconds * 1000 + 1000, 30000);
                log(`   倒计时检测到 ${cd.seconds}s，等待 ${Math.ceil(waitTime / 1000)} 秒后检查...`);
                await sleep(waitTime);
            }

            // 检查是否出现"恭喜完成任务"
            const doneEl = findElementContainingText('恭喜完成任务');
            if (doneEl) {
                log('✅ 视频倒计时完成！');
                return true;
            }

            // 检查是否出现"直接领取"（备选结束标志）
            const claimEl = findElementContainingText('直接领取');
            if (claimEl) {
                log('✅ 视频完成（检测到直接领取）');
                return true;
            }

            await sleep(CONFIG.COUNTDOWN_POLL_MS);
        }

        warn('视频倒计时等待超时');
        return false;
    }

    /**
     * 关闭奖励弹窗
     * 尝试多种关闭方式
     */
    async function closeRewardPopup() {
        log('❌ 关闭奖励弹窗...');

        // 尝试找关闭按钮（X）
        const closeSelectors = [
            '[class*="close"]',
            '[class*="Close"]',
            '[aria-label*="关闭"]',
            '[aria-label*="close"]',
            'button:has(svg)',
        ];

        // 先找包含X图标的元素
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            const text = (el.textContent || '').trim();
            if (text === '×' || text === '✕' || text === 'X' || text === '关闭') {
                if (el.offsetParent !== null) {
                    safeClick(el);
                    await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
                    return true;
                }
            }
        }

        // 尝试 close 类名
        for (const selector of closeSelectors) {
            try {
                const el = document.querySelector(selector);
                if (el && el.offsetParent !== null) {
                    safeClick(el);
                    await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
                    return true;
                }
            } catch (e) { /* skip */ }
        }

        // 点击空白区域关闭弹窗（modal 背景）
        const modals = document.querySelectorAll('[class*="modal"], [class*="popup"], [class*="overlay"], [class*="mask"]');
        for (const modal of modals) {
            if (modal.offsetParent !== null) {
                // 点击 modal 边缘或背景
                const rect = modal.getBoundingClientRect();
                const clickX = rect.left + 5;
                const clickY = rect.top + 5;
                const evt = new MouseEvent('click', {
                    bubbles: true,
                    cancelable: true,
                    clientX: clickX,
                    clientY: clickY,
                });
                modal.dispatchEvent(evt);
                await sleep(CONFIG.POPUP_CLOSE_DELAY_MS);
                return true;
            }
        }

        warn('未找到关闭弹窗的方式');
        return false;
    }

    /**
     * 执行一轮看视频领奖流程
     * @returns {boolean} 是否成功完成
     */
    async function runOneCycle() {
        cycleCount++;
        log(`🔄 第 ${cycleCount} 轮开始`);

        // Step 1: 选择"免费抽 +10"（第一个选项）
        const freeOption = findElementContainingText('免费抽');
        if (freeOption) {
            await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
            safeClick(freeOption);
            log('🎯 选择「免费抽 +10」');
            await sleep(500);
        } else {
            warn('未找到「免费抽 +10」选项，尝试继续');
        }

        // Step 2: 点击"看视频免费参与"
        const watchBtn = await waitForText('看视频免费参与', 10000);
        if (!watchBtn) {
            error('未找到「看视频免费参与」按钮');
            return false;
        }

        await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
        safeClick(watchBtn);
        log(`👆 点击「看视频免费参与」[${cycleCount}]`);

        // Step 3: 等待视频倒计时
        const countdownDone = await waitForCountdown();
        if (!countdownDone) {
            warn('视频可能未正常完成，尝试继续');
        }

        // Step 4: 点击"恭喜完成任务"
        await sleep(1000);
        const doneBtn = findElementContainingText('恭喜完成任务');
        if (doneBtn) {
            await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
            safeClick(doneBtn);
            log('✅ 点击「恭喜完成任务」');
            await sleep(1500);
        } else {
            // 备选：点击"直接领取"
            const claimBtn = findElementContainingText('直接领取');
            if (claimBtn) {
                await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
                safeClick(claimBtn);
                log('✅ 点击「直接领取」');
                await sleep(1500);
            } else {
                warn('未找到确认按钮');
            }
        }

        // Step 5: 关闭奖励弹窗
        await closeRewardPopup();
        await sleep(CONFIG.CYCLE_COOLDOWN_MS);

        // Step 6: 读取幸运值
        await sleep(1000);
        const lucky = parseLuckyValue();
        if (lucky !== null) {
            const prev = currentLuckyValue;
            currentLuckyValue = lucky;
            log(`📊 当前幸运值: ${prev} → ${lucky}`);
        } else {
            // 估计增加 10
            currentLuckyValue += 10;
            log(`📊 估计幸运值: ${currentLuckyValue} (未能读取到精确值)`);
        }

        // Step 7: 检查是否达到上限
        if (currentLuckyValue >= CONFIG.MAX_LUCKY_VALUE) {
            log('🏁 幸运值已达到 200，任务完成！');
            isCompleted = true;
            return true;
        }

        log(`✅ 第 ${cycleCount} 轮完成`);
        return true;
    }

    /**
     * 点击欧皇入口进入活动
     * 使用多种 CSS 选择器定位
     */
    async function enterActivity() {
        const entry = detectOhuangEntry();
        if (!entry) {
            console.warn(`${TAG} enterActivity: 未检测到欧皇入口`);
            return false;
        }

        // 确保入口可见且可点击
        const rect = entry.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) {
            console.warn(`${TAG} enterActivity: 入口元素尺寸为0`);
            return false;
        }

        console.log(`${TAG} enterActivity: 检测到欧皇时刻活动入口！`);
        await humanDelay(CONFIG.CLICK_DELAY_MIN_MS, CONFIG.CLICK_DELAY_MAX_MS);
        safeClick(entry);
        console.log(`${TAG} enterActivity: 点击欧皇入口，进入活动...`);
        await sleep(3000); // 等待活动界面加载

        return true;
    }

    /**
     * 主循环：持续执行看视频领奖流程
     */
    async function mainLoop() {
        if (isRunning) return;
        isRunning = true;

        log('🚀 虎牙欧皇时刻自动脚本启动');

        // 检查是否已经进入活动界面
        const onActivityPage = findElementContainingText('看视频免费参与');

        if (!onActivityPage) {
            // 尝试点击欧皇入口
            const entered = await enterActivity();
            if (!entered) {
                log('⏸️ 未检测到欧皇活动，持续监听中...');
                isRunning = false;
                return;
            }
        }

        // 开始循环
        while (!isCompleted && currentLuckyValue < CONFIG.MAX_LUCKY_VALUE) {
            try {
                const success = await runOneCycle();
                if (!success) {
                    // 一轮失败后等待再重试
                    await sleep(CONFIG.RETRY_INTERVAL_MS);
                }

                // 每轮之间检查活动页面是否还在
                const stillOnActivity = findElementContainingText('看视频免费参与') ||
                                       findElementContainingText('恭喜完成任务');
                if (!stillOnActivity) {
                    warn('活动页面似乎已关闭，尝试重新检测入口...');
                    const reEntered = await enterActivity();
                    if (!reEntered) {
                        log('⏸️ 活动可能已结束');
                        break;
                    }
                }
            } catch (e) {
                error(`循环异常: ${e.message}\n${e.stack}`);
                await sleep(CONFIG.RETRY_INTERVAL_MS);
            }
        }

        if (isCompleted) {
            log('🎉 恭喜！今日欧皇时刻任务已全部完成！');
        }

        isRunning = false;
    }

    // ======================== 入口触发 ========================

    /**
     * 使用 MutationObserver + 定时轮询监听欧皇入口
     */
    function startWatching() {
        const banner = [
            '╔══════════════════════════════════╗',
            '║   🎰 虎牙欧皇时刻自动脚本 v1.0  ║',
            '║   监听中...                     ║',
            `║   页面: ${location.href.substring(0, 50)}`,
            '╚══════════════════════════════════╝',
        ];
        banner.forEach(line => console.log(line));

        // 立即检查（不延迟）
        function checkNow() {
            if (isRunning || isCompleted) return;
            
            // 使用改进的入口检测
            const entry = detectOhuangEntry();
            if (entry) {
                const span = entry.querySelector('span');
                const timer = span ? span.textContent.trim() : '?';
                log(`🔔 检测到欧皇入口 (倒计时: ${timer})`);
                mainLoop();
                return true;
            }
            
            // 调试：输出当前页面中可能的 player 相关元素
            const playerElements = document.querySelectorAll('[class*="player"]');
            if (playerElements.length > 0 && Math.random() < 0.1) { // 10% 概率输出，避免日志过多
                log(`🔍 页面中有 ${playerElements.length} 个 player 相关元素`);
                for (let i = 0; i < Math.min(3, playerElements.length); i++) {
                    log(`   [${i}] class="${playerElements[i].className}"`);
                }
            }
            
            return false;
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
                const status = entry ? `检测到入口 (倒计时: ${(entry.querySelector('span')||{}).textContent||'?'})` : '等待活动开始';
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
