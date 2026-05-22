<script setup>
import { computed } from 'vue'

const props = defineProps(['modelValue', 'isEvaluating', 'selectedProvider', 'selectedModel'])
const emit = defineEmits(['update:modelValue', 'update:selectedProvider', 'update:selectedModel', 'startEvaluation'])

const modelOptions = computed(() => {
  if (props.selectedProvider === 'ollama') {
    return [
      { value: 'qwen2.5:3b',   label: 'Qwen 2.5 · 3B' },
      { value: 'llama3.2:3b',  label: 'Llama 3.2 · 3B' },
      { value: 'phi3.5',       label: 'Phi-3.5 Mini · 3.8B' },
    ]
  }
  return [
    { value: 'llama-3.3-70b-versatile', label: 'Llama 3.3 · 70B (Versatile)' },
    { value: 'llama-3.1-8b-instant',    label: 'Llama 3.1 · 8B (Instant)' },
  ]
})

function onProviderChange(e) {
  const newProvider = e.target.value
  emit('update:selectedProvider', newProvider)
  const defaults = { groq: 'llama-3.3-70b-versatile', ollama: 'qwen2.5:3b' }
  emit('update:selectedModel', defaults[newProvider])
}
</script>

<template>
  <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl mb-8">
    <label class="block text-sm font-medium text-gray-300 mb-2">Subject Query</label>

    <!-- Query input row -->
    <div class="flex gap-4 mb-4">
      <input
        :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        @keyup.enter="$emit('startEvaluation')"
        type="text"
        class="flex-1 bg-gray-900 border border-gray-600 rounded px-4 py-2 text-white focus:outline-none focus:border-yellow-500"
        placeholder="Enter a question to evaluate..."
      />
      <button
        @click="$emit('startEvaluation')"
        :disabled="isEvaluating"
        class="bg-yellow-600 hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition-colors disabled:opacity-50"
      >
        {{ isEvaluating ? 'Evaluating...' : 'Dispatch Judges' }}
      </button>
    </div>

    <!-- Provider / model selector row -->
    <div class="flex gap-4 items-center">
      <div class="flex flex-col gap-1">
        <label class="text-xs text-gray-400 uppercase tracking-wider">Provider</label>
        <select
          :value="selectedProvider"
          @change="onProviderChange"
          class="bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-white text-sm focus:outline-none focus:border-yellow-500"
        >
          <option value="groq">Groq (Cloud)</option>
          <option value="ollama">Ollama (Local)</option>
        </select>
      </div>

      <div class="flex flex-col gap-1 flex-1">
        <label class="text-xs text-gray-400 uppercase tracking-wider">Model</label>
        <select
          :value="selectedModel"
          @change="$emit('update:selectedModel', $event.target.value)"
          class="bg-gray-900 border border-gray-600 rounded px-3 py-1.5 text-white text-sm focus:outline-none focus:border-yellow-500"
        >
          <option v-for="opt in modelOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <div class="flex flex-col gap-1 justify-end pb-0.5">
        <span class="text-xs text-gray-400 uppercase tracking-wider invisible">Status</span>
        <span
          :class="selectedProvider === 'ollama'
            ? 'bg-green-900 text-green-300 border border-green-700'
            : 'bg-blue-900 text-blue-300 border border-blue-700'"
          class="text-xs px-2 py-1.5 rounded font-mono"
        >
          {{ selectedProvider === 'ollama' ? '⬡ Local / Free' : '☁ Cloud API' }}
        </span>
      </div>
    </div>
  </div>
</template>
