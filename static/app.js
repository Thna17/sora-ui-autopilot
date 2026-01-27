const API_BASE = window.location.origin;

document.addEventListener('DOMContentLoaded', () => {
    fetchProfiles();

    document.getElementById('create-btn').addEventListener('click', createProfile);

    // Allow Enter key in input
    document.getElementById('new-profile-name').addEventListener('keyup', (e) => {
        if (e.key === 'Enter') createProfile();
    });
});

async function fetchProfiles() {
    try {
        const res = await fetch(`${API_BASE}/list_profiles`);
        const data = await res.json();
        renderProfiles(data.profiles || []);
    } catch (err) {
        showToast('Failed to load profiles', 'error');
        console.error(err);
    }
}

function renderProfiles(profiles) {
    const container = document.getElementById('profile-list');
    container.innerHTML = '';

    if (profiles.length === 0) {
        container.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary); padding: 2rem;">No profiles found. Create one to get started.</div>';
        return;
    }

    profiles.forEach(name => {
        const card = document.createElement('div');
        card.className = 'glass-card profile-card';

        // Generate a pseudo-random emoji/icon based on name char code sum
        const icon = getProfileIcon(name);

        card.innerHTML = `
            <div>
                <div class="profile-icon">${icon}</div>
                <div class="profile-name">${name}</div>
                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">Ready to launch</div>
            </div>
            <div class="profile-actions">
                <button class="btn btn-primary" onclick="launchProfile('${name}')">
                    🚀 Launch
                </button>
                <button class="btn btn-danger" onclick="deleteProfile('${name}')" style="margin-left: auto;">
                    🗑️
                </button>
            </div>
        `;
        container.appendChild(card);
    });
}

function getProfileIcon(name) {
    const icons = ['👤', '🤖', '🦊', '🐯', '🐼', '🦄', '🐲', '👻', '👽', '👾'];
    let sum = 0;
    for (let i = 0; i < name.length; i++) sum += name.charCodeAt(i);
    return icons[sum % icons.length];
}

async function createProfile() {
    const input = document.getElementById('new-profile-name');
    const name = input.value.trim();
    if (!name) return;

    try {
        const res = await fetch(`${API_BASE}/create_profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();

        if (data.ok) {
            showToast(`Profile "${data.name}" created!`, 'success');
            input.value = '';
            fetchProfiles();
        } else {
            showToast(data.error || 'Creation failed', 'error');
        }
    } catch (err) {
        showToast('Error creating profile', 'error');
    }
}

async function launchProfile(name) {
    try {
        showToast(`Launching ${name}...`, 'success'); // Optimistic UI
        const res = await fetch(`${API_BASE}/launch_profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (!data.ok) {
            showToast(data.error || 'Launch failed', 'error');
        }
    } catch (err) {
        showToast('Error launching profile', 'error');
    }
}

async function deleteProfile(name) {
    if (!confirm(`Are you sure you want to delete profile "${name}"? This cannot be undone.`)) return;

    try {
        const res = await fetch(`${API_BASE}/delete_profile`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();
        if (data.ok) {
            showToast(`Profile "${name}" deleted`, 'success');
            fetchProfiles();
        } else {
            showToast(data.error || 'Delete failed', 'error');
        }
    } catch (err) {
        showToast('Error deleting profile', 'error');
    }
}

function showToast(msg, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.className = `toast ${type}`;
    }, 3000);
}
