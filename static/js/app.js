/**
 * Arcane Panel — Global Alpine.js Helpers
 */
window.showToast = function(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideIn 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
};

window.api = async function(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            ...options,
            headers: { 'Content-Type': 'application/json', ...options.headers },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || data.error || 'Request failed');
        return data;
    } catch (error) {
        showToast(error.message, 'error');
        throw error;
    }
};

window.formatBytes = function(bytes, decimals = 2) {
    if (bytes === 0) return '0 B';
    const k = 1024, dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

window.formatDate = function(timestamp) {
    if (!timestamp) return '—';
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString('fa-IR') + ' ' + date.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' });
};

window.copyToClipboard = function(text) {
    const fullUrl = text.startsWith('/') ? window.location.origin + text : text;
    navigator.clipboard.writeText(fullUrl).then(() => showToast('کپی شد!', 'success')).catch(() => showToast('خطا در کپی', 'error'));
};
