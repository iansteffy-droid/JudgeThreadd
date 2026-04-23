<script setup>
defineProps(['runHistory'])
</script>

<template>
  <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl">
    <h2 class="text-xl font-bold text-yellow-400 mb-4 border-b border-gray-700 pb-2">Archived Council Verdicts (Supabase)</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse">
        <thead>
          <tr class="bg-gray-900 text-gray-400 text-sm uppercase">
            <th class="p-3 border-b border-gray-700">Run ID</th>
            <th class="p-3 border-b border-gray-700 w-1/3">Query</th>
            <th class="p-3 border-b border-gray-700 text-center">Chief Judge Score</th>
            <th class="p-3 border-b border-gray-700 text-center">Status</th>
            <th class="p-3 border-b border-gray-700 text-right">Timestamp</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runHistory" :key="run.id"
              :class="['border-b border-gray-700 transition-colors', run.chief_score < 3 ? 'bg-red-900/40 text-red-200 border-red-500/50' : 'hover:bg-gray-700/50']">
            <td class="p-3 font-mono text-xs text-gray-500">{{ run.id }}</td>
            <td class="p-3 font-medium">{{ run.question }}</td>
            <td class="p-3 text-center font-bold" :class="run.chief_score < 3 ? 'text-red-400' : 'text-green-400'">{{ run.chief_score }}/5</td>
            <td class="p-3 text-center">
              <span v-if="run.chief_score >= 3" class="bg-green-900/50 text-green-400 px-2 py-1 rounded text-xs">APPROVED</span>
              <span v-else class="bg-red-900/80 text-red-300 px-2 py-1 rounded text-xs font-bold animate-pulse">DRIFT DETECTED</span>
            </td>
            <td class="p-3 text-right text-sm text-gray-400">{{ run.created_at }}</td>
          </tr>
          <tr v-if="runHistory.length === 0">
            <td colspan="5" class="p-6 text-center text-gray-500 italic">No historical runs retrieved.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>