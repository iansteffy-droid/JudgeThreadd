<script setup>
import { ref, onMounted } from 'vue'
import { useEventSource } from '@vueuse/core'
import QueryInput from './components/QueryInput.vue'
import TraceConsole from './components/TraceConsole.vue'
import HistoryTable from './components/HistoryTable.vue'

const searchQuery = ref('What is a python tuple?')
const selectedProvider = ref('groq')
const selectedModel = ref('llama-3.3-70b-versatile')
const events = ref([])
const isEvaluating = ref(false)
const isBatchEvaluating = ref(false)
const isIngesting = ref(false)
const eventSource = ref(null)
const reports = ref([])
const reportContent = ref(null)
const datasetFile = ref(null)

const fetchReports = async () => {
  try {
    const res = await fetch('http://127.0.0.1:8000/reports')
    reports.value = await res.json()
  } catch (err) {
    console.error("Failed to fetch reports", err)
  }
}

const openReport = async (filename) => {
  try {
    const res = await fetch(`http://127.0.0.1:8000/reports/${encodeURIComponent(filename)}`)
    reportContent.value = await res.text()
  } catch (err) {
    console.error("Failed to load report", err)
  }
}

onMounted(fetchReports)

const openSseStream = (url) => {
  if (eventSource.value) eventSource.value.close()
  const { data, close } = useEventSource(url)
  eventSource.value = { close }
  import('vue').then(({ watch }) => {
    watch(data, (newData) => {
      if (newData) {
        try {
          const parsedEvent = JSON.parse(newData)
          events.value.push(parsedEvent)
          if (parsedEvent.event === 'complete' || parsedEvent.event === 'error') {
            isEvaluating.value = false
            isBatchEvaluating.value = false
            isIngesting.value = false
            close()
            fetchReports()
          }
        } catch (e) {
          console.error("Failed to parse event:", newData)
        }
      }
    })
  })
}

const startEvaluation = () => {
  if (!searchQuery.value) return
  events.value = []
  reportContent.value = null
  isEvaluating.value = true
  const url = `http://127.0.0.1:8000/stream_telemetry?question=${encodeURIComponent(searchQuery.value)}&provider=${selectedProvider.value}&model=${encodeURIComponent(selectedModel.value)}`
  openSseStream(url)
}

const startIngestion = (pdfKey) => {
  events.value = []
  reportContent.value = null
  isIngesting.value = true
  const url = `http://127.0.0.1:8000/stream_ingest?pdf_key=${encodeURIComponent(pdfKey)}`
  openSseStream(url)
}

const startDatasetEvaluation = async () => {
  events.value = []
  reportContent.value = null
  isBatchEvaluating.value = true

  let url
  if (datasetFile.value) {
    try {
      const form = new FormData()
      form.append('file', datasetFile.value)
      const res = await fetch('http://127.0.0.1:8000/upload_dataset', { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json()
        events.value.push({ event: 'error', message: `Upload failed: ${err.detail}` })
        isBatchEvaluating.value = false
        return
      }
      const { dataset_id } = await res.json()
      url = `http://127.0.0.1:8000/stream_dataset_evaluation?use_default=false&dataset_id=${dataset_id}&provider=${selectedProvider.value}&model=${encodeURIComponent(selectedModel.value)}`
    } catch (e) {
      events.value.push({ event: 'error', message: `Upload error: ${e.message}` })
      isBatchEvaluating.value = false
      return
    }
  } else {
    url = `http://127.0.0.1:8000/stream_dataset_evaluation?use_default=true&provider=${selectedProvider.value}&model=${encodeURIComponent(selectedModel.value)}`
  }

  openSseStream(url)
}
</script>

<template>
  <div class="min-h-screen bg-gray-900 text-gray-100 p-8 font-sans">
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-yellow-400 tracking-wider uppercase">Mega-City One: Grand Hall Telemetry</h1>
      <p class="text-gray-400 mt-2">Live Agentic Observability Pipeline</p>
    </header>

    <QueryInput
      v-model="searchQuery"
      v-model:selectedProvider="selectedProvider"
      v-model:selectedModel="selectedModel"
      :isEvaluating="isEvaluating"
      :isBatchEvaluating="isBatchEvaluating"
      :isIngesting="isIngesting"
      @startEvaluation="startEvaluation"
      @startDatasetEvaluation="startDatasetEvaluation"
      @startIngestion="startIngestion"
      @update:datasetFile="datasetFile = $event"
    />
    <TraceConsole :events="events" :isEvaluating="isEvaluating || isBatchEvaluating" :reportContent="reportContent" />
    <HistoryTable :reports="reports" @openReport="openReport" />
  </div>
</template>
