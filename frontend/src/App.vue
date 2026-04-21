<script setup>
import { ref } from 'vue'
import { useEventSource } from '@vueuse/core'

const searchQuery = ref('What is a python tuple?')
const events = ref([])
const isEvaluating = ref(false)
const eventSource = ref(null)

const startEvaluation = () => {
  if (!searchQuery.value) return;
  
  events.value = []
  isEvaluating.value = true

  if (eventSource.value) {
    eventSource.value.close()
  }

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

    <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl mb-8">
      <label class="block text-sm font-medium text-gray-300 mb-2">Subject Query</label>
      <div class="flex gap-4">
        <input 
          v-model="searchQuery" 
          type="text" 
          class="flex-1 bg-gray-900 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-yellow-500"
          placeholder="Enter a question to evaluate..."
          @keyup.enter="startEvaluation"
        />
        <button 
          @click="startEvaluation" 
          :disabled="isEvaluating"
          class="bg-yellow-600 hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition-colors disabled:opacity-50"
        >
          {{ isEvaluating ? 'Evaluating...' : 'Dispatch Judges' }}
        </button>
      </div>
    </div>

    <div class="bg-black p-6 rounded-lg border border-gray-700 shadow-xl font-mono">
      <div class="flex items-center justify-between mb-4 border-b border-gray-800 pb-2">
        <h2 class="text-lg text-green-400">Live Execution Trace</h2>
        <span v-if="isEvaluating" class="flex h-3 w-3 relative">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
        </span>
      </div>
      
      <div class="space-y-2 h-96 overflow-y-auto">
        <div v-if="events.length === 0" class="text-gray-600 italic">Awaiting dispatch orders...</div>
        
        <div v-for="(evt, idx) in events" :key="idx" class="text-sm">
          <span class="text-gray-500">[{{ new Date().toLocaleTimeString() }}]</span> 
          
          <span v-if="evt.event === 'info'" class="text-blue-400 ml-2">{{ evt.message }}</span>
          <span v-else-if="evt.event === 'node_start'" class="text-yellow-300 ml-2">{{ evt.message }}</span>
          <span v-else-if="evt.event === 'node_end'" class="text-green-300 ml-2">{{ evt.message }}</span>
          <span v-else-if="evt.event === 'error'" class="text-red-500 ml-2 font-bold">{{ evt.message }}</span>
          <span v-else-if="evt.event === 'complete'" class="text-white ml-2 font-bold bg-green-900 px-2 rounded">{{ evt.message }}</span>
          <span v-else class="text-gray-300 ml-2">{{ evt.message }}</span>
        </div>
      </div>
    </div>
  </div>
</template>