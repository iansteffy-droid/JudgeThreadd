<script setup>
import { ref, onMounted } from 'vue'
import { useEventSource } from '@vueuse/core'
import QueryInput from './components/QueryInput.vue'
import TraceConsole from './components/TraceConsole.vue'
import HistoryTable from './components/HistoryTable.vue'

const searchQuery = ref('What is a python tuple?')
const events = ref([])
const isEvaluating = ref(false)
const eventSource = ref(null)
const runHistory = ref([]) 

const fetchHistory = async () => {
  try {
    const res = await fetch('http://127.0.0.1:8000/history')
    const data = await res.json()
    if (!data.error) runHistory.value = data
  } catch (err) {
    console.error("Failed to fetch history", err)
  }
}

onMounted(fetchHistory)

const startEvaluation = () => {
  if (!searchQuery.value) return;
  
  events.value = []
  isEvaluating.value = true

  if (eventSource.value) eventSource.value.close()

  const url = `http://127.0.0.1:8000/stream_telemetry?question=${encodeURIComponent(searchQuery.value)}`
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
            close()
            setTimeout(fetchHistory, 500) 
          }
        } catch (e) {
          console.error("Failed to parse event:", newData)
        }
      }
    })
  })
}
</script>

<template>
  <div class="min-h-screen bg-gray-900 text-gray-100 p-8 font-sans">
    <header class="mb-8">
      <h1 class="text-3xl font-bold text-yellow-400 tracking-wider uppercase">Mega-City One: Grand Hall Telemetry</h1>
      <p class="text-gray-400 mt-2">Live Agentic Observability Pipeline</p>
    </header>

    <QueryInput v-model="searchQuery" :isEvaluating="isEvaluating" @startEvaluation="startEvaluation" />
    <TraceConsole :events="events" :isEvaluating="isEvaluating" />
    <HistoryTable :runHistory="runHistory" />
  </div>
</template>