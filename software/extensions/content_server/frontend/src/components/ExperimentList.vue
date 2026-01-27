<template>
    <div class="experiment-list">
        <h1 class="page-title">{{ settings.homeTitle || 'Additional Material' }}</h1>
        <p class="page-subtitle">{{ settings.homeSubtitle || 'Browse chapters and sections' }}</p>

        <!-- Accordion Style Folders -->
        <div v-if="settings.folderStyle === 'accordion' && folders.length > 0" class="section">
            <div class="items-grid">
                <div
                    v-for="folder in folders"
                    :key="folder.id"
                    class="item-card folder-card"
                    :class="{ expanded: expandedFolder === folder.id }"
                    @click="toggleFolder(folder.id)"
                >
                    <div class="card-content">
                        <div class="card-info">
                            <div class="card-header">
                                <span class="item-count">{{ countExperiments(folder) }} experiments</span>
                                <span class="folder-icon">{{ expandedFolder === folder.id ? '&#9660;' : '&#9654;' }}</span>
                            </div>
                            <h2 class="card-title">
                                <svg class="folder-svg-icon" width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                                </svg>
                                {{ folder.name }}
                            </h2>
                            <p class="card-description">{{ folder.description }}</p>
                        </div>
                        <div v-if="folder.image" class="card-image">
                            <img :src="`/thumbnails/${folder.image}`" :alt="folder.name" @error="onImageError">
                        </div>
                    </div>

                    <div v-if="expandedFolder === folder.id" class="folder-experiments" @click.stop>
                        <router-link
                            v-for="exp in folder.experiments"
                            :key="exp.id"
                            :to="getItemRoute(exp)"
                            class="item-card experiment-card nested"
                            :class="getItemClass(exp.type)"
                        >
                            <div class="card-content">
                                <div class="card-info">
                                    <div class="card-header">
                                        <span class="element-badge" :class="exp.type || 'synchronized'">
                                            <!-- Synchronized -->
                                            <svg v-if="!exp.type || exp.type === 'synchronized'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                                <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                                            </svg>
                                            <!-- Collection -->
                                            <svg v-else-if="exp.type === 'collection'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                            </svg>
                                            <!-- PDF -->
                                            <svg v-else-if="exp.type === 'pdf'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                            </svg>
                                            <!-- Figures -->
                                            <svg v-else-if="exp.type === 'figures'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                                            </svg>
                                            <!-- Code -->
                                            <svg v-else-if="exp.type === 'code'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                                            </svg>
                                            <!-- Interactive -->
                                            <svg v-else-if="exp.type === 'interactive'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                            </svg>
                                            {{ getBadgeText(exp) }}
                                        </span>
                                        <span class="date">{{ exp.date }}</span>
                                    </div>
                                    <h3 class="card-title">{{ exp.title }}</h3>
                                    <p class="card-description">{{ exp.description }}</p>
                                    <div class="card-footer">
                                        <span class="meta-info">{{ getMetaInfo(exp) }}</span>
                                        <span class="view-btn">View &rarr;</span>
                                    </div>
                                </div>
                                <div v-if="exp.image" class="card-image small">
                                    <img :src="`/thumbnails/${exp.image}`" :alt="exp.title" @error="onImageError">
                                </div>
                            </div>
                        </router-link>
                    </div>
                </div>
            </div>
        </div>

        <!-- Navigation Style Folders -->
        <div v-if="settings.folderStyle === 'navigation' && folders.length > 0" class="section">
            <div class="folders-grid">
                <router-link
                    v-for="folder in folders"
                    :key="folder.id"
                    :to="`/folder/${folder.id}`"
                    class="item-card folder-card-nav"
                >
                    <div class="card-content">
                        <div class="card-info">
                            <div class="card-header">
                                <!-- Total count mode -->
                                <span v-if="settings.folderCountStyle !== 'detailed'" class="item-count">
                                    {{ countExperiments(folder) }} {{ countExperiments(folder) === 1 ? 'element' : 'elements' }}
                                </span>
                                <!-- Detailed count mode -->
                                <div v-else class="element-counts" :class="{ 'with-labels': settings.folderCountLabels === 'text' }">
                                    <span v-if="countByType(folder, 'synchronized') > 0" class="count-badge synchronized" title="Synchronized Videos">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                                        </svg>
                                        {{ countByType(folder, 'synchronized') }}{{ settings.folderCountLabels === 'text' ? (countByType(folder, 'synchronized') === 1 ? ' Synchronized Video' : ' Synchronized Videos') : '' }}
                                    </span>
                                    <span v-if="countByType(folder, 'collection') > 0" class="count-badge collection" title="Video Collections">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                        </svg>
                                        {{ countByType(folder, 'collection') }}{{ settings.folderCountLabels === 'text' ? (countByType(folder, 'collection') === 1 ? ' Video Collection' : ' Video Collections') : '' }}
                                    </span>
                                    <span v-if="countByType(folder, 'pdf') > 0" class="count-badge pdf" title="PDFs">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                        </svg>
                                        {{ countByType(folder, 'pdf') }}{{ settings.folderCountLabels === 'text' ? (countByType(folder, 'pdf') === 1 ? ' PDF' : ' PDFs') : '' }}
                                    </span>
                                    <span v-if="countByType(folder, 'figures') > 0" class="count-badge figures" title="Figure Collections">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                        </svg>
                                        {{ countByType(folder, 'figures') }}{{ settings.folderCountLabels === 'text' ? (countByType(folder, 'figures') === 1 ? ' Figure Collection' : ' Figure Collections') : '' }}
                                    </span>
                                    <span v-if="countByType(folder, 'code') > 0" class="count-badge code" title="Code Snippets">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                                        </svg>
                                        {{ countByType(folder, 'code') }}{{ settings.folderCountLabels === 'text' ? ' Code' : '' }}
                                    </span>
                                    <span v-if="countByType(folder, 'interactive') > 0" class="count-badge interactive" title="Interactive">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                        </svg>
                                        {{ countByType(folder, 'interactive') }}{{ settings.folderCountLabels === 'text' ? ' Interactive' : '' }}
                                    </span>
                                </div>
                            </div>
                            <h2 class="card-title">
                                <svg class="folder-svg-icon" width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                                </svg>
                                {{ folder.name }}
                            </h2>
                            <p class="card-description">{{ folder.description }}</p>
                            <div class="card-footer">
                                <span class="view-btn">Open &rarr;</span>
                            </div>
                        </div>
                        <div v-if="folder.image" class="card-image">
                            <img :src="`/thumbnails/${folder.image}`" :alt="folder.name" @error="onImageError">
                        </div>
                    </div>
                </router-link>
            </div>
        </div>

        <!-- Standalone Experiments (after navigation folders) -->
        <div v-if="experiments.length > 0" class="section">
            <h2 v-if="folders.length > 0" class="section-title">Other Content</h2>
            <div class="cards-grid">
                <router-link
                    v-for="exp in experiments"
                    :key="exp.id"
                    :to="getItemRoute(exp)"
                    class="item-card experiment-card"
                    :class="getItemClass(exp.type)"
                >
                    <div class="card-content">
                        <div class="card-info">
                            <div class="card-header">
                                <span class="element-badge" :class="exp.type || 'synchronized'">
                                    <!-- Synchronized -->
                                    <svg v-if="!exp.type || exp.type === 'synchronized'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                        <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                                    </svg>
                                    <!-- Collection -->
                                    <svg v-else-if="exp.type === 'collection'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                    </svg>
                                    <!-- PDF -->
                                    <svg v-else-if="exp.type === 'pdf'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                    </svg>
                                    <!-- Figures -->
                                    <svg v-else-if="exp.type === 'figures'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                                    </svg>
                                    <!-- Interactive -->
                                    <svg v-else-if="exp.type === 'interactive'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                    </svg>
                                    {{ getBadgeText(exp) }}
                                </span>
                                <span class="date">{{ exp.date }}</span>
                            </div>
                            <h2 class="card-title">{{ exp.title }}</h2>
                            <p class="card-description">{{ exp.description }}</p>
                            <div class="card-footer">
                                <span class="meta-info">{{ getMetaInfo(exp) }}</span>
                                <span class="view-btn">View &rarr;</span>
                            </div>
                        </div>
                        <div v-if="exp.image" class="card-image">
                            <img :src="`/thumbnails/${exp.image}`" :alt="exp.title" @error="onImageError">
                        </div>
                    </div>
                </router-link>
            </div>
        </div>

        <div v-if="folders.length === 0 && experiments.length === 0" class="empty-state">
            <p>No experiments found. Add experiments to experiments.json</p>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted, inject } from 'vue'

