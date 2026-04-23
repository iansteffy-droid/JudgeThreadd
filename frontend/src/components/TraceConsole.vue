<script setup>
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps(['events', 'isEvaluating'])

const loadingMessages = [
  "Consulting the Book of Law...",
  "Analyzing citizen prompt for infractions...",
  "Cross-referencing Mega-City databases...",
  "Awaiting Council of Judges deliberation...",
  "Scanning for unauthorized hallucinations...",
  "Tek Division analyzing structural integrity...",
  "Psi Division detecting intent anomalies..."
]

const currentLoadingMessage = ref(loadingMessages[0])
let messageInterval = null

watch(() => props.isEvaluating, (isNowEvaluating) => {
  if (isNowEvaluating) {
    let i = 0
    currentLoadingMessage.value = loadingMessages[0] 
    
    messageInterval = setInterval(() => {
      i = (i + 1) % loadingMessages.length
      currentLoadingMessage.value = loadingMessages[i]
    }, 2000)
    
  } else {
    clearInterval(messageInterval)
  }
})

onUnmounted(() => {
  if (messageInterval) clearInterval(messageInterval)
})
</script>

<template>
  <div class="bg-black p-6 rounded-lg border border-gray-700 shadow-xl font-mono mb-8">
    
    <div class="flex items-center justify-between mb-4 border-b border-gray-800 pb-2">
      <div class="flex items-center gap-4">
        <h2 class="text-lg text-green-400">Live Execution Trace</h2>
        
        <span v-if="isEvaluating" class="text-sm text-yellow-500 italic animate-pulse">
          > {{ currentLoadingMessage }}
        </span>
      </div>
      
      <span v-if="isEvaluating" class="flex h-3 w-3 relative">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
      </span>
    </div>
    
    <div class="space-y-2 h-64 overflow-y-auto">
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
</template>