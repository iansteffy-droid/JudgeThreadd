<script setup>
import { ref, computed } from 'vue'
import ModelSelector from './ModelSelector.vue'

const props = defineProps(['modelValue', 'isEvaluating', 'isBatchEvaluating', 'selectedProvider', 'selectedModel'])
const emit = defineEmits(['update:modelValue', 'update:selectedProvider', 'update:selectedModel', 'startEvaluation', 'startDatasetEvaluation', 'update:datasetFile'])

const selectedFile = ref(null)
const selectedFileName = computed(() => selectedFile.value?.name ?? 'golden_dataset.json')
const anyEvaluating = computed(() => props.isEvaluating || props.isBatchEvaluating)

function onFileChange(e) {
  selectedFile.value = e.target.files[0] ?? null
  emit('update:datasetFile', selectedFile.value)
}
</script>

<template>
  <div class="space-y-4 mb-8">
    <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl">
      <label class="block text-sm font-medium text-gray-300 mb-2">Subject Query</label>
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
          :disabled="anyEvaluating"
          class="bg-yellow-600 hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition-colors disabled:opacity-50"
        >
          {{ isEvaluating ? 'Evaluating...' : 'Dispatch Judges' }}
        </button>
      </div>
    </div>

    <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl">
      <label class="block text-sm font-medium text-gray-300 mb-2">Golden Dataset</label>
      <div class="flex gap-4 items-center">
        <label class="flex-1 flex items-center gap-3 bg-gray-900 border border-gray-600 rounded px-4 py-2 cursor-pointer hover:border-yellow-500 transition-colors">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          <span class="text-sm truncate" :class="selectedFile ? 'text-white' : 'text-gray-400'">
            {{ selectedFileName }}
          </span>
          <input type="file" accept=".json" class="hidden" @change="onFileChange" />
        </label>
        <button
          @click="$emit('startDatasetEvaluation')"
          :disabled="anyEvaluating"
          class="bg-yellow-600 hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition-colors disabled:opacity-50 whitespace-nowrap"
        >
          {{ isBatchEvaluating ? 'Evaluating...' : 'Dispatch Judges on Dataset' }}
        </button>
      </div>
      <ModelSelector
        :selectedProvider="selectedProvider"
        :selectedModel="selectedModel"
        @update:selectedProvider="$emit('update:selectedProvider', $event)"
        @update:selectedModel="$emit('update:selectedModel', $event)"
      />
      <p class="mt-2 text-xs text-gray-500">
        Upload a JSON file matching the golden dataset schema, or leave blank to use the default <span class="text-gray-400">golden_dataset.json</span>.
      </p>
    </div>
  </div>
</template>
