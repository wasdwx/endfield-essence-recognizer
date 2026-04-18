import type {
  EssenceInfo,
  EssenceListResponse,
  RarityColorResponse,
  WeaponInfo,
  WeaponListResponse,
  WeaponTypeInfo,
  WeaponTypeListResponse,
} from '@/types/staticData'
import { ref } from 'vue'

const weaponsMap = ref<Map<string, WeaponInfo>>(new Map())
const weaponTypes = ref<WeaponTypeInfo[]>([])
const essencesMap = ref<Map<string, EssenceInfo>>(new Map())
const rarityColors = ref<Record<number, string>>({})
const isLoaded = ref(false)
const isLoading = ref(false)

let inflightStaticDataRequest: Promise<boolean> | null = null

function sleep(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`${url} -> ${response.status}`)
  }
  return (await response.json()) as T
}

async function loadStaticDataOnce(): Promise<void> {
  const [weaponsRes, weaponTypesRes, essencesRes, rarityColorsRes] = await Promise.all([
    fetchJson<WeaponListResponse>('/api/static/weapons'),
    fetchJson<WeaponTypeListResponse>('/api/static/weapon_types'),
    fetchJson<EssenceListResponse>('/api/static/essences'),
    fetchJson<RarityColorResponse>('/api/static/rarity_colors'),
  ])

  weaponsMap.value = new Map(weaponsRes.weapons.map((w) => [w.id, w]))
  weaponTypes.value = weaponTypesRes.weaponTypes
  essencesMap.value = new Map(essencesRes.items.map((e) => [e.id, e]))
  rarityColors.value = rarityColorsRes.colors
  isLoaded.value = true
}

export interface FetchStaticDataOptions {
  force?: boolean
  maxAttempts?: number
}

async function fetchStaticData(options: FetchStaticDataOptions = {}): Promise<boolean> {
  const { force = false, maxAttempts = 5 } = options
  const wasLoaded = isLoaded.value

  if (isLoaded.value && !force) {
    return true
  }

  if (inflightStaticDataRequest) {
    return inflightStaticDataRequest
  }

  inflightStaticDataRequest = (async () => {
    isLoading.value = true
    let lastError: unknown = null

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        await loadStaticDataOnce()
        return true
      } catch (error) {
        lastError = error
        if (attempt < maxAttempts) {
          await sleep(attempt * 300)
        }
      }
    }

    console.error('Failed to fetch static data:', lastError)
    isLoaded.value = wasLoaded
    return false
  })()

  try {
    return await inflightStaticDataRequest
  } finally {
    inflightStaticDataRequest = null
    isLoading.value = false
  }
}

export function useStaticData() {
  return {
    weaponsMap,
    weaponTypes,
    essencesMap,
    rarityColors,
    isLoaded,
    isLoading,
    fetchStaticData,
  }
}