const settings = inject('settings')
const folders = ref([])
const experiments = ref([])
const expandedFolder = ref(null)

function toggleFolder(folderId) {
    expandedFolder.value = expandedFolder.value === folderId ? null : folderId
}

function countExperiments(folder) {
    let count = folder.experiments?.length || 0
    if (folder.folders) {
        for (const subfolder of folder.folders) {
            count += countExperiments(subfolder)
        }
    }
    return count
}

function countByType(folder, type) {
    let count = 0
    if (folder.experiments) {
        for (const exp of folder.experiments) {
            const expType = exp.type || 'synchronized'
            if (expType === type) count++
        }
    }
    if (folder.folders) {
        for (const subfolder of folder.folders) {
            count += countByType(subfolder, type)
        }
    }
    return count
}

function onImageError(event) {
    event.target.style.display = 'none'
}

function getItemRoute(item) {
    const type = item.type || 'synchronized'
    if (type === 'pdf') return `/pdf/${item.id}`
    if (type === 'figures') return `/figures/${item.id}`
    if (type === 'code') return `/code/${item.id}`
    return `/experiment/${item.id}`
}

function getItemClass(type) {
    return `type-${type || 'synchronized'}`
}

function getBadgeIcon(type) {
    // Return inline SVG based on type - using functional component pattern
    return {
        functional: true,
        render: (h) => null // placeholder, actual icons are in template
    }
}

