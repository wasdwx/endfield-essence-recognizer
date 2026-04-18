import { onMounted, ref } from 'vue'

export function useUpdateMirrors() {
  const mirrorOptions = ref<Array<{ title: string; value: string }>>([])

  onMounted(async () => {
    try {
      const response = await fetch('/api/update/mirrors')
      const data = await response.json()
      mirrorOptions.value = data.mirrors
    } catch (error) {
      console.error('获取镜像源列表失败：', error)
      mirrorOptions.value = [{ title: 'GitHub 官方', value: 'github' }]
    }
  })

  return { mirrorOptions }
}
