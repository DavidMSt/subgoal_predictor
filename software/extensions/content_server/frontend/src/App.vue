<template>
    <div class="app-container">
        <header class="header">
            <div class="header-left">
                <button class="sidebar-toggle" @click="toggleSidebar" :title="sidebarOpen ? 'Close navigation' : 'Open navigation'">
                    <svg v-if="!sidebarOpen" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="3" y1="12" x2="21" y2="12"/>
                        <line x1="3" y1="6" x2="21" y2="6"/>
                        <line x1="3" y1="18" x2="21" y2="18"/>
                    </svg>
                    <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
                <router-link to="/" class="logo" @click="clearSearch">
                    <img v-if="settings.logo" :src="`/${settings.logo}`" alt="Logo" class="logo-img">
                    <span v-else class="logo-icon">&#9654;</span>
                    <span class="logo-text">{{ settings.title || 'Additional Material' }}</span>
                </router-link>
            </div>

            <div class="search-container">
                <div class="search-box">
                    <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="m21 21-4.35-4.35"/>
                    </svg>
                    <input
                        type="text"
                        v-model="searchQuery"
                        @input="onSearchInput"
                        @focus="showResults = true"
                        placeholder="Search material..."
                        class="search-input"
                    >
                    <button v-if="searchQuery" class="clear-btn" @click="clearSearch">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
                <button class="help-btn" @click="showHelpModal = true" title="Help">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                        <circle cx="12" cy="17" r="0.5" fill="currentColor"/>
                    </svg>
                </button>

                <div class="search-results" v-if="showResults && searchQuery && searchResults.length > 0">
                    <router-link
                        v-for="result in searchResults"
                        :key="result.id"
                        :to="getSearchResultRoute(result)"
                        class="search-result"
                        @click="clearSearch"
                    >
                        <div class="result-header">
                            <span v-if="result.type === 'folder'" class="result-type folder">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                                </svg>
                                Folder
                            </span>
                            <span v-else-if="result.experimentType === 'pdf'" class="result-type pdf">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                    <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
                                </svg>
                                PDF
                            </span>
                            <span v-else-if="result.experimentType === 'figures'" class="result-type figures">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                    <polyline points="21 15 16 10 5 21"/>
                                </svg>
                                Figure Collection
                            </span>
                            <span v-else-if="result.experimentType === 'code'" class="result-type code">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="16 18 22 12 16 6"/>
                                    <polyline points="8 6 2 12 8 18"/>
                                </svg>
                                Code
                            </span>
                            <span v-else-if="result.experimentType === 'collection'" class="result-type collection">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                </svg>
                                Video Collection
                            </span>
                            <span v-else class="result-type experiment">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <path d="M12 6v6l4 2"/>
                                </svg>
                                Synchronized Videos
                            </span>
                        </div>
                        <div class="result-title">{{ result.title }}</div>
                        <div class="result-meta">
                            <span class="result-path" v-if="result.folderPath && result.folderPath.length > 0">
                                {{ result.folderPath.map(f => f.name).join(' / ') }}
                            </span>
                            <span v-if="result.type === 'folder'" class="result-count">{{ result.experimentCount }} {{ result.experimentCount === 1 ? 'element' : 'elements' }}</span>
                            <span v-else-if="result.experimentType === 'pdf'" class="result-count pdf">1 document</span>
                            <span v-else-if="result.experimentType === 'figures'" class="result-count figures">{{ result.videoCount || 0 }} {{ (result.videoCount || 0) === 1 ? 'figure' : 'figures' }}</span>
                            <span v-else-if="result.experimentType === 'code'" class="result-count code">{{ result.language || 'code' }}</span>
                            <span v-else class="result-count" :class="result.experimentType === 'collection' ? 'collection' : ''">{{ result.videoCount }} {{ result.experimentType === 'collection' ? (result.videoCount === 1 ? 'clip' : 'clips') : (result.videoCount === 1 ? 'video' : 'videos') }}</span>
                        </div>
                    </router-link>
                </div>

                <div class="search-results" v-if="showResults && searchQuery && searchResults.length === 0 && !isSearching">
                    <div class="no-results">No results found</div>
                </div>
            </div>
        </header>

        <div class="content-wrapper">
            <!-- Sidebar -->
            <aside class="sidebar" :class="{ open: sidebarOpen }">
                <div class="sidebar-header">
                    <span class="sidebar-title">Navigation</span>
                    <button class="collapse-all-btn" @click="collapseAll" title="Collapse all">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="4 14 10 14 10 20"/>
                            <polyline points="20 10 14 10 14 4"/>
                            <line x1="14" y1="10" x2="21" y2="3"/>
                            <line x1="3" y1="21" x2="10" y2="14"/>
                        </svg>
                    </button>
                </div>
                <nav class="sidebar-nav">
                    <router-link to="/" class="nav-item home-link" @click="closeSidebarOnMobile">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                            <polyline points="9 22 9 12 15 12 15 22"/>
                        </svg>
                        <span>Home</span>
                    </router-link>

                    <div class="nav-tree">
                        <template v-for="folder in structure.folders" :key="folder.id">
                            <NavFolder
                                :folder="folder"
                                :expanded-folders="expandedFolders"
                                :depth="0"
                                @toggle="toggleFolder"
                                @navigate="closeSidebarOnMobile"
                            />
                        </template>
                    </div>
                </nav>
            </aside>

            <!-- Main content -->
            <main class="main-content" :class="{ 'sidebar-open': sidebarOpen }" @click="showResults = false">
                <router-view :settings="settings" />
            </main>
        </div>

        <!-- Help Modal -->
        <div v-if="showHelpModal" class="modal-overlay" @click.self="showHelpModal = false">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>About This Application</h2>
                    <button class="modal-close" @click="showHelpModal = false">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
                <div class="modal-body">
                    <p class="help-intro">
                        This application provides access to additional materials organized in folders.
                        Browse through the navigation or use the search bar to find specific content.
                    </p>

                    <h3>Material Types</h3>
                    <div class="help-types">
                        <div class="help-type">
                            <span class="help-type-badge synchronized">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <path d="M12 6v6l4 2"/>
                                </svg>
                                Synchronized Videos
                            </span>
                            <p>Multiple videos that play together in sync with shared markers and annotations.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge collection">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                </svg>
                                Video Collection
                            </span>
                            <p>A collection of independent video clips for comparison or grouped viewing.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge figures">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                    <polyline points="21 15 16 10 5 21"/>
                                </svg>
                                Figure Collection
                            </span>
                            <p>An image gallery containing figures, diagrams, or other visual content.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge pdf">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                </svg>
                                PDF
                            </span>
                            <p>PDF documents such as papers, reports, or presentations.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge code">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="16 18 22 12 16 6"/>
                                    <polyline points="8 6 2 12 8 18"/>
                                </svg>
                                Code
                            </span>
                            <p>Source code snippets with syntax highlighting.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge interactive">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                </svg>
                                Interactive
                            </span>
                            <p>3D models and interactive visualizations.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, onMounted, provide, h, defineComponent, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()

