<template>
  <v-container>
    <v-expansion-panels color="primary-darken-1" :model-value="[0, 1, 2]" multiple>
      <v-expansion-panel :value="0">
        <v-expansion-panel-title>武器基质预设</v-expansion-panel-title>
        <v-expansion-panel-text>
          <h2>将以下武器所对应的基质视为宝藏</h2>
          <h3>按稀有度快捷选择</h3>
          <div class="d-flex flex-row flex-wrap gc-4">
            <v-checkbox
              v-for="rarity in [3, 4, 5, 6]"
              :key="rarity"
              :color="rarityColors[rarity]"
              density="compact"
              hide-details
              :indeterminate="isRarityPartiallySelected(rarity)"
              :model-value="isRarityAllSelected(rarity)"
              @click="raritySelectAll(rarity, !isRarityAllSelected(rarity))"
            >
              <template #label>
                <span :style="{ color: rarityColors[rarity] }">{{ rarity }}★</span>
              </template>
            </v-checkbox>
          </div>
          <v-divider class="my-4" />
          <template v-for="weaponType in weaponTypes" :key="weaponType.id">
            <h3>
              <v-checkbox
                density="compact"
                hide-details
                :indeterminate="isTypePartiallySelected(weaponType.id)"
                :model-value="isTypeAllSelected(weaponType.id)"
                @click="typeSelectAll(weaponType.id, !isTypeAllSelected(weaponType.id))"
              >
                <template #prepend>
                  <img
                    :alt="weaponType.name"
                    class="group-icon me-2"
                    :src="weaponType.iconUrl"
                    :style="{
                      filter: theme.current.value.dark ? 'none' : 'invert(1)',
                    }"
                  />
                  <h3 class="ma-0">{{ weaponType.name }}</h3>
                </template>
              </v-checkbox>
            </h3>
            <div class="weapon-grid">
              <div
                v-for="weaponId in weaponType.weaponIds"
                :key="weaponId"
                class="d-flex flex-column align-center"
                :class="{
                  'opacity-50': !selectedWeaponIds.includes(weaponId),
                }"
              >
                <div
                  class="weapon-item"
                  @click="
                    selectedWeaponIds.includes(weaponId)
                      ? selectedWeaponIds.splice(selectedWeaponIds.indexOf(weaponId), 1)
                      : selectedWeaponIds.push(weaponId)
                  "
                >
                  <v-badge
                    v-if="weaponEssenceCounts[weaponId]"
                    color="primary"
                    :content="weaponEssenceCounts[weaponId]"
                    location="top end"
                  >
                    <item-icon :item-id="weaponId" show-item-name />
                  </v-badge>
                  <item-icon v-else :item-id="weaponId" show-item-name />
                </div>
                <v-checkbox-btn
                  v-model="selectedWeaponIds"
                  color="primary"
                  density="comfortable"
                  :value="weaponId"
                />
                <v-tooltip activator="parent" location="bottom">
                  {{ getWeaponStatsDescription(weaponId) }}
                </v-tooltip>
              </div>
            </div>
          </template>
        </v-expansion-panel-text>
      </v-expansion-panel>

      <v-expansion-panel :value="1">
        <v-expansion-panel-title>自定义宝藏基质</v-expansion-panel-title>
        <v-expansion-panel-text>
          <h2>如果基质的某个词条初始属性较高，也将其视为宝藏</h2>
          <v-row align="center" class="my-4">
            <v-col cols="12" md="4">
              <v-switch
                v-model="highLevelTreasureEnabled"
                color="primary"
                density="comfortable"
                hide-details
                label="启用高等级基质属性词条判定"
              />
            </v-col>
            <v-col cols="12" md="8">
              <v-slider
                v-model="highLevelTreasureAttributeThreshold"
                color="primary"
                :disabled="!highLevelTreasureEnabled"
                label="基础属性"
                :max="6"
                :min="1"
                show-ticks="always"
                :step="1"
                thumb-label
                tick-size="4"
                :ticks="{ 1: '+1', 2: '+2', 3: '+3', 4: '+4', 5: '+5', 6: '+6' }"
              >
                <template #thumb-label="{ modelValue }">+{{ modelValue }}</template>
              </v-slider>
              <v-slider
                v-model="highLevelTreasureSecondaryThreshold"
                color="primary"
                :disabled="!highLevelTreasureEnabled"
                label="附加属性"
                :max="6"
                :min="1"
                show-ticks="always"
                :step="1"
                thumb-label
                tick-size="4"
                :ticks="{ 1: '+1', 2: '+2', 3: '+3', 4: '+4', 5: '+5', 6: '+6' }"
              >
                <template #thumb-label="{ modelValue }">+{{ modelValue }}</template>
              </v-slider>
              <v-slider
                v-model="highLevelTreasureSkillThreshold"
                color="primary"
                :disabled="!highLevelTreasureEnabled"
                label="技能属性"
                :max="3"
                :min="1"
                show-ticks="always"
                :step="1"
                thumb-label
                tick-size="4"
                :ticks="{ 1: '+1', 2: '+2', 3: '+3' }"
              >
                <template #thumb-label="{ modelValue }">+{{ modelValue }}</template>
              </v-slider>
              <v-alert
                v-if="highLevelTreasureEnabled"
                border="start"
                class="mt-2"
                type="info"
                variant="tonal"
              >
                当前效果：如果基质的基础属性等级 ≥{{
                  highLevelTreasureAttributeThreshold
                }}，或者附加属性等级 ≥{{ highLevelTreasureSecondaryThreshold }}，或者技能属性等级 ≥{{
                  highLevelTreasureSkillThreshold
                }}，则也将其视为宝藏。
              </v-alert>
            </v-col>
          </v-row>
          <v-divider class="my-4" />
          <h2>额外将以下属性的基质视为宝藏</h2>
          <v-row v-for="(essenceStat, index) in treasureEssenceStats" :key="index" align="center">
            <v-col cols="12" md="3" sm="6">
              <v-select
                v-model="essenceStat.attribute"
                density="comfortable"
                hide-details
                :items="
                  allAttributeStats.map((gemTermId) => ({
                    title: getGemTagName(gemTermId),
                    value: gemTermId,
                  }))
                "
                label="基础属性"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="3" sm="6">
              <v-select
                v-model="essenceStat.secondary"
                density="comfortable"
                hide-details
                :items="
                  allSecondaryStats.map((gemTermId) => ({
                    title: getGemTagName(gemTermId),
                    value: gemTermId,
                  }))
                "
                label="附加属性"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="3" sm="6">
              <v-select
                v-model="essenceStat.skill"
                density="comfortable"
                hide-details
                :items="
                  allSkillStats.map((gemTermId) => ({
                    title: getGemTagName(gemTermId),
                    value: gemTermId,
                  }))
                "
                label="技能属性"
                variant="outlined"
              />
            </v-col>
            <v-col cols="12" md="3" sm="6">
              <v-btn
                color="primary"
                icon="mdi-plus"
                variant="text"
                @click="
                  treasureEssenceStats.splice(index, 0, {
                    attribute: null,
                    secondary: null,
                    skill: null,
                  })
                "
              />
              <v-btn
                color="error"
                icon="mdi-delete"
                variant="text"
                @click="treasureEssenceStats.splice(index, 1)"
              />
              <v-btn
                :disabled="index === 0"
                icon="mdi-chevron-up"
                variant="text"
                @click="
                  () => {
                    const stat = treasureEssenceStats.splice(index, 1)[0]!
                    treasureEssenceStats.splice(index - 1, 0, stat)
                  }
                "
              />
              <v-btn
                :disabled="index === treasureEssenceStats.length - 1"
                icon="mdi-chevron-down"
                variant="text"
                @click="
                  () => {
                    const stat = treasureEssenceStats.splice(index, 1)[0]!
                    treasureEssenceStats.splice(index + 1, 0, stat)
                  }
                "
              />
            </v-col>
          </v-row>
          <v-row v-if="treasureEssenceStats.length === 0" class="my-4">
            <v-col cols="12" md="9" sm="6">
              <v-btn
                color="primary"
                prepend-icon="mdi-plus"
                @click="
                  treasureEssenceStats.push({ attribute: null, secondary: null, skill: null })
                "
              >
                添加自定义宝藏基质
              </v-btn>
            </v-col>
          </v-row>
          <v-row v-else>
            <v-col cols="12" md="9" sm="6" />
            <v-col cols="12" md="3" sm="6">
              <v-btn
                color="primary"
                icon="mdi-plus"
                variant="text"
                @click="
                  treasureEssenceStats.push({ attribute: null, secondary: null, skill: null })
                "
              />
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>

      <v-expansion-panel :value="2">
        <v-expansion-panel-title>操作设置</v-expansion-panel-title>
        <v-expansion-panel-text>
          <h2>界面设置</h2>
          <v-row class="my-4">
            <v-col cols="12" md="6">
              <v-switch
                v-model="statusPollingEnabled"
                color="primary"
                density="comfortable"
                hide-details
                label="启用轮询状态更新"
                @update:model-value="onStatusPollingToggle"
              />
              <v-alert border="start" class="mt-2" type="info" variant="tonal">
                启用后，前端会轮询更新扫描状态、武器统计和武器数据更新状态；禁用后可减少请求频率。
              </v-alert>
            </v-col>
          </v-row>

          <v-divider class="my-4" />
          <h2>武器数据热更新</h2>
          <v-alert border="start" class="mb-4" type="info" variant="tonal">
            武器数据会从 GitHub Pages 清单读取，只覆盖武器相关静态数据，不影响程序本体更新逻辑。
          </v-alert>
          <v-card variant="outlined">
            <v-card-text class="d-flex flex-column ga-2">
              <div>当前数据来源：{{ dataUpdateSourceText }}</div>
              <div>已应用版本：{{ dataUpdateStatus?.appliedVersion || '暂无' }}</div>
              <div v-if="dataUpdateStatus?.pendingVersion">
                待应用版本：{{ dataUpdateStatus.pendingVersion }}
              </div>
              <div>最近检查版本：{{ dataUpdateStatus?.lastCheckedVersion || '暂无' }}</div>
              <div>最近检查时间：{{ formatDataUpdateTime(dataUpdateStatus?.lastCheckedAt) }}</div>
              <div>最近下载时间：{{ formatDataUpdateTime(dataUpdateStatus?.lastDownloadedAt) }}</div>
              <div>最近应用时间：{{ formatDataUpdateTime(dataUpdateStatus?.lastAppliedAt) }}</div>
              <div v-if="dataUpdateStatus?.pendingApply" class="text-warning">
                当前扫描正在进行中，更新将在扫描结束后自动应用。
              </div>
              <div v-else-if="dataUpdateStatus?.updateAvailable" class="text-info">
                已检测到新的武器数据版本。
              </div>
              <div v-if="dataUpdateStatus?.lastError" class="text-error">
                最近错误：{{ dataUpdateStatus.lastError }}
              </div>
            </v-card-text>
            <v-card-actions>
              <v-btn
                color="primary"
                :loading="isCheckingDataUpdate"
                prepend-icon="mdi-magnify"
                variant="text"
                @click="checkWeaponDataUpdate()"
              >
                检查武器数据更新
              </v-btn>
              <v-btn
                color="primary"
                :loading="isDownloadingDataUpdate"
                prepend-icon="mdi-download"
                variant="elevated"
                @click="downloadWeaponDataUpdate()"
              >
                下载并应用
              </v-btn>
            </v-card-actions>
          </v-card>

          <v-divider class="my-4" />
          <h2>声音提示</h2>
          <v-row class="my-4">
            <v-col cols="12" md="6">
              <v-switch
                v-model="enableSound"
                color="primary"
                density="comfortable"
                hide-details
                label="启用扫描启停提示音"
              />
              <v-alert border="start" class="mt-2" type="info" variant="tonal">
                启用后，开始扫描和停止扫描时会播放提示音。
              </v-alert>
            </v-col>
          </v-row>

          <v-divider class="my-4" />
          <h2>扫描时自动翻页</h2>
          <v-alert border="start" class="mb-4" type="info" variant="tonal">
            启用后，扫描完当前页会按所选方式自动翻页继续扫描，直到滚动条到达底部。
          </v-alert>
          <v-switch
            v-model="autoPageFlip"
            color="primary"
            density="comfortable"
            hide-details
            label="启用自动翻页扫描"
          />
          <v-radio-group
            v-model="pageFlipMode"
            color="primary"
            density="comfortable"
            :disabled="!autoPageFlip"
            inline
          >
            <v-radio label="滚轮" value="wheel" />
            <v-radio label="拖拽" value="drag" />
          </v-radio-group>

          <v-divider class="my-4" />
          <h2>遇到非无瑕基质（即非橙色基质）时，该如何操作？</h2>
          <v-radio-group v-model="nonFiveStarBehavior" color="primary" density="comfortable" inline>
            <v-radio label="跳过当前项" value="skip" />
            <v-radio label="结束本次扫描" value="stop_scan" />
            <v-radio label="继续处理（按无瑕基质逻辑）" value="process" />
          </v-radio-group>

          <v-divider class="my-4" />
          <h2>遇到宝藏基质或者养成材料时，该如何操作？</h2>
          <v-alert border="start" class="mb-4" type="info" variant="tonal">
            “宝藏基质”和“养成材料”仅为分类简称，不是宝藏的基质都会被视作养成材料。
          </v-alert>
          <v-row>
            <v-col cols="12" md="6">
              <h3>对于<span class="text-success">宝藏基质</span>，我们</h3>
              <v-radio-group v-model="treasureAction" color="primary" density="comfortable">
                <v-radio label="不去动它" value="keep" />
                <v-radio label="把它锁上" value="lock" />
                <v-radio disabled label="把它标记为弃用" value="deprecate" />
                <v-radio label="如果锁着，则解锁" value="unlock" />
                <v-radio label="如果已标记为弃用，则取消弃用" value="undeprecate" />
                <v-radio label="解锁且取消弃用" value="unlock_and_undeprecate" />
                <v-radio disabled label="如果没有上锁，则弃用" value="deprecate_if_not_locked" />
                <v-radio label="如果没有弃用，则上锁" value="lock_if_not_deprecated" />
              </v-radio-group>
            </v-col>
            <v-col cols="12" md="6">
              <h3>对于<span class="text-error">养成材料</span>，我们</h3>
              <v-radio-group v-model="trashAction" color="primary" density="comfortable">
                <v-radio label="不去动它" value="keep" />
                <v-radio label="把它锁上" value="lock" />
                <v-radio label="把它标记为弃用" value="deprecate" />
                <v-radio label="如果锁着，则解锁" value="unlock" />
                <v-radio label="如果已标记为弃用，则取消弃用" value="undeprecate" />
                <v-radio label="解锁且取消弃用" value="unlock_and_undeprecate" />
                <v-radio label="如果没有上锁，则弃用" value="deprecate_if_not_locked" />
                <v-radio label="如果没有弃用，则上锁" value="lock_if_not_deprecated" />
              </v-radio-group>
            </v-col>
          </v-row>

          <v-divider class="my-4" />
          <h2>程序更新设置</h2>
          <v-alert border="start" class="mb-4" type="info" variant="tonal">
            程序版本信息会从 GitHub Pages 清单读取，安装包仍通过 GitHub Releases 与镜像下载。
          </v-alert>
          <v-row>
            <v-col cols="12" md="6">
              <v-select
                v-model="updateMirror"
                density="comfortable"
                hide-details
                :items="mirrorOptions"
                label="下载镜像源"
                variant="outlined"
              >
                <template #append-inner>
                  <v-tooltip location="top">
                    <template #activator="{ props }">
                      <v-icon v-bind="props" size="small">mdi-information-outline</v-icon>
                    </template>
                    <span>{{ selectedMirrorName }}</span>
                  </v-tooltip>
                </template>
              </v-select>
            </v-col>
            <v-col cols="12" md="6">
              <div class="d-flex align-center">
                <v-text-field
                  v-model="updateProxyPort"
                  class="flex-grow-1"
                  density="comfortable"
                  :disabled="!updateProxyEnabled"
                  hide-details
                  label="代理端口"
                  placeholder="7890"
                  type="number"
                  variant="outlined"
                />
                <v-switch
                  v-model="updateProxyEnabled"
                  class="ms-4 flex-shrink-0"
                  color="primary"
                  density="comfortable"
                  hide-details
                  label="使用代理"
                />
              </div>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <v-card class="mt-4" variant="outlined">
      <v-card-text class="text-center text-caption text-medium-emphasis">
        配置版本: v{{ configVersion }}
      </v-card-text>
    </v-card>
  </v-container>

  <v-snackbar v-model="successDialogVisible" color="success">
    {{ dialogMessage }}
    <template #actions>
      <v-btn variant="text" @click="dismissDialogs">关闭</v-btn>
    </template>
  </v-snackbar>

  <v-snackbar v-model="infoDialogVisible" color="info">
    {{ dialogMessage }}
    <template #actions>
      <v-btn variant="text" @click="dismissDialogs">关闭</v-btn>
    </template>
  </v-snackbar>

  <v-snackbar v-model="errorDialogVisible" color="error">
    {{ dialogMessage }}
    <template #actions>
      <v-btn variant="text" @click="dismissDialogs">关闭</v-btn>
    </template>
  </v-snackbar>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useTheme } from 'vuetify'
