<template>
    <div class="folder-view" v-if="folder">
        <div class="viewer-header">
            <div class="nav-section">
                <button v-if="folder.breadcrumb && folder.breadcrumb.length > 0" class="back-btn" @click="goBack">
                    &larr; Back
                </button>
                <router-link v-else to="/" class="back-btn">&larr; Home</router-link>

                <div class="breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="(crumb, index) in folder.breadcrumb" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">
                            {{ crumb.name }}
                        </router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ folder.name }}</span>
                </div>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ folder.name }}</h1>
                    <span class="item-type-badge folder">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                        </svg>
                        Folder
                    </span>
                </div>
                <p class="item-description">{{ folder.description }}</p>
            </div>
        </div>

        <div class="folder-content">
            <!-- Subfolders -->
            <div v-if="folder.folders && folder.folders.length > 0" class="section">
            <h2 class="section-title">Subfolders</h2>
            <div class="folders-grid">
                <router-link
                    v-for="subfolder in folder.folders"
                    :key="subfolder.id"
                    :to="`/folder/${subfolder.id}`"
                    class="item-card folder-card"
                >
                    <div class="card-content">
                        <div class="card-info">
                            <div class="card-header">
                                <!-- Total count mode -->
                                <span v-if="settings.folderCountStyle !== 'detailed'" class="item-count total">
                                    {{ countExperiments(subfolder) }} {{ countExperiments(subfolder) === 1 ? 'element' : 'elements' }}
                                </span>
                                <!-- Detailed count mode -->
                                <div v-else class="element-counts" :class="{ 'with-labels': settings.folderCountLabels === 'text' }">
                                    <span v-if="countByType(subfolder, 'synchronized') > 0" class="count-badge synchronized" title="Synchronized Videos">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>
                                        </svg>
                                        {{ countByType(subfolder, 'synchronized') }}{{ settings.folderCountLabels === 'text' ? (countByType(subfolder, 'synchronized') === 1 ? ' Synchronized Video' : ' Synchronized Videos') : '' }}
                                    </span>
                                    <span v-if="countByType(subfolder, 'collection') > 0" class="count-badge collection" title="Video Collections">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                        </svg>
                                        {{ countByType(subfolder, 'collection') }}{{ settings.folderCountLabels === 'text' ? (countByType(subfolder, 'collection') === 1 ? ' Video Collection' : ' Video Collections') : '' }}
                                    </span>
                                    <span v-if="countByType(subfolder, 'pdf') > 0" class="count-badge pdf" title="PDFs">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
                                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                        </svg>
                                        {{ countByType(subfolder, 'pdf') }}{{ settings.folderCountLabels === 'text' ? (countByType(subfolder, 'pdf') === 1 ? ' PDF' : ' PDFs') : '' }}
                                    </span>
                                    <span v-if="countByType(subfolder, 'figures') > 0" class="count-badge figures" title="Figure Collections">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                        </svg>
                                        {{ countByType(subfolder, 'figures') }}{{ settings.folderCountLabels === 'text' ? (countByType(subfolder, 'figures') === 1 ? ' Figure Collection' : ' Figure Collections') : '' }}
                                    </span>
                                    <span v-if="countByType(subfolder, 'code') > 0" class="count-badge code" title="Code Snippets">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                            <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
                                        </svg>
                                        {{ countByType(subfolder, 'code') }}{{ settings.folderCountLabels === 'text' ? (countByType(subfolder, 'code') === 1 ? ' Code' : ' Code') : '' }}
                                    </span>
                                    <span v-if="countByType(subfolder, 'interactive') > 0" class="count-badge interactive" title="Interactive">
                                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                        </svg>
                                        {{ countByType(subfolder, 'interactive') }}{{ settings.folderCountLabels === 'text' ? ' Interactive' : '' }}
                                    </span>
                                </div>
                            </div>
                            <h2 class="card-title">
                                <svg class="folder-icon" width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                                </svg>
                                {{ subfolder.name }}
                            </h2>
                            <p class="card-description">{{ subfolder.description }}</p>
                            <div class="card-footer">
                                <span class="view-btn">Open &rarr;</span>
                            </div>
                        </div>
                        <div v-if="subfolder.image" class="card-image">
                            <img :src="`/thumbnails/${subfolder.image}`" :alt="subfolder.name" @error="onImageError">
                        </div>
                    </div>
                </router-link>
            </div>
        </div>

        <!-- Elements (Experiments, PDFs, Figures, etc.) -->
        <div v-if="folder.experiments && folder.experiments.length > 0" class="section">
            <h2 class="section-title">Content</h2>
            <div class="cards-grid">
                <router-link
                    v-for="exp in folder.experiments"
                    :key="exp.id"
                    :to="getItemRoute(exp)"
                    class="item-card element-card"
                    :class="getItemClass(exp.type)"
                >
                    <div class="card-content">
                        <div class="card-info">
                            <div class="card-header">
                                <span class="element-badge" :class="exp.type || 'synchronized'">
                                    <!-- Synchronized videos -->
                                    <svg v-if="!exp.type || exp.type === 'synchronized'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                        <circle cx="12" cy="12" r="10"/>
                                        <path d="M12 6v6l4 2"/>
                                    </svg>
                                    <!-- Collection -->
                                    <svg v-else-if="exp.type === 'collection'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                    </svg>
                                    <!-- PDF -->
                                    <svg v-else-if="exp.type === 'pdf'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                        <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
                                    </svg>
                                    <!-- Figures -->
                                    <svg v-else-if="exp.type === 'figures'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                        <circle cx="8.5" cy="8.5" r="1.5"/>
                                        <polyline points="21 15 16 10 5 21"/>
                                    </svg>
                                    <!-- Code -->
                                    <svg v-else-if="exp.type === 'code'" class="badge-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <polyline points="16 18 22 12 16 6"/>
                                        <polyline points="8 6 2 12 8 18"/>
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

            <div v-if="(!folder.folders || folder.folders.length === 0) && (!folder.experiments || folder.experiments.length === 0)" class="empty-state">
                <p>This folder is empty</p>
            </div>
        </div>
    </div>

    <div v-else class="loading">
        Loading folder...
    </div>