// NavFolder component defined inline
const NavFolder = defineComponent({
    name: 'NavFolder',
    props: {
        folder: Object,
        expandedFolders: Object,
        depth: Number
    },
    emits: ['toggle', 'navigate'],
    setup(props, { emit }) {
        const getItemRoute = (item) => {
            const type = item.type || 'synchronized'
            if (type === 'pdf') return `/pdf/${item.id}`
            if (type === 'figures') return `/figures/${item.id}`
            if (type === 'code') return `/code/${item.id}`
            return `/experiment/${item.id}`
        }

        const getTypeClass = (type) => type || 'synchronized'

        const getTypeIcon = (type) => {
            const icons = {
                synchronized: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('circle', { cx: 12, cy: 12, r: 10 }),
                    h('path', { d: 'M12 6v6l4 2' })
                ]),
                collection: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                    h('path', { d: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20' }),
                    h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z' })
                ]),
                pdf: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                    h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' })
                ]),
                figures: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('rect', { x: 3, y: 3, width: 18, height: 18, rx: 2, ry: 2 }),
                    h('circle', { cx: 8.5, cy: 8.5, r: 1.5 }),
                    h('polyline', { points: '21 15 16 10 5 21' })
                ]),
                code: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('polyline', { points: '16 18 22 12 16 6' }),
                    h('polyline', { points: '8 6 2 12 8 18' })
                ]),
                interactive: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('path', { d: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z' })
                ])
            }
            return icons[type] || icons.synchronized
        }

        return () => {
            const isExpanded = props.expandedFolders[props.folder.id]
            const hasChildren = (props.folder.folders?.length > 0) || (props.folder.experiments?.length > 0)
            const paddingLeft = `${12 + props.depth * 16}px`

            const children = []

            // Folder header
            children.push(
                h('div', { class: 'nav-folder-header', style: { paddingLeft } }, [
                    h('button', {
                        class: ['nav-folder-toggle', { expanded: isExpanded, 'no-children': !hasChildren }],
                        onClick: () => emit('toggle', props.folder.id)
                    }, [
                        hasChildren ? h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                            h('polyline', { points: '9 18 15 12 9 6' })
                        ]) : null
                    ]),
                    h(RouterLink, {
                        to: `/folder/${props.folder.id}`,
                        class: 'nav-folder-link',
                        onClick: () => emit('navigate'),
                        onDblclick: (e) => {
                            e.preventDefault()
                            emit('toggle', props.folder.id)
                        }
                    }, () => [
                        h('svg', { class: 'nav-folder-icon', width: 16, height: 16, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                            h('path', { d: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' })
                        ]),
                        h('span', { class: 'nav-folder-name' }, props.folder.name)
                    ])
                ])
            )

            // Children (if expanded)
            if (isExpanded && hasChildren) {
                const childElements = []

                // Subfolders
                if (props.folder.folders) {
                    props.folder.folders.forEach(subfolder => {
                        childElements.push(
                            h(NavFolder, {
                                key: subfolder.id,
                                folder: subfolder,
                                expandedFolders: props.expandedFolders,
                                depth: props.depth + 1,
                                onToggle: (id) => emit('toggle', id),
                                onNavigate: () => emit('navigate')
                            })
                        )
                    })
                }

                // Experiments
                if (props.folder.experiments) {
                    props.folder.experiments.forEach(exp => {
                        const expPaddingLeft = `${12 + (props.depth + 1) * 16}px`
                        childElements.push(
                            h(RouterLink, {
                                key: exp.id,
                                to: getItemRoute(exp),
                                class: ['nav-item', 'nav-experiment', getTypeClass(exp.type)],
                                style: { paddingLeft: expPaddingLeft },
                                onClick: () => emit('navigate')
                            }, () => [
                                h('span', { class: ['nav-item-icon', getTypeClass(exp.type)] }, [getTypeIcon(exp.type)]),
                                h('span', { class: 'nav-item-name' }, exp.title)
                            ])
                        )
                    })
                }

                children.push(h('div', { class: 'nav-folder-children' }, childElements))
            }

            return h('div', { class: 'nav-folder' }, children)
        }
    }
})

