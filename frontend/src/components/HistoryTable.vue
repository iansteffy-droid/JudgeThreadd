<script setup>
defineProps(['reports'])
defineEmits(['openReport'])
</script>

<template>
  <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl">
    <h2 class="text-xl font-bold text-yellow-400 mb-4 border-b border-gray-700 pb-2">Archived Council Verdicts</h2>
    <div class="space-y-1 max-h-64 overflow-y-auto">
      <div
        v-for="report in reports"
        :key="report.filename"
        class="flex items-center justify-between px-3 py-2 rounded cursor-pointer hover:bg-gray-700/60 transition-colors group"
        @click="$emit('openReport', report.filename)"
      >
        <span class="text-green-400 font-mono text-sm group-hover:text-green-300">{{ report.display }}</span>
        <span class="text-gray-500 font-mono text-xs truncate ml-4">{{ report.filename }}</span>
      </div>
      <div v-if="reports.length === 0" class="px-3 py-6 text-center text-gray-500 italic">
        No reports found in data/reports/.
      </div>
    </div>
  </div>
</template>
