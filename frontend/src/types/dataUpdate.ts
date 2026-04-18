export type DataSource = 'bundled' | 'override'

export interface DataUpdateStatusResponse {
  currentDataSource: DataSource
  appliedVersion: string | null
  pendingVersion: string | null
  lastCheckedVersion: string | null
  updateAvailable: boolean
  pendingApply: boolean
  lastCheckedAt: string | null
  lastDownloadedAt: string | null
  lastAppliedAt: string | null
  lastError: string | null
}

export interface DataUpdateActionResponse {
  status: DataUpdateStatusResponse
  message: string
  downloaded: boolean
  applied: boolean
}