const settings = ref({
    title: 'Additional Material',
    folderStyle: 'accordion',
    logo: 'bilbolab_logo.png'
})

const searchQuery = ref('')
const searchResults = ref([])
const showResults = ref(false)
const isSearching = ref(false)
const sidebarOpen = ref(false)
const structure = ref({ folders: [], experiments: [] })
const expandedFolders = ref({})
const showHelpModal = ref(false)
let searchTimeout = null

provide('settings', settings)

function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
    // Save preference
    localStorage.setItem('sidebarOpen', sidebarOpen.value.toString())
}

function closeSidebarOnMobile() {
    if (window.innerWidth < 768) {
        sidebarOpen.value = false
    }
}

function toggleFolder(folderId) {
    expandedFolders.value[folderId] = !expandedFolders.value[folderId]
}

function collapseAll() {
    expandedFolders.value = {}
}

// Find path to an item (folder or experiment) by ID
function findPathToItem(folders, targetId, currentPath = []) {
    for (const folder of folders) {
        // Check if this folder matches
        if (folder.id === targetId) {
            return currentPath
        }

        // Check experiments in this folder
        if (folder.experiments) {
            for (const exp of folder.experiments) {
                if (exp.id === targetId) {
                    return [...currentPath, folder.id]
                }
            }
        }

        // Recursively check subfolders
        if (folder.folders) {
            const result = findPathToItem(folder.folders, targetId, [...currentPath, folder.id])
            if (result) {
                return result
            }
        }
    }
    return null
}

// Expand path to current route item in sidebar
function expandPathToRoute() {
    const path = route.path
    let targetId = null

    // Extract ID from route
    if (path.startsWith('/folder/')) {
        targetId = path.replace('/folder/', '')
    } else if (path.startsWith('/experiment/')) {
        targetId = path.replace('/experiment/', '')
    } else if (path.startsWith('/pdf/')) {
        targetId = path.replace('/pdf/', '')
    } else if (path.startsWith('/figures/')) {
        targetId = path.replace('/figures/', '')
    } else if (path.startsWith('/code/')) {
        targetId = path.replace('/code/', '')
    }

    if (targetId && structure.value.folders) {
        const pathToItem = findPathToItem(structure.value.folders, targetId)
        if (pathToItem) {
            // Expand all folders in the path
            pathToItem.forEach(folderId => {
                expandedFolders.value[folderId] = true
            })
        }
    }
}

// Watch for route changes to expand sidebar path
watch(() => route.path, () => {
    expandPathToRoute()
})