import ItemIcon from '@/components/ItemIcon.vue'
import { useDataUpdate } from '@/composables/useDataUpdate'
import { setScanningStatusPolling, useScanningStatus } from '@/composables/useScanningStatus'
import { useUpdateMirrors } from '@/composables/useUpdateMirrors'
import { useStaticData } from '@/utils/gameData/staticData'
import { getGemTagName, getStatsForWeapon } from '@/utils/gameData/weapon'

const theme = useTheme()
const { weaponTypes, weaponsMap, rarityColors, essencesMap, isLoaded, fetchStaticData } =
  useStaticData()
const { isScanning, pollingEnabled } = useScanningStatus()
const { mirrorOptions } = useUpdateMirrors()
const {
  status: dataUpdateStatus,
  isChecking: isCheckingDataUpdate,
  isDownloading: isDownloadingDataUpdate,
  successDialogVisible,
  infoDialogVisible,
  errorDialogVisible,
  dialogMessage,
  dismissDialogs,
  fetchDataUpdateStatus,
  checkWeaponDataUpdate,
  downloadWeaponDataUpdate,
} = useDataUpdate()

const statusPollingEnabled = ref(pollingEnabled)
const configVersion = ref(0)
const loadedTrashWeaponIds = ref<string[]>([])
const hasLoadedConfig = ref(false)

