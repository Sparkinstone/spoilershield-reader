/* SpoilerShield — local interactions. No htmx, no CDN, no build step. */
(() => {
    "use strict";

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    /* ---------------------------------------------------------- comments */
    const dialog = $("#comment-dialog");
    const dialogContent = $("#comment-dialog-content");
    const reader = $(".reader");
    const bookId = reader ? reader.dataset.bookId : null;

    let activeTrigger = null;
    let activeIndex = 0;
    let requestId = 0;

    const COMMENT_LOAD_ERROR =
        '<div class="notice notice--warn" role="alert">' +
        "评论加载失败，请检查网络后重试。" +
        '<button class="btn btn--quiet btn--sm" type="button" data-retry>重试</button>' +
        "</div>";

    function resetSpoilerToggle() {
        const toggle = $("[data-toggle-spoilers]");
        if (!toggle) return;
        toggle.setAttribute("aria-pressed", "false");
        toggle.textContent = "展开剧透";
        toggle.hidden = true;
    }

    function updateSpoilerToggle() {
        const toggle = $("[data-toggle-spoilers]");
        if (!toggle || !dialogContent) return;
        const hasSpoilers = dialogContent.querySelectorAll(".spoiler-blur").length > 0;
        toggle.hidden = !hasSpoilers;
        if (!hasSpoilers) {
            toggle.setAttribute("aria-pressed", "false");
            toggle.textContent = "展开剧透";
        }
    }

    function hideReadingHint() {
        const hint = $("[data-reading-hint]");
        if (hint) hint.classList.add("is-hidden");
    }

    async function loadComments(paraIndex, trigger) {
        if (!dialog || !dialogContent || !bookId) return;

        activeTrigger = trigger || activeTrigger;
        activeIndex = Number(paraIndex);
        const currentRequest = ++requestId;

        dialogContent.innerHTML = '<p class="loading">正在加载评论…</p>';
        resetSpoilerToggle();
        hideReadingHint();
        if (!dialog.open) {
            dialog.showModal();
        }

        try {
            const response = await fetch(
                `/book/${encodeURIComponent(bookId)}/comments/${encodeURIComponent(paraIndex)}`,
                { headers: { "X-Requested-With": "fetch" } }
            );
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const html = await response.text();
            if (currentRequest !== requestId) return;
            dialogContent.innerHTML = html;
            updateSpoilerToggle();
            dialogContent.focus({ preventScroll: true });
        } catch (error) {
            if (currentRequest !== requestId) return;
            dialogContent.innerHTML = COMMENT_LOAD_ERROR;
        }
    }

    function activateParagraph(element) {
        $$(".paragraph.is-active").forEach((paragraph) => paragraph.classList.remove("is-active"));
        element.classList.add("is-active");
        setProgress(Number(element.dataset.paraIndex));
    }

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest("[data-comment-trigger]");
        if (!trigger) return;
        // Selecting a sentence to quote should not pop the panel open.
        if (window.getSelection && String(window.getSelection()).trim()) return;
        event.preventDefault();
        activateParagraph(trigger);
        loadComments(trigger.dataset.paraIndex, trigger);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const trigger = event.target.closest ? event.target.closest("[data-comment-trigger]") : null;
        if (!trigger) return;
        event.preventDefault();
        activateParagraph(trigger);
        loadComments(trigger.dataset.paraIndex, trigger);
    });

    if (dialog) {
        dialog.addEventListener("click", (event) => {
            if (event.target === dialog) dialog.close();
        });
        dialog.addEventListener("close", () => {
            requestId += 1;
            if (activeTrigger) activeTrigger.focus({ preventScroll: true });
        });
    }

    document.addEventListener("click", (event) => {
        if (event.target.closest("[data-close-dialog]") && dialog) {
            dialog.close();
        }
    });

    if (dialogContent) {
        dialogContent.addEventListener("click", (event) => {
            const retry = event.target.closest("[data-retry]");
            if (retry) {
                loadComments(activeIndex, activeTrigger);
                return;
            }

            const toggle = event.target.closest(".spoiler-toggle");
            if (!toggle) return;
            const wrapper = toggle.closest(".spoiler") || toggle.parentElement;
            const text = wrapper ? $(".spoiler-blur", wrapper) : null;
            if (!text) return;
            const revealed = text.classList.toggle("is-revealed");
            toggle.setAttribute("aria-expanded", String(revealed));
            toggle.textContent = revealed ? "收起" : "展开";
        });

        dialogContent.addEventListener("submit", async (event) => {
            const form = event.target.closest("form[data-comment-form]");
            if (!form) return;
            event.preventDefault();

            const button = $('button[type="submit"]', form);
            const errorBox = $("[data-comment-error]", form);
            const originalLabel = button ? button.textContent : "";
            if (errorBox) errorBox.hidden = true;
            if (button) {
                button.disabled = true;
                button.textContent = "发送中…";
            }

            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    body: new FormData(form),
                    headers: { "X-Requested-With": "fetch" },
                });

                if (!response.ok) {
                    let message = "发送失败，请重试。";
                    try {
                        const payload = await response.json();
                        if (payload && payload.detail) message = payload.detail;
                    } catch (ignored) {
                        /* non-JSON error body */
                    }
                    throw new Error(message);
                }

                dialogContent.innerHTML = await response.text();
                updateSpoilerToggle();
                incrementCommentCount();
                dialogContent.focus({ preventScroll: true });
            } catch (error) {
                if (errorBox) {
                    errorBox.textContent = error.message || "发送失败，请重试。";
                    errorBox.hidden = false;
                }
                if (button) {
                    button.disabled = false;
                    button.textContent = originalLabel;
                }
            }
        });
    }

    function incrementCommentCount() {
        if (!activeTrigger) return;
        const badge = $(".comment-count", activeTrigger);
        if (!badge) return;
        const value = badge.querySelector("[data-comment-count]");
        const next = Number(value ? value.textContent : 0) + 1;
        if (value) value.textContent = String(next);
        badge.title = `${next} 条评论`;
    }

    const spoilerAll = $("[data-toggle-spoilers]");
    if (spoilerAll && dialogContent) {
        spoilerAll.addEventListener("click", () => {
            const revealed = spoilerAll.getAttribute("aria-pressed") === "true";
            $$(".spoiler-blur", dialogContent).forEach((element) => {
                element.classList.toggle("is-revealed", !revealed);
            });
            $$(".spoiler-toggle", dialogContent).forEach((button) => {
                button.setAttribute("aria-expanded", String(!revealed));
                button.textContent = revealed ? "展开" : "收起";
            });
            spoilerAll.setAttribute("aria-pressed", String(!revealed));
            spoilerAll.textContent = revealed ? "展开剧透" : "收起剧透";
        });
    }

    /* ------------------------------------------------------------- drawer */
    const drawer = $("#toc-drawer");
    const overlay = $("[data-toc-overlay]");
    const tocOpen = $("[data-toc-open]");
    let drawerReturnFocus = null;

    function openToc() {
        if (!drawer) return;
        drawerReturnFocus = document.activeElement;
        drawer.classList.add("is-open");
        drawer.setAttribute("aria-hidden", "false");
        if (tocOpen) tocOpen.setAttribute("aria-expanded", "true");
        if (overlay) {
            overlay.hidden = false;
            requestAnimationFrame(() => overlay.classList.add("is-open"));
        }
        const closeButton = $("[data-toc-close]", drawer);
        if (closeButton) closeButton.focus({ preventScroll: true });
    }

    function closeToc(restoreFocus = true) {
        if (!drawer) return;
        drawer.classList.remove("is-open");
        drawer.setAttribute("aria-hidden", "true");
        if (tocOpen) tocOpen.setAttribute("aria-expanded", "false");
        if (overlay) {
            overlay.classList.remove("is-open");
            window.setTimeout(() => {
                if (!drawer.classList.contains("is-open")) overlay.hidden = true;
            }, 240);
        }
        if (restoreFocus && drawerReturnFocus && drawerReturnFocus.focus) {
            drawerReturnFocus.focus({ preventScroll: true });
        }
        drawerReturnFocus = null;
    }

    if (tocOpen) tocOpen.addEventListener("click", openToc);
    $$("[data-toc-close]").forEach((button) => {
        button.addEventListener("click", () => closeToc());
    });
    if (overlay) overlay.addEventListener("click", () => closeToc());

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && drawer && drawer.classList.contains("is-open")) {
            closeToc();
        }
    });

    $$(".toc-link").forEach((link) => {
        link.addEventListener("click", () => closeToc(false));
    });

    /* ----------------------------------------------------------- progress */
    const slider = $("#para-slider");
    const progressLabel = $("#para-label");
    const paragraphs = $$(".paragraph");
    const totalParagraphs = paragraphs.length;

    let tocData = [];
    const tocScript = $("#toc-data");
    if (tocScript) {
        try {
            tocData = JSON.parse(tocScript.textContent || "[]");
        } catch (error) {
            tocData = [];
        }
    }

    function setProgress(index) {
        activeIndex = index;
        if (slider) slider.value = String(index);
        if (progressLabel && totalParagraphs) {
            progressLabel.textContent = `第 ${index + 1} / ${totalParagraphs} 段`;
        }
    }

    function scrollToParagraph(index, smooth = true) {
        const element = document.getElementById(`para-${index}`);
        if (!element) return;
        element.scrollIntoView({
            behavior: smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "auto",
            block: "center",
        });
        activateParagraph(element);
    }

    if (slider) {
        slider.addEventListener("input", () => scrollToParagraph(Number(slider.value)));
        setProgress(Number(slider.value) || 0);
    }

    if ("IntersectionObserver" in window && paragraphs.length) {
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        setProgress(Number(entry.target.dataset.paraIndex));
                    }
                });
            },
            { rootMargin: "-48% 0px -48% 0px", threshold: 0 }
        );
        paragraphs.forEach((paragraph) => observer.observe(paragraph));
    }

    function chapterIndexFor(index) {
        let chapter = 0;
        tocData.forEach((item, position) => {
            if (index >= Number(item.para_index)) chapter = position;
        });
        return chapter;
    }

    const previousChapter = $("[data-chapter-prev]");
    const nextChapter = $("[data-chapter-next]");

    if (previousChapter) {
        previousChapter.addEventListener("click", () => {
            const chapter = chapterIndexFor(activeIndex);
            if (chapter > 0) scrollToParagraph(Number(tocData[chapter - 1].para_index));
        });
    }

    if (nextChapter) {
        nextChapter.addEventListener("click", () => {
            const chapter = chapterIndexFor(activeIndex);
            if (chapter < tocData.length - 1) {
                scrollToParagraph(Number(tocData[chapter + 1].para_index));
            }
        });
    }

    /* ------------------------------------------------------------ upload */
    const uploadForm = $("[data-upload-form]");
    const uploadDialog = $("#upload-dialog");
    const uploadErrorDialog = $("#upload-error-dialog");

    if (uploadForm && uploadDialog && uploadErrorDialog) {
        const submitButton = $("[data-upload-submit]", uploadForm);
        const progress = $("[data-upload-progress]", uploadDialog);
        const bar = $("[data-upload-bar]", uploadDialog);
        const percent = $("[data-upload-percent]", uploadDialog);
        const status = $("[data-upload-status]", uploadDialog);
        const errorText = $("[data-upload-error]", uploadErrorDialog);
        const closeButton = $("[data-upload-close]", uploadErrorDialog);
        const retryButton = $("[data-upload-retry]", uploadErrorDialog);
        let uploading = false;

        function resetUploadUi() {
            uploading = true;
            progress.dataset.indeterminate = "false";
            progress.setAttribute("aria-valuenow", "0");
            bar.style.width = "0%";
            percent.textContent = "0%";
            status.textContent = "正在上传文件…";
            if (submitButton) submitButton.disabled = true;
        }

        function setIndeterminate() {
            progress.dataset.indeterminate = "true";
            progress.removeAttribute("aria-valuenow");
            percent.textContent = "处理中";
            status.textContent = "文件已上传，正在解析段落并生成向量…";
        }

        function finishUpload() {
            uploading = false;
            if (submitButton) submitButton.disabled = false;
        }

        function failureMessage(request) {
            let message = "";
            try {
                const payload = JSON.parse(request.responseText);
                if (payload && payload.detail) message = String(payload.detail);
            } catch (ignored) {
                /* Nginx/proxy HTML error page */
            }
            if (message) return message;
            if (request.status === 0) return "网络连接中断，请检查网络后重试。";
            if (request.status === 413) return "文件超过大小限制，请换一个更小的文件。";
            if (request.status === 502 || request.status === 504) {
                return "服务器处理超时或暂时不可用，请稍后重试。";
            }
            return `上传失败（HTTP ${request.status}），请稍后重试。`;
        }

        function showFailure(message) {
            finishUpload();
            if (uploadDialog.open) uploadDialog.close();
            errorText.textContent = message || "上传失败，请稍后重试。";
            if (!uploadErrorDialog.open) uploadErrorDialog.showModal();
            const title = $("#upload-error-title", uploadErrorDialog);
            if (title) title.focus({ preventScroll: true });
        }

        uploadForm.addEventListener("submit", (event) => {
            if (!window.FormData || !window.XMLHttpRequest) return; // native fallback
            event.preventDefault();

            const fileInput = $('input[type="file"]', uploadForm);
            if (!fileInput || !fileInput.files || !fileInput.files.length) {
                if (fileInput) fileInput.reportValidity();
                return;
            }
            if (uploading) return;

            resetUploadUi();
            uploadDialog.showModal();

            const request = new XMLHttpRequest();
            request.open("POST", uploadForm.action, true);
            request.timeout = 10 * 60 * 1000;

            request.upload.addEventListener("progress", (progressEvent) => {
                if (!progressEvent.lengthComputable) return;
                const value = Math.min(
                    100,
                    Math.round((progressEvent.loaded / progressEvent.total) * 100)
                );
                progress.dataset.indeterminate = "false";
                progress.setAttribute("aria-valuenow", String(value));
                bar.style.width = `${value}%`;
                percent.textContent = `${value}%`;
                status.textContent =
                    value >= 100 ? "文件已上传，正在解析…" : "正在上传文件…";
            });

            request.upload.addEventListener("load", () => setIndeterminate());

            request.addEventListener("load", () => {
                if (request.status >= 200 && request.status < 400) {
                    finishUpload();
                    window.location.assign(
                        request.responseURL || window.location.href
                    );
                    return;
                }
                showFailure(failureMessage(request));
            });

            request.addEventListener("error", () => {
                showFailure("网络连接中断，请检查网络后重试。");
            });
            request.addEventListener("timeout", () => {
                showFailure("服务器处理时间过长，请稍后重试。");
            });
            request.addEventListener("abort", () => finishUpload());

            request.send(new FormData(uploadForm));
        });

        uploadDialog.addEventListener("cancel", (event) => {
            if (uploading) event.preventDefault();
        });

        closeButton.addEventListener("click", () => {
            uploadErrorDialog.close();
            const fileInput = $('input[type="file"]', uploadForm);
            if (fileInput) fileInput.focus();
        });

        retryButton.addEventListener("click", () => {
            uploadErrorDialog.close();
            uploadForm.requestSubmit();
        });

        window.addEventListener("beforeunload", (event) => {
            if (!uploading) return;
            event.preventDefault();
            event.returnValue = "";
        });
    }
})();