function getBadgeText(item) {
    const type = item.type || 'synchronized'
    const videoCount = item.videos?.length || 0
    const figureCount = item.figures?.length || 0
    if (type === 'synchronized') return `${videoCount} ${videoCount === 1 ? 'video' : 'videos'}`
    if (type === 'collection') return `${videoCount} ${videoCount === 1 ? 'clip' : 'clips'}`
    if (type === 'pdf') return 'PDF'
    if (type === 'figures') return `${figureCount} ${figureCount === 1 ? 'figure' : 'figures'}`
    if (type === 'code') return item.language || 'Code'
    if (type === 'interactive') return '3D'
    return type
}

function getMetaInfo(item) {
    const type = item.type || 'synchronized'
    if (type === 'synchronized') return `${item.markers?.length || 0} markers`
    if (type === 'collection') return 'Comparison'
    if (type === 'pdf') return 'Document'
    if (type === 'figures') return 'Gallery'
    if (type === 'code') return 'Snippet'
    if (type === 'interactive') return 'Interactive'
    return ''
}

onMounted(async () => {
    try {
        const response = await fetch('/api/experiments')
        const data = await response.json()
        folders.value = data.folders || []
        experiments.value = data.experiments || []
    } catch (error) {
        console.error('Failed to load experiments:', error)
    }
})
</script>

<style scoped>
.experiment-list {
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

.page-title {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 8px;
}

.page-subtitle {
    color: #888;
    margin-bottom: 32px;
}

.section {
    margin-bottom: 28px;
}

.section-title {
    font-size: 18px;
    font-weight: 600;
    color: #888;
    margin-bottom: 16px;
}

.items-grid {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
    gap: 16px;
}

.folders-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    align-items: stretch;
}

.item-card {
    background: #161616;
    border: 1px solid #222;
    border-radius: 10px;
    padding: 18px;
    text-decoration: none;
    color: inherit;
    transition: all 0.2s ease;
    display: flex;
    flex-direction: column;
}

.item-card:hover {
    border-color: #3b82f6;
}

.experiment-card:hover,
.folder-card-nav:hover {
    transform: translateY(-2px);
}

.folder-card {
    cursor: pointer;
}

.folder-card.expanded {
    border-color: #3b82f6;
}

.folder-card-nav {
    border-left: 3px solid #6b7280;
}

.card-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 18px;
    flex: 1;
}

.card-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
}

.card-image {
    width: 160px;
    height: 100px;
    border-radius: 8px;
    overflow: hidden;
    flex-shrink: 0;
    background: #111;
}

.card-image.small {
    width: 120px;
    height: 75px;
}

.card-image img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    font-size: 13px;
    min-height: 26px;
}

.element-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 500;
    font-size: 12px;
}

.element-badge.synchronized {
    background: #3b82f6;
    color: white;
}

.element-badge.collection {
    background: #f59e0b;
    color: white;
}

.element-badge.pdf {
    background: #ef4444;
    color: white;
}

.element-badge.figures {
    background: #a855f7;
    color: white;
}

.element-badge.code {
    background: #06b6d4;
    color: white;
}

.element-badge.interactive {
    background: #22c55e;
    color: white;
}

.badge-icon {
    flex-shrink: 0;
}

/* Element card type styling */
.experiment-card.type-synchronized {
    border-left: 3px solid #3b82f6;
}

.experiment-card.type-collection {
    border-left: 3px solid #f59e0b;
}

.experiment-card.type-pdf {
    border-left: 3px solid #ef4444;
}

.experiment-card.type-figures {
    border-left: 3px solid #a855f7;
}

.experiment-card.type-interactive {
    border-left: 3px solid #22c55e;
}

.meta-info {
    color: #666;
    font-size: 13px;
}

.item-count {
    background: #8b5cf6;
    color: white;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 500;
}

/* Element counts for detailed mode */
.element-counts {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
}

.element-counts.with-labels {
    gap: 8px;
}

.count-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 6px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 500;
}

.count-badge.synchronized {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
}

.count-badge.collection {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
}

.count-badge.pdf {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
}

.count-badge.figures {
    background: rgba(168, 85, 247, 0.2);
    color: #c084fc;
}

.count-badge.code {
    background: rgba(6, 182, 212, 0.2);
    color: #22d3ee;
}

.count-badge.interactive {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
}

.folder-icon {
    color: #666;
    font-size: 12px;
}

.date {
    color: #666;
}

.card-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 6px;
}

.folder-svg-icon {
    color: #9ca3af;
    flex-shrink: 0;
}

.nested .card-title {
    font-size: 16px;
}

.card-description {
    color: #888;
    font-size: 13px;
    line-height: 1.4;
}

.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 12px;
    margin-top: auto;
    border-top: 1px solid #222;
}

.marker-count {
    color: #666;
    font-size: 13px;
}

.view-btn {
    color: #3b82f6;
    font-weight: 500;
    font-size: 14px;
}

.folder-experiments {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #222;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.folder-experiments .item-card {
    background: #1a1a1a;
    padding: 16px 20px;
}

.empty-state {
    text-align: center;
    padding: 60px;
    color: #666;
}

</style>
