<script setup lang="ts">
import { MoreHorizontal, Eye, Pencil, Play, Wrench, Trash2, Images } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{
  view: [];
  use: [];
  edit: [];
  scan: [];
  repair: [];
  unregister: [];
}>();
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon" :disabled="disabled" aria-label="Library actions"><MoreHorizontal /></Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end">
      <DropdownMenuItem @select="emit('view')"><Eye /> View details</DropdownMenuItem>
      <DropdownMenuItem @select="emit('use')"><Images /> Use in gallery</DropdownMenuItem>
      <DropdownMenuItem @select="emit('edit')"><Pencil /> Edit</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @select="emit('scan')"><Play /> Scan / Rescan</DropdownMenuItem>
      <DropdownMenuItem @select="emit('repair')"><Wrench /> Repair</DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem class="text-destructive focus:text-destructive" @select="emit('unregister')">
        <Trash2 /> Unregister
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