async function onSearchInput() {
    if (searchTimeout) clearTimeout(searchTimeout)

    if (!searchQuery.value.trim()) {
        searchResults.value = []
        return
    }

    isSearching.value = true
    searchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.value)}`)
            const data = await response.json()
            searchResults.value = data.results || []
        } catch (error) {
            console.error('Search failed:', error)
            searchResults.value = []
        }
        isSearching.value = false
    }, 200)
}

function clearSearch() {
    searchQuery.value = ''
    searchResults.value = []
    showResults.value = false
}

function getSearchResultRoute(result) {
    if (result.type === 'folder') {
        return `/folder/${result.id}`
    }
    if (result.experimentType === 'pdf') {
        return `/pdf/${result.id}`
    }
    if (result.experimentType === 'figures') {
        return `/figures/${result.id}`
    }
    if (result.experimentType === 'code') {
        return `/code/${result.id}`
    }
    return `/experiment/${result.id}`
}

onMounted(async () => {
    // Load settings
    try {
        const response = await fetch('/api/settings')
        const data = await response.json()
        settings.value = { ...settings.value, ...data }
    } catch (error) {
        console.error('Failed to load settings:', error)
    }

    // Load structure for sidebar
    try {
        const response = await fetch('/api/experiments')
        structure.value = await response.json()

        // Expand path to current route after structure is loaded
        expandPathToRoute()
    } catch (error) {
        console.error('Failed to load structure:', error)
    }

    // Restore sidebar state
    const savedSidebarState = localStorage.getItem('sidebarOpen')
    if (savedSidebarState !== null) {
        sidebarOpen.value = savedSidebarState === 'true'
    }
})
</script>

<style>
.app-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.header {
    background: #111;
    border-bottom: 1px solid #222;
    padding: 10px 24px;
    flex-shrink: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 24px;
    z-index: 100;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}

.sidebar-toggle {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #888;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}

.sidebar-toggle:hover {
    background: #222;
    color: #fff;
    border-color: #444;
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 20px;
    font-weight: 600;
    color: #fff;
    text-decoration: none;
    flex-shrink: 0;
}

.logo-text {
    position: relative;
    top: 5px;
}

.logo-img {
    height: 36px;
    width: auto;
}

.logo-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 8px;
    font-size: 14px;
}

.search-container {
    position: relative;
    width: 100%;
    max-width: 450px;
    display: flex;
    align-items: center;
}

.search-box {
    display: flex;
    align-items: center;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 0 12px;
    transition: border-color 0.2s;
    flex: 1;
}

.search-box:focus-within {
    border-color: #3b82f6;
}

.search-icon {
    color: #666;
    flex-shrink: 0;
}

.search-input {
    flex: 1;
    background: none;
    border: none;
    color: #fff;
    font-size: 14px;
    padding: 10px 12px;
    outline: none;
}

.search-input::placeholder {
    color: #666;
}

.clear-btn {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
}

.clear-btn:hover {
    color: #fff;
}

.search-results {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 8px;
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
    z-index: 100;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.search-result {
    display: block;
    padding: 12px 16px;
    text-decoration: none;
    color: inherit;
    border-bottom: 1px solid #222;
    transition: background 0.2s;
}

.search-result:last-child {
    border-bottom: none;
}

.search-result:hover {
    background: #222;
}

.result-header {
    margin-bottom: 4px;
}

.result-type {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 4px;
}

.result-type.folder {
    background: rgba(107, 114, 128, 0.2);
    color: #9ca3af;
}

.result-type.experiment {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
}

.result-type.collection {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
}

.result-type.pdf {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
}

.result-type.figures {
    background: rgba(16, 185, 129, 0.2);
    color: #34d399;
}

.result-type.code {
    background: rgba(6, 182, 212, 0.2);
    color: #22d3ee;
}

.result-title {
    font-weight: 500;
    margin-bottom: 4px;
}

.result-meta {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #888;
}

.result-path {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-right: 12px;
}

.result-count {
    flex-shrink: 0;
    color: #3b82f6;
}

.result-count.collection {
    color: #f59e0b;
}

.result-count.pdf {
    color: #f87171;
}

.result-count.figures {
    color: #34d399;
}

.result-count.code {
    color: #22d3ee;
}

.no-results {
    padding: 16px;
    text-align: center;
    color: #666;
}

/* Content wrapper with sidebar */
.content-wrapper {
    flex: 1;
    display: flex;
    min-height: 0;
    overflow: hidden;
}

/* Sidebar */
.sidebar {
    width: 280px;
    background: #0d0d0d;
    border-right: 1px solid #222;
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    position: absolute;
    left: 0;
    top: 61px;
    bottom: 0;
    z-index: 50;
}

.sidebar.open {
    transform: translateX(0);
}

/* On larger screens, push content when sidebar is open */
@media (min-width: 1024px) {
    .main-content.sidebar-open {
        margin-left: 280px;
    }
}

.sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid #222;
    flex-shrink: 0;
}

.sidebar-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #666;
}

.collapse-all-btn {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.2s;
}

.collapse-all-btn:hover {
    background: #1a1a1a;
    color: #fff;
}

.sidebar-nav {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    color: #888;
    text-decoration: none;
    font-size: 13px;
    transition: all 0.15s;
    border-left: 2px solid transparent;
}

.nav-item:hover {
    background: #1a1a1a;
    color: #fff;
}

.nav-item.router-link-active {
    background: #1a1a1a;
    color: #fff;
    border-left-color: #3b82f6;
}

.home-link {
    margin-bottom: 8px;
    border-bottom: 1px solid #222;
    padding-bottom: 12px;
}

/* Nav tree */
.nav-tree {
    padding-top: 4px;
}

.nav-folder {
    user-select: none;
}

.nav-folder-header {
    display: flex;
    align-items: center;
    gap: 4px;
}

.nav-folder-toggle {
    background: none;
    border: none;
    color: #666;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.15s;
    flex-shrink: 0;
    width: 20px;
    height: 20px;
}

.nav-folder-toggle:hover {
    background: #222;
    color: #fff;
}

.nav-folder-toggle svg {
    transition: transform 0.2s;
}

.nav-folder-toggle.expanded svg {
    transform: rotate(90deg);
}

.nav-folder-toggle.no-children {
    visibility: hidden;
}

.nav-folder-link {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    color: #999;
    text-decoration: none;
    font-size: 13px;
    border-radius: 4px;
    transition: all 0.15s;
    flex: 1;
    min-width: 0;
}

.nav-folder-link:hover {
    background: #1a1a1a;
    color: #fff;
}

.nav-folder-link.router-link-active {
    background: #1a1a1a;
    color: #fff;
}

.nav-folder-icon {
    color: #6b7280;
    flex-shrink: 0;
}

.nav-folder-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.nav-folder-children {
    /* Children are indented via paddingLeft */
}

/* Nav experiment items */
.nav-experiment {
    padding: 5px 8px;
    margin-left: 24px;
    border-radius: 4px;
    border-left: none;
}

.nav-item-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.nav-item-icon.synchronized { color: #60a5fa; }
.nav-item-icon.collection { color: #fbbf24; }
.nav-item-icon.pdf { color: #f87171; }
.nav-item-icon.figures { color: #a78bfa; }
.nav-item-icon.code { color: #22d3ee; }
.nav-item-icon.interactive { color: #34d399; }

.nav-item-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Main content */
.main-content {
    flex: 1;
    padding: 20px 32px;
    overflow: auto;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    min-height: 0;
    transition: margin-left 0.3s ease;
    background: linear-gradient(90deg, #0a0a0a 0%, #111111 50%, #0a0a0a 100%);
}

.main-content > * {
    width: 100%;
}

/* Mobile overlay */
@media (max-width: 1023px) {
    .sidebar.open::before {
        content: '';
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: -1;
    }
}

/* Help button */
.help-btn {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #888;
    width: 38px;
    height: 38px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    flex-shrink: 0;
    margin-left: 8px;
}

.help-btn:hover {
    background: #222;
    color: #fff;
    border-color: #444;
}

/* Help modal */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    padding: 20px;
}

.modal-content {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 16px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid #333;
}

.modal-header h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
}

.modal-close {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    transition: all 0.2s;
}

.modal-close:hover {
    background: #222;
    color: #fff;
}

.modal-body {
    padding: 24px;
}

.help-intro {
    color: #aaa;
    line-height: 1.6;
    margin-bottom: 24px;
}

.modal-body h3 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
    color: #fff;
}

.help-types {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.help-type {
    background: #111;
    border: 1px solid #222;
    border-radius: 10px;
    padding: 16px;
}

.help-type p {
    margin: 8px 0 0;
    color: #888;
    font-size: 14px;
    line-height: 1.5;
}

.help-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
}

.help-type-badge.synchronized {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
}

.help-type-badge.collection {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
}

.help-type-badge.figures {
    background: rgba(168, 85, 247, 0.2);
    color: #c084fc;
}

.help-type-badge.pdf {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
}

.help-type-badge.code {
    background: rgba(6, 182, 212, 0.2);
    color: #22d3ee;
}

.help-type-badge.interactive {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
}
</style>