const allAttributeStats = computed(() =>
  Array.from(essencesMap.value.values())
    .filter((e) => e.type === 'ATTRIBUTE')
    .map((e) => e.id),
)
const allSecondaryStats = computed(() =>
  Array.from(essencesMap.value.values())
    .filter((e) => e.type === 'SECONDARY')
    .map((e) => e.id),
)
const allSkillStats = computed(() =>
  Array.from(essencesMap.value.values())
    .filter((e) => e.type === 'SKILL')
    .map((e) => e.id),
)

interface EssenceStat {
  attribute: string | null
  secondary: string | null
  skill: string | null
}

const selectedWeaponIds = ref<string[]>([])
const treasureEssenceStats = ref<EssenceStat[]>([])
const treasureAction = ref('lock')
const trashAction = ref('unlock')
const nonFiveStarBehavior = ref('process')
const autoPageFlip = ref(true)
const pageFlipMode = ref('wheel')
const enableSound = ref(true)
const highLevelTreasureEnabled = ref(false)
const highLevelTreasureAttributeThreshold = ref(3)
const highLevelTreasureSecondaryThreshold = ref(3)
const highLevelTreasureSkillThreshold = ref(3)
const updateMirror = ref('github')
const updateProxyEnabled = ref(false)
const updateProxyPort = ref('7890')
const weaponEssenceCounts = ref<Record<string, number>>({})

