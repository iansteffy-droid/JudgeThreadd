<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps(['isIngesting'])
const emit = defineEmits(['startIngestion'])

const selectedFile = ref(null)
const activeContentName = ref('thinkpython.pdf')
const isUploading = ref(false)
const uploadError = ref('')

const selectedFileName = computed(() => selectedFile.value?.name ?? 'No file selected')
const busy = computed(() => props.isIngesting || isUploading.value)

watch(() => props.isIngesting, (ingesting, wasIngesting) => {
  if (wasIngesting && !ingesting) {
    // Stream ended — update the active name and reset selection
    if (!uploadError.value && selectedFile.value) {
      activeContentName.value = selectedFile.value.name
    }
    selectedFile.value = null
    isUploading.value = false
  }
})

function onFileChange(e) {
  selectedFile.value = e.target.files[0] ?? null
  uploadError.value = ''
}

async function ingestContent() {
  if (!selectedFile.value || busy.value) return
  uploadError.value = ''
  isUploading.value = true
  try {
    const form = new FormData()
    form.append('file', selectedFile.value)
    const res = await fetch('http://127.0.0.1:8000/upload_pdf', { method: 'POST', body: form })
    if (!res.ok) {
      const err = await res.json()
      uploadError.value = err.detail ?? 'Upload failed.'
      isUploading.value = false
      return
    }
    const { pdf_key } = await res.json()
    isUploading.value = false
    emit('startIngestion', pdf_key)
  } catch (e) {
    uploadError.value = `Upload error: ${e.message}`
    isUploading.value = false
  }
}
</script>

<template>
  <div class="bg-gray-800 p-6 rounded-lg border border-gray-700 shadow-xl">
    <div class="flex items-center justify-between mb-3">
      <label class="block text-sm font-medium text-gray-300">Test Content</label>
      <span class="text-xs text-gray-400 bg-gray-900 border border-gray-700 rounded px-2 py-1">
        Active: <span class="text-yellow-400 font-medium">{{ activeContentName }}</span>
      </span>
    </div>

    <div class="flex gap-4 items-center">
      <label class="flex-1 flex items-center gap-3 bg-gray-900 border border-gray-600 rounded px-4 py-2 cursor-pointer hover:border-yellow-500 transition-colors" :class="{ 'opacity-50 cursor-not-allowed': busy }">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <span class="text-sm truncate" :class="selectedFile ? 'text-white' : 'text-gray-400'">
          {{ isUploading ? 'Uploading...' : selectedFileName }}
        </span>
        <input type="file" accept=".pdf" class="hidden" :disabled="busy" @change="onFileChange" />
      </label>

      <button
        v-if="selectedFile"
        @click="ingestContent"
        :disabled="busy"
        class="bg-yellow-600 hover:bg-yellow-500 text-black font-bold py-2 px-6 rounded transition-colors disabled:opacity-50 whitespace-nowrap"
      >
        {{ isIngesting ? 'Ingesting...' : isUploading ? 'Uploading...' : 'Ingest Content' }}
      </button>
    </div>

    <p v-if="uploadError" class="mt-2 text-xs text-red-400">{{ uploadError }}</p>
    <p v-else class="mt-2 text-xs text-gray-500">
      Upload a PDF to replace the active test content. Ingestion re-indexes the document in Qdrant Cloud.
    </p>
  </div>
</template>
