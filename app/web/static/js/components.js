/**
 * HTMX component enhancements for the PDF Scraper web interface.
 * Pure JavaScript - NO frameworks.
 */

/**
 * Initialize status polling for elements with auto-refresh.
 */
function initializeStatusPolling() {
    // HTMX handles polling via hx-trigger="every Xs"
    // This function can be used for additional initialization if needed
    console.log('Status polling initialized via HTMX');
}

/**
 * Initialize CSRF protection for HTMX requests.
 * Reads token from meta tag and adds to headers.
 */
function initializeCSRF() {
    document.body.addEventListener('htmx:configRequest', function(evt) {
        const tokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (tokenMeta) {
            evt.detail.headers['X-CSRFToken'] = tokenMeta.content;
        }
    });
}

/**
 * Handle scraper action button clicks.
 * Adds loading state and disables button during request.
 */
function handleScraperActions() {
    document.addEventListener('htmx:beforeRequest', function(event) {
        const target = event.target;
        if (target.matches('[hx-post*="/run"]')) {
            target.disabled = true;
            target.dataset.originalText = target.textContent;
            target.textContent = 'Starting...';
        }
    });

    document.addEventListener('htmx:afterRequest', function(event) {
        const target = event.target;
        if (target.matches('[hx-post*="/run"]') && target.dataset.originalText) {
            // Button will be replaced by HTMX, but just in case
            target.disabled = false;
        }
        // Handle preview button - remove htmx-request class to stop spinner
        if (target.matches('[hx-post*="/preview"]')) {
            target.classList.remove('htmx-request');
            target.disabled = false;
        }
    });

    document.addEventListener('htmx:requestError', function(event) {
        const target = event.target;
        if (target.matches('[hx-post*="/run"]')) {
            target.disabled = false;
            target.textContent = target.dataset.originalText || 'Run Now';
            showNotification('Request failed. Please try again.', 'error');
        }
        // Handle preview button errors
        if (target.matches('[hx-post*="/preview"]')) {
            target.classList.remove('htmx-request');
            target.disabled = false;
            showNotification('Preview failed. Please try again.', 'error');
        }
    });

    // Handle timeout/abort for preview buttons
    document.addEventListener('htmx:timeout', function(event) {
        const target = event.target;
        if (target.matches('[hx-post*="/preview"]')) {
            target.classList.remove('htmx-request');
            target.disabled = false;
            showNotification('Preview timed out. Try fewer pages.', 'warning');
        }
    });

    document.addEventListener('htmx:abort', function(event) {
        const target = event.target;
        if (target.matches('[hx-post*="/preview"]')) {
            target.classList.remove('htmx-request');
            target.disabled = false;
        }
    });
}

/**
 * Update progress bars dynamically.
 * @param {string} elementId - Progress bar element ID
 * @param {number} current - Current value
 * @param {number} total - Total value
 */
function updateProgressBar(elementId, current, total) {
    const element = document.getElementById(elementId);
    if (!element) return;

    const percentage = total > 0 ? Math.round((current / total) * 100) : 0;
    const bar = element.querySelector('.progress-bar-fill');
    const text = element.querySelector('.progress-text');

    if (bar) {
        bar.style.width = percentage + '%';
    }
    if (text) {
        text.textContent = current + ' / ' + total + ' (' + percentage + '%)';
    }
}

/**
 * Format log entries with syntax highlighting.
 * @param {HTMLElement} container - Log container element
 */
function formatLogEntries(container) {
    if (!container) return;

    const entries = container.querySelectorAll('.log-entry');
    entries.forEach(function(entry) {
        const text = entry.textContent;

        // Highlight timestamps
        const timestampMatch = text.match(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/);
        if (timestampMatch) {
            entry.innerHTML = entry.innerHTML.replace(
                timestampMatch[0],
                '<span class="log-timestamp">' + timestampMatch[0] + '</span>'
            );
        }

        // Add appropriate class based on level
        if (text.includes('| ERROR')) {
            entry.classList.add('log-error');
        } else if (text.includes('| WARNING')) {
            entry.classList.add('log-warning');
        } else if (text.includes('| DEBUG')) {
            entry.classList.add('log-debug');
        }
    });
}

/**
 * Confirm dangerous actions before proceeding.
 * @param {string} action - Description of the action
 * @returns {boolean} True if confirmed
 */
function confirmDangerousAction(action) {
    return confirm('Are you sure you want to ' + action + '? This action cannot be undone.');
}

/**
 * Handle form submissions with loading state.
 */
function handleFormSubmissions() {
    document.addEventListener('htmx:beforeRequest', function(event) {
        const form = event.target.closest('form');
        if (form) {
            const submitBtn = form.querySelector('[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.dataset.originalText = submitBtn.textContent;
                submitBtn.textContent = 'Saving...';
            }
        }
    });

    document.addEventListener('htmx:afterRequest', function(event) {
        const form = event.target.closest('form');
        if (form) {
            const submitBtn = form.querySelector('[type="submit"]');
            if (submitBtn && submitBtn.dataset.originalText) {
                submitBtn.disabled = false;
                submitBtn.textContent = submitBtn.dataset.originalText;
            }
        }
    });
}

/**
 * Auto-scroll log viewer to bottom when new content is added.
 */
function initializeLogAutoScroll() {
    document.addEventListener('htmx:afterSwap', function(event) {
        const autoScroll = document.getElementById('auto-scroll');
        if (autoScroll && autoScroll.checked) {
            const container = document.getElementById('log-container');
            if (container && event.target.closest('#log-container')) {
                container.scrollTop = container.scrollHeight;
            }
        }
    });
}

/**
 * Handle HTMX errors globally.
 */
function handleHTMXErrors() {
    document.addEventListener('htmx:responseError', function(event) {
        console.error('HTMX Error:', event.detail);
        showNotification('An error occurred. Please try again.', 'error');
    });

    document.addEventListener('htmx:sendError', function(event) {
        console.error('HTMX Send Error:', event.detail);
        showNotification('Network error. Please check your connection.', 'error');
    });
}

/**
 * Initialize keyboard shortcuts.
 */
function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function(event) {
        // Ctrl/Cmd + R to refresh (prevent default and trigger HTMX refresh)
        if ((event.ctrlKey || event.metaKey) && event.key === 'r') {
            // Let browser handle the refresh
            return;
        }

        // Escape to close modals (if any)
        if (event.key === 'Escape') {
            const modal = document.querySelector('.modal.open');
            if (modal) {
                modal.classList.remove('open');
                event.preventDefault();
            }
        }
    });
}

// Initialize all components when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeCSRF();
    initializeStatusPolling();
    handleScraperActions();
    handleFormSubmissions();
    initializeLogAutoScroll();
    handleHTMXErrors();
    initializeKeyboardShortcuts();

    console.log('PDF Scraper components initialized');
});

// Re-initialize after HTMX swaps
document.addEventListener('htmx:afterSettle', function(event) {
    // Format any new log entries
    const logViewer = event.target.querySelector('.log-viewer');
    if (logViewer) {
        formatLogEntries(logViewer);
    }
});
