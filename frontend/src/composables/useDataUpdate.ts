import type { DataUpdateActionResponse, DataUpdateStatusResponse } from '@/types/dataUpdate'
import { readonly, ref } from 'vue'
import { useStaticData } from '@/utils/gameData/staticData'

const status = ref<DataUpdateStatusResponse | null>(null)
const isChecking = ref(false)
const isDownloading = ref(false)

const successDialogVisible = ref(false)
const infoDialogVisible = ref(false)
const errorDialogVisible = ref(false)
const dialogMessage = ref('')

function setMessage(type: 'success' | 'info' | 'error', message: string) {
  dialogMessage.value = message
  successDialogVisible.value = type === 'success'
  infoDialogVisible.value = type === 'info'
  errorDialogVisible.value = type === 'error'
}

function dismissDialogs() {
  successDialogVisible.value = false
  infoDialogVisible.value = false
  errorDialogVisible.value = false
}

async function syncStaticDataIfNeeded(
  previous: DataUpdateStatusResponse | null,
  next: DataUpdateStatusResponse | null,
) {
  if (!next) {
    return
  }

  const sourceChanged = previous?.currentDataSource !== next.currentDataSource
  const appliedVersionChanged = previous?.appliedVersion !== next.appliedVersion

  if (!sourceChanged && !appliedVersionChanged) {
    return
  }

  const { fetchStaticData } = useStaticData()
  await fetchStaticData({ force: true })
}

async function fetchDataUpdateStatus() {
  try {
    const response = await fetch('/api/data_update/status')
    if (!response.ok) {
      throw new Error(`/api/data_update/status -> ${response.status}`)
    }

    const previous = status.value
    const next = (await response.json()) as DataUpdateStatusResponse
    status.value = next
    await syncStaticDataIfNeeded(previous, next)
    return status.value
  } catch (error) {
    console.error('Failed to fetch data update status:', error)
    return status.value
  }
}

async function checkWeaponDataUpdate(showLatestMessage: boolean = true) {
  isChecking.value = true
  try {
    const response = await fetch('/api/data_update/check', { method: 'POST' })
    const result = (await response.json()) as DataUpdateActionResponse
    const previous = status.value
    status.value = result.status
    await syncStaticDataIfNeeded(previous, result.status)

    if (result.status.lastError) {
      setMessage('error', result.message)
    } else if (result.status.updateAvailable || result.status.pendingApply || showLatestMessage) {
      setMessage('info', result.message)
    }

    return result
  } catch (error) {
    const message = error instanceof Error ? error.message : '检查武器数据更新失败。'
    setMessage('error', message)
    throw error
  } finally {
    isChecking.value = false
  }
}

async function downloadWeaponDataUpdate(showLatestMessage: boolean = true) {
  isDownloading.value = true
  try {
    const response = await fetch('/api/data_update/download', { method: 'POST' })
    const result = (await response.json()) as DataUpdateActionResponse
    const previous = status.value
    status.value = result.status
    await syncStaticDataIfNeeded(previous, result.status)

    if (result.status.lastError) {
      setMessage('error', result.message)
    } else if (result.applied) {
      setMessage('success', result.message)
    } else if (result.downloaded || showLatestMessage || result.status.pendingApply) {
      setMessage('info', result.message)
    }

    return result
  } catch (error) {
    const message = error instanceof Error ? error.message : '下载武器数据更新失败。'
    setMessage('error', message)
    throw error
  } finally {
    isDownloading.value = false
  }
}

export function useDataUpdate() {
  return {
    status: readonly(status),
    isChecking: readonly(isChecking),
    isDownloading: readonly(isDownloading),
    successDialogVisible,
    infoDialogVisible,
    errorDialogVisible,
    dialogMessage,
    fetchDataUpdateStatus,
    checkWeaponDataUpdate,
    downloadWeaponDataUpdate,
    dismissDialogs,
  }
}
