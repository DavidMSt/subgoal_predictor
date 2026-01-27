import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import ExperimentList from './components/ExperimentList.vue'
import ExperimentViewer from './components/ExperimentViewer.vue'
import FolderView from './components/FolderView.vue'
import PDFViewer from './components/PDFViewer.vue'
import FigureViewer from './components/FigureViewer.vue'
import CodeViewer from './components/CodeViewer.vue'

const routes = [
    { path: '/', component: ExperimentList },
    { path: '/folder/:id', component: FolderView, props: true },
    { path: '/experiment/:id', component: ExperimentViewer, props: true },
    { path: '/pdf/:id', component: PDFViewer, props: true },
    { path: '/figures/:id', component: FigureViewer, props: true },
    { path: '/code/:id', component: CodeViewer, props: true }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')