const dataUpdateSourceText = computed(() => {
  if (!dataUpdateStatus.value) {
    return '未知'
  }
  return dataUpdateStatus.value.currentDataSource === 'override' ? '热更新覆盖' : '内置资源'
})

const notSelectedWeaponIds = computed(() => {
  return Array.from(weaponsMap.value.keys()).filter(
    (weaponId) => !selectedWeaponIds.value.includes(weaponId),
  )
})

const selectedMirrorName = computed(() => {
  const mirror = mirrorOptions.value.find((m) => m.value === updateMirror.value)
  return mirror ? mirror.title : 'GitHub 官方'
})

function formatDataUpdateTime(value: string | null | undefined): string {
  if (!value) {
    return '暂无'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function getWeaponStatsDescription(weaponId: string): string {
  const stats = getStatsForWeapon(weaponId)
  if (!stats.attribute && !stats.secondary && !stats.skill) {
    return '暂无词条信息'
  }

  const parts: string[] = []
  if (stats.attribute) {
    parts.push(getGemTagName(stats.attribute))
  }
  if (stats.secondary) {
    parts.push(getGemTagName(stats.secondary))
  }
  if (stats.skill) {
    parts.push(getGemTagName(stats.skill))
  }
  return parts.join(' / ')
}

function raritySelectAll(rarity: number, select: boolean) {
  const weaponIds = Array.from(weaponsMap.value.values())
    .filter((weapon) => weapon.rarity === rarity)
    .map((weapon) => weapon.id)
  if (select) {
    selectedWeaponIds.value = [...new Set([...selectedWeaponIds.value, ...weaponIds])]
  } else {
    selectedWeaponIds.value = selectedWeaponIds.value.filter((id) => !weaponIds.includes(id))
  }
}

function isRarityAllSelected(rarity: number): boolean {
  const weaponIds = Array.from(weaponsMap.value.values())
    .filter((weapon) => weapon.rarity === rarity)
    .map((weapon) => weapon.id)
  if (weaponIds.length === 0) return false
  return weaponIds.every((id) => selectedWeaponIds.value.includes(id))
}

function isRarityPartiallySelected(rarity: number): boolean {
  const weaponIds = Array.from(weaponsMap.value.values())
    .filter((weapon) => weapon.rarity === rarity)
    .map((weapon) => weapon.id)
  if (weaponIds.length === 0) return false
  const selectedCount = weaponIds.filter((id) => selectedWeaponIds.value.includes(id)).length
  return selectedCount > 0 && selectedCount < weaponIds.length
}

function typeSelectAll(groupId: string, select: boolean) {
  const weaponType = weaponTypes.value.find((t) => t.id === groupId)
  const weaponIds = weaponType?.weaponIds ?? []
  if (select) {
    selectedWeaponIds.value = [...new Set([...selectedWeaponIds.value, ...weaponIds])]
  } else {
    selectedWeaponIds.value = selectedWeaponIds.value.filter((id) => !weaponIds.includes(id))
  }
}

function isTypeAllSelected(groupId: string): boolean {
  const weaponType = weaponTypes.value.find((t) => t.id === groupId)
  const weaponIds = weaponType?.weaponIds ?? []
  if (weaponIds.length === 0) return false
  return weaponIds.every((id) => selectedWeaponIds.value.includes(id))
}

function isTypePartiallySelected(groupId: string): boolean {
  const weaponType = weaponTypes.value.find((t) => t.id === groupId)
  const weaponIds = weaponType?.weaponIds ?? []
  if (weaponIds.length === 0) return false
  const selectedCount = weaponIds.filter((id) => selectedWeaponIds.value.includes(id)).length
  return selectedCount > 0 && selectedCount < weaponIds.length
}

const config = computed(() => {
  const proxyUrl = updateProxyEnabled.value ? `http://127.0.0.1:${updateProxyPort.value}` : ''
  return {
    version: 5,
    trash_weapon_ids: notSelectedWeaponIds.value,
    treasure_essence_stats: treasureEssenceStats.value,
    treasure_action: treasureAction.value,
    trash_action: trashAction.value,
    non_five_star_behavior: nonFiveStarBehavior.value,
    auto_page_flip: autoPageFlip.value,
    page_flip_mode: pageFlipMode.value,
    enable_sound: enableSound.value,
    high_level_treasure_enabled: highLevelTreasureEnabled.value,
    high_level_treasure_attribute_threshold: highLevelTreasureAttributeThreshold.value,
    high_level_treasure_secondary_threshold: highLevelTreasureSecondaryThreshold.value,
    high_level_treasure_skill_threshold: highLevelTreasureSkillThreshold.value,
    update_mirror: updateMirror.value,
    update_proxy: proxyUrl,
  }
})

async function getConfig() {
  const response = await fetch('/api/config')
  if (!response.ok) {
    throw new Error(`/api/config -> ${response.status}`)
  }

  const result = await response.json()
  const {
    version,
    trash_weapon_ids,
    treasure_essence_stats,
    treasure_action,
    trash_action,
    non_five_star_behavior,
    auto_page_flip,
    page_flip_mode,
    enable_sound,
    high_level_treasure_enabled,
    high_level_treasure_attribute_threshold,
    high_level_treasure_secondary_threshold,
    high_level_treasure_skill_threshold,
    update_mirror,
    update_proxy,
  } = result

  configVersion.value = version
  treasureEssenceStats.value = treasure_essence_stats
  treasureAction.value = treasure_action
  trashAction.value = trash_action
  nonFiveStarBehavior.value = non_five_star_behavior || 'process'
  autoPageFlip.value = auto_page_flip !== undefined ? auto_page_flip : true
  pageFlipMode.value = page_flip_mode || 'wheel'
  enableSound.value = enable_sound !== undefined ? enable_sound : true
  highLevelTreasureEnabled.value = high_level_treasure_enabled
  highLevelTreasureAttributeThreshold.value = high_level_treasure_attribute_threshold
  highLevelTreasureSecondaryThreshold.value = high_level_treasure_secondary_threshold
  highLevelTreasureSkillThreshold.value = high_level_treasure_skill_threshold
  updateMirror.value = update_mirror || 'github'

  if (update_proxy) {
    updateProxyEnabled.value = true
    const match = update_proxy.match(/:(\d+)$/)
    updateProxyPort.value = match ? match[1] : '7890'
  } else {
    updateProxyEnabled.value = false
    updateProxyPort.value = '7890'
  }

  loadedTrashWeaponIds.value = trash_weapon_ids
  selectedWeaponIds.value = Array.from(weaponsMap.value.keys()).filter(
    (weaponId) => !trash_weapon_ids.includes(weaponId),
  )
  hasLoadedConfig.value = true
}

async function postConfig() {
  await fetch('/api/config', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config.value),
  })
}

