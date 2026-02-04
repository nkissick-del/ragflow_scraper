/**
 * Pure JavaScript utility functions for the PDF Scraper web interface.
 * NO frameworks (Alpine.js, Vue, React, etc.) - just vanilla JS.
 */

/**
 * Format a date string to a more readable format.
 * @param {string} dateStr - ISO date string
 * @returns {string} Formatted date string
 */
function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateStr;
    }
}

/**
 * Format a file size in bytes to a human-readable string.
 * @param {number} bytes - Size in bytes
 * @returns {string} Human-readable size string
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return parseFloat((bytes / Math.pow(1024, i)).toFixed(1)) + ' ' + units[i];
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param {number} seconds - Duration in seconds
 * @returns {string} Human-readable duration
 */
function formatDuration(seconds) {
    if (seconds < 60) {
        return Math.round(seconds) + 's';
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return mins + 'm ' + secs + 's';
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return hours + 'h ' + mins + 'm';
    }
}

/**
 * Show a notification message.
 * @param {string} message - Message to display
 * @param {string} type - Type: 'success', 'error', 'warning', 'info'
 * @param {number} duration - Duration in milliseconds (0 for persistent)
 */
function showNotification(message, type = 'info', duration = 3000) {
    // Create notification container if it doesn't exist
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 1000;';
        document.body.appendChild(container);
    }

    // Create notification element
    const notification = document.createElement('div');
    notification.className = 'notification notification-' + type;
    notification.style.cssText = `
        background: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        margin-bottom: 8px;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;

    // Add type-specific styling
    const colors = {
        success: '#16a34a',
        error: '#dc2626',
        warning: '#ca8a04',
        info: '#2563eb'
    };
    notification.style.borderLeft = '4px solid ' + (colors[type] || colors.info);

    // Add accessibility attributes
    if (type === 'error' || type === 'warning') {
        notification.setAttribute('role', 'alert');
    } else {
        notification.setAttribute('role', 'status');
    }

    container.appendChild(notification);

    // Auto-remove after duration
    if (duration > 0) {
        setTimeout(function() {
            notification.style.animation = 'slideOut 0.3s ease';
            setTimeout(function() {
                notification.remove();
            }, 300);
        }, duration);
    }

    return notification;
}

/**
 * Copy text to clipboard.
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} Success status
 */
async function copyToClipboard(text) {
    try {
        // Try modern API first (if available and secure context)
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
        } else {
            // Fallback for non-secure contexts (e.g., HTTP local network)
            const textArea = document.createElement("textarea");
            textArea.value = text;

            // Avoid scrolling to bottom
            textArea.style.top = "0";
            textArea.style.left = "0";
            textArea.style.position = "fixed";

            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();

            try {
                const successful = document.execCommand('copy');
                if (!successful) throw new Error('execCommand failed');
            } catch (err) {
                document.body.removeChild(textArea);
                throw err;
            }

            document.body.removeChild(textArea);
        }

        showNotification('Copied to clipboard', 'success', 2000);
        return true;
    } catch (e) {
        console.error('Failed to copy:', e);
        showNotification('Failed to copy to clipboard', 'error', 2000);
        return false;
    }
}

/**
 * Debounce function calls.
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds
 * @returns {Function} Debounced function
 */
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(function() {
            func.apply(this, args);
        }.bind(this), wait);
    };
}

/**
 * Parse query string parameters.
 * @param {string} queryString - Query string (optional, defaults to current URL)
 * @returns {Object} Parameter key-value pairs
 */
function parseQueryString(queryString) {
    if (!queryString) {
        queryString = window.location.search;
    }
    const params = {};
    const searchParams = new URLSearchParams(queryString);
    for (const [key, value] of searchParams) {
        params[key] = value;
    }
    return params;
}

/**
 * Build a query string from an object.
 * @param {Object} params - Parameter key-value pairs
 * @returns {string} Query string
 */
function buildQueryString(params) {
    return new URLSearchParams(params).toString();
}

// Add CSS for notifications
(function() {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
})();
