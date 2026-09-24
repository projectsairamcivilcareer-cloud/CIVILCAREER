(function () {
    "use strict";

    function setupCivilCareerMenu() {
        if (document.getElementById("cc-global-menu")) {
            return;
        }

        document.body.classList.add("cc-menu-page");

        const menu = document.createElement("div");
        menu.id = "cc-global-menu";
        menu.innerHTML = `
            <button
                class="cc-menu-button"
                id="cc-menu-button"
                type="button"
                aria-label="Open navigation menu"
                aria-controls="cc-menu-drawer"
                aria-expanded="false"
            >☰</button>

            <div class="cc-menu-backdrop" id="cc-menu-backdrop"></div>

            <aside
                class="cc-menu-drawer"
                id="cc-menu-drawer"
                aria-label="Civil Career navigation"
            >
                <div class="cc-menu-head">
                    <div class="cc-menu-brand">
                        <span class="cc-menu-brand-icon">🏗️</span>
                        <span>CIVIL CAREER</span>
                    </div>
                    <button
                        class="cc-menu-close"
                        id="cc-menu-close"
                        type="button"
                        aria-label="Close navigation menu"
                    >×</button>
                </div>

                <nav class="cc-menu-nav">
                    <a class="cc-menu-link" href="/dashboard" data-cc-path="/dashboard">
                        <span class="cc-menu-icon">📊</span><span>Dashboard</span>
                    </a>
                    <a class="cc-menu-link" href="/exams" data-cc-path="/exams">
                        <span class="cc-menu-icon">📚</span><span>Exams</span>
                    </a>
                    <a class="cc-menu-link" href="/government-jobs" data-cc-path="/government-jobs">
                        <span class="cc-menu-icon">🏛️</span><span>Government Jobs</span>
                    </a>
                    <a class="cc-menu-link" href="/syllabus" data-cc-path="/syllabus">
                        <span class="cc-menu-icon">📖</span><span>Syllabus</span>
                    </a>
                    <a class="cc-menu-link" href="/materials" data-cc-path="/materials">
                        <span class="cc-menu-icon">📚</span><span>Materials</span>
                    </a>
                    <a class="cc-menu-link" href="/notifications" data-cc-path="/notifications">
                        <span class="cc-menu-icon">🔔</span><span>Notifications</span>
                    </a>
                    <a class="cc-menu-link" href="/practice" data-cc-path="/practice">
                        <span class="cc-menu-icon">🎯</span><span>Practice</span>
                    </a>
                    <a class="cc-menu-link" href="/profile" data-cc-path="/profile">
                        <span class="cc-menu-icon">👤</span><span>Profile</span>
                    </a>
                </nav>

                <div class="cc-menu-bottom">
                    <a class="cc-menu-link" href="/">
                        <span class="cc-menu-icon">🏠</span><span>Home</span>
                    </a>
                    <a class="cc-menu-link" href="/logout">
                        <span class="cc-menu-icon">🚪</span><span>Logout</span>
                    </a>
                </div>
            </aside>
        `;

        document.body.appendChild(menu);

        const button = document.getElementById("cc-menu-button");
        const close = document.getElementById("cc-menu-close");
        const backdrop = document.getElementById("cc-menu-backdrop");

        function setOpen(open) {
            document.body.classList.toggle("cc-menu-open", open);
            button.setAttribute("aria-expanded", String(open));
        }

        // Always start each page load with the navigation collapsed.
        setOpen(false);

        // Browsers may restore a page from the back-forward cache with old UI state.
        window.addEventListener("pageshow", function () {
            setOpen(false);
        });

        button.addEventListener("click", function () {
            setOpen(!document.body.classList.contains("cc-menu-open"));
        });

        close.addEventListener("click", function () {
            setOpen(false);
        });

        backdrop.addEventListener("click", function () {
            setOpen(false);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") {
                setOpen(false);
            }
        });

        const path = window.location.pathname.replace(/\/+$/, "") || "/";

        document.querySelectorAll(".cc-menu-link[data-cc-path]").forEach(function (link) {
            const target = link.getAttribute("data-cc-path");
            if (
                path === target ||
                (target !== "/dashboard" && path.startsWith(target + "/"))
            ) {
                link.classList.add("active");
            }

            link.addEventListener("click", function () {
                setOpen(false);
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", setupCivilCareerMenu);
    } else {
        setupCivilCareerMenu();
    }
})();