async function fetchWeaponEssenceCounts() {
  try {
    const response = await fetch('/api/weapon_essence_counts')
    const result = await response.json()
    weaponEssenceCounts.value = result
  } catch (error) {
    console.error('Failed to fetch weapon essence counts:', error)
  }
}

let pollTimer: number | null = null

function clearPolling() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

function schedulePolling(delay: number) {
  clearPolling()
  if (!statusPollingEnabled.value) {
    return
  }

  pollTimer = window.setTimeout(() => {
    void pollStatusLoop()
  }, delay)
}

async function pollStatusLoop() {
  pollTimer = null

  if (!statusPollingEnabled.value) {
    return
  }

  if (isScanning.value) {
    await fetchWeaponEssenceCounts()
    schedulePolling(1000)
    return
  }

  await Promise.allSettled([fetchWeaponEssenceCounts(), fetchDataUpdateStatus()])
  schedulePolling(5000)
}

function restartPolling() {
  if (!statusPollingEnabled.value) {
    clearPolling()
    return
  }
  schedulePolling(isScanning.value ? 1000 : 5000)
}

function onStatusPollingToggle(enabled: boolean | null) {
  if (enabled === null) return

  setScanningStatusPolling(enabled)
  if (!enabled) {
    clearPolling()
    return
  }

  void Promise.allSettled([fetchWeaponEssenceCounts(), fetchDataUpdateStatus()])
  restartPolling()
}

