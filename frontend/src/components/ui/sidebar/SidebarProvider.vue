<script setup lang="ts">
import type { HTMLAttributes, Ref } from "vue"
import { useMediaQuery, useVModel } from "@vueuse/core"
import { TooltipProvider } from "reka-ui"
import { computed, ref } from "vue"
import { cn } from "@/lib/utils"
import { provideSidebarContext, SIDEBAR_WIDTH, SIDEBAR_WIDTH_ICON } from "./utils"

const props = withDefaults(defineProps<{
  defaultOpen?: boolean
  open?: boolean
  openMobile?: boolean
  defaultOpenMobile?: boolean
  class?: HTMLAttributes["class"]
}>(), {
  defaultOpen: true,
  open: undefined,
  openMobile: undefined,
  defaultOpenMobile: false,
})

const emits = defineEmits<{
  "update:open": [open: boolean]
  "update:openMobile": [open: boolean]
}>()

const isMobile = useMediaQuery("(max-width: 1199px)")

const open = useVModel(props, "open", emits, {
  defaultValue: props.defaultOpen ?? false,
  passive: (props.open === undefined) as false,
}) as Ref<boolean>

const openMobile = useVModel(props, "openMobile", emits, {
  defaultValue: props.defaultOpenMobile ?? false,
  passive: (props.openMobile === undefined) as false,
}) as Ref<boolean>

function setOpen(value: boolean) {
  open.value = value
}

function setOpenMobile(value: boolean) {
  openMobile.value = value
}

function toggleSidebar() {
  return isMobile.value ? setOpenMobile(!openMobile.value) : setOpen(!open.value)
}

const state = computed(() => open.value ? "expanded" : "collapsed")

provideSidebarContext({
  state,
  open,
  setOpen,
  isMobile,
  openMobile,
  setOpenMobile,
  toggleSidebar,
})
</script>

<template>
  <TooltipProvider :delay-duration="300" :skip-delay-duration="100">
    <div
      :style="{
        '--sidebar-width': SIDEBAR_WIDTH,
        '--sidebar-width-icon': SIDEBAR_WIDTH_ICON,
      }"
      :class="cn('group/sidebar-wrapper flex min-h-svh w-full has-[[data-variant=inset]]:bg-sidebar', props.class)"
      v-bind="$attrs"
    >
      <slot />
    </div>
  </TooltipProvider>
</template>