</template>

<script setup>
import { ref, watch, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
    id: String
})

const settings = inject('settings')
const route = useRoute()
const router = useRouter()
const folder = ref(null)

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

function goBack() {
    if (folder.value?.breadcrumb && folder.value.breadcrumb.length > 0) {
        const parent = folder.value.breadcrumb[folder.value.breadcrumb.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

async function loadFolder(folderId) {
    try {
        const response = await fetch(`/api/folders/${folderId}`)
        folder.value = await response.json()
    } catch (error) {
        console.error('Failed to load folder:', error)
    }
}

loadFolder(props.id)

watch(() => route.params.id, (newId) => {
    if (newId) {
        loadFolder(newId)
    }
})
</script>

<style scoped>
.folder-view {
    width: 100%;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
    flex-shrink: 0;
    padding-bottom: 16px;
    border-bottom: 1px solid #222;
}

.folder-content {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    width: 100%;
    max-width: 1200px;
    margin: 0 auto;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 8px;
}

.back-btn {
    color: #fff;
    text-decoration: none;
    font-size: 14px;
    padding: 8px 16px;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    transition: all 0.2s;
    flex-shrink: 0;
    cursor: pointer;
}

.back-btn:hover {
    background: #222;
    border-color: #444;
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    flex-wrap: wrap;
}

.breadcrumb-item {
    color: #888;
    text-decoration: none;
    padding: 4px 10px;
    background: #1a1a1a;
    border-radius: 6px;
    transition: all 0.2s;
}

.breadcrumb-item:hover:not(.current) {
    background: #222;
    color: #fff;
}

.breadcrumb-item.current {
    color: #fff;
    background: #333;
}

.breadcrumb-sep {
    color: #444;
}

.title-row {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
}

.item-title {
    font-size: 24px;
    font-weight: 600;
    margin: 0;
}

.item-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 6px;
}

.item-type-badge.folder {
    background: rgba(156, 163, 175, 0.15);
    color: #9ca3af;
    border: 1px solid rgba(156, 163, 175, 0.3);
}

.item-description {
    color: #888;
    font-size: 14px;
    margin-top: 8px;
}

.section {
    margin-bottom: 40px;
    width: 100%;
}

.section-title {
    font-size: 18px;
    font-weight: 600;
    color: #888;
    margin-bottom: 16px;
}

.folders-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    width: 100%;
}

.cards-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    width: 100%;
}

.item-card {
    background: #161616;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 24px;
    text-decoration: none;
    color: inherit;
    transition: all 0.2s ease;
}

.item-card:hover {
    border-color: #3b82f6;
    transform: translateY(-2px);
}

.folder-card {
    border-left: 3px solid #6b7280;
}

.card-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 24px;
}

.card-info {
    flex: 1;
    min-width: 0;
}

.card-image {
    width: 120px;
    height: 75px;
    border-radius: 8px;
    overflow: hidden;
    flex-shrink: 0;
    background: #111;
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

.item-count.total {
    background: #8b5cf6;
    color: white;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 500;
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
.element-card.type-synchronized {
    border-left: 3px solid #3b82f6;
}

.element-card.type-collection {
    border-left: 3px solid #f59e0b;
}

.element-card.type-pdf {
    border-left: 3px solid #ef4444;
}

.element-card.type-figures {
    border-left: 3px solid #a855f7;
}

.element-card.type-interactive {
    border-left: 3px solid #22c55e;
}

.meta-info {
    color: #666;
    font-size: 13px;
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
    margin-bottom: 8px;
}

.folder-icon {
    color: #9ca3af;
    flex-shrink: 0;
}

.card-description {
    color: #888;
    font-size: 14px;
    line-height: 1.5;
}

.card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 16px;
    margin-top: 16px;
    border-top: 1px solid #222;
}

.view-btn {
    color: #3b82f6;
    font-weight: 500;
    font-size: 14px;
}

.empty-state {
    text-align: center;
    padding: 60px;
    color: #666;
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: #888;
}
</style>