watch(isScanning, () => {
  if (!statusPollingEnabled.value) {
    return
  }

  void fetchWeaponEssenceCounts()
  restartPolling()
})

watch(
  () => Array.from(weaponsMap.value.keys()),
  (currentWeaponIds, previousWeaponIds) => {
    if (!hasLoadedConfig.value) {
      return
    }

    const previousIds = previousWeaponIds ? new Set(previousWeaponIds) : new Set<string>()
    const newWeaponIds = currentWeaponIds.filter((weaponId) => !previousIds.has(weaponId))

    if (newWeaponIds.length === 0) {
      return
    }

    const autoSelectedNewWeaponIds = newWeaponIds.filter(
      (weaponId) => !loadedTrashWeaponIds.value.includes(weaponId),
    )

    if (autoSelectedNewWeaponIds.length === 0) {
      return
    }

    selectedWeaponIds.value = [
      ...new Set([...selectedWeaponIds.value, ...autoSelectedNewWeaponIds]),
    ]
  },
)

onMounted(async () => {
  if (!isLoaded.value) {
    await fetchStaticData()
  }

  await getConfig()
  await Promise.allSettled([fetchWeaponEssenceCounts(), fetchDataUpdateStatus()])
  watch(config, postConfig, { deep: true })
  restartPolling()
})

onBeforeUnmount(() => {
  clearPolling()
})
</script>

<style scoped lang="scss">
$weapon-icon-size: clamp(3rem, 16vw, 6rem);

.group-icon {
  width: 2rem;
  height: 2rem;
}

.weapon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, $weapon-icon-size);
  gap: calc($weapon-icon-size / 10);
}

.weapon-item {
  width: $weapon-icon-size;
  height: $weapon-icon-size;
}
</style>
