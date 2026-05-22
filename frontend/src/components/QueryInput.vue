<script setup>
import ModelSelector from './ModelSelector.vue'

defineProps(['modelValue', 'isEvaluating', 'selectedProvider', 'selectedModel'])
defineEmits(['update:modelValue', 'update:selectedProvider', 'update:selectedModel', 'startEvaluation'])
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

    <!-- Provider / model selector -->
    <ModelSelector
      :selectedProvider="selectedProvider"
      :selectedModel="selectedModel"
      @update:selectedProvider="$emit('update:selectedProvider', $event)"
      @update:selectedModel="$emit('update:selectedModel', $event)"
    />
  </div>
</template>
