<script setup lang="ts">
import { computed, shallowRef, watch } from "vue";
import { Plus, Trash2, Workflow } from "lucide-vue-next";
import Button from "@/components/ui/Button.vue";
import Input from "@/components/ui/Input.vue";
import type { SearchWorkflowGroupV1, SearchWorkflowPredicateV1, WorkflowRegistryPropertyV1 } from "@/types";

const props = withDefaults(
  defineProps<{
    registry: Record<string, Record<string, WorkflowRegistryPropertyV1>>;
    initialGroups: SearchWorkflowGroupV1[];
    serverFieldErrors?: Record<string, string>;
  }>(),
  { serverFieldErrors: () => ({}) },
);
const emit = defineEmits<{ apply: [groups: SearchWorkflowGroupV1[]] }>();
type DraftPredicate = { property: string; op: SearchWorkflowPredicateV1["op"]; value: string };
type DraftGroup = { node_type: string; predicates: DraftPredicate[] };
const groups = shallowRef<DraftGroup[]>([]);

const nodeTypes = computed(() => Object.keys(props.registry).sort());
const cloneInitial = (): DraftGroup[] =>
  props.initialGroups.map((group) => ({
    node_type: group.node_type,
    predicates: group.predicates.map((predicate) => ({
      property: predicate.property,
      op: predicate.op,
      value: String(predicate.value),
    })),
  }));

watch(
  () => props.initialGroups,
  () => {
    groups.value = cloneInitial();
  },
  { immediate: true, deep: true },
);

const definitionFor = (group: DraftGroup, predicate: DraftPredicate) =>
  props.registry[group.node_type]?.[predicate.property];

function replaceGroup(index: number, next: DraftGroup) {
  groups.value = groups.value.map((group, groupIndex) => (groupIndex === index ? next : group));
}

function addGroup() {
  const nodeType = nodeTypes.value[0];
  if (!nodeType || groups.value.length >= 4) return;
  const property = Object.keys(props.registry[nodeType])[0];
  if (!property) return;
  const definition = props.registry[nodeType][property];
  groups.value = [
    ...groups.value,
    { node_type: nodeType, predicates: [{ property, op: definition.operators[0], value: "" }] },
  ];
}

function setNodeType(groupIndex: number, nodeType: string) {
  const property = Object.keys(props.registry[nodeType] ?? {})[0];
  if (!property) return;
  const definition = props.registry[nodeType][property];
  replaceGroup(groupIndex, { node_type: nodeType, predicates: [{ property, op: definition.operators[0], value: "" }] });
}

function addPredicate(groupIndex: number) {
  const group = groups.value[groupIndex];
  if (!group || group.predicates.length >= 8) return;
  const property = Object.keys(props.registry[group.node_type] ?? {})[0];
  if (!property) return;
  const definition = props.registry[group.node_type][property];
  replaceGroup(groupIndex, {
    ...group,
    predicates: [...group.predicates, { property, op: definition.operators[0], value: "" }],
  });
}

function updatePredicate(groupIndex: number, predicateIndex: number, patch: Partial<DraftPredicate>) {
  const group = groups.value[groupIndex];
  if (!group) return;
  const predicates = group.predicates.map((predicate, index) =>
    index === predicateIndex ? { ...predicate, ...patch } : predicate,
  );
  replaceGroup(groupIndex, { ...group, predicates });
}

function setProperty(groupIndex: number, predicateIndex: number, property: string) {
  const group = groups.value[groupIndex];
  const definition = group ? props.registry[group.node_type]?.[property] : undefined;
  if (!definition) return;
  updatePredicate(groupIndex, predicateIndex, { property, op: definition.operators[0], value: "" });
}

function rowError(group: DraftGroup, predicate: DraftPredicate, groupIndex: number, predicateIndex: number): string {
  const serverPrefix = `filters.workflow_groups[${groupIndex}].predicates[${predicateIndex}]`;
  const serverError = Object.entries(props.serverFieldErrors).find(([path]) => path.startsWith(serverPrefix))?.[1];
  if (serverError) return serverError;
  const definition = definitionFor(group, predicate);
  if (!definition) return "Unsupported property";
  if (!definition.operators.includes(predicate.op)) return "Unsupported operator";
  if (!predicate.value.trim()) return "Enter a value";
  if (["integer", "real"].includes(definition.type) && !Number.isFinite(Number(predicate.value)))
    return "Enter a number";
  if (definition.type === "uint64_token" && !/^(?:0|[1-9][0-9]*)$/.test(predicate.value))
    return "Enter an unsigned integer";
  return "";
}

const errors = computed(() =>
  groups.value.map((group, groupIndex) =>
    group.predicates.map((predicate, predicateIndex) => rowError(group, predicate, groupIndex, predicateIndex)),
  ),
);
const canApply = computed(
  () => groups.value.length > 0 && errors.value.every((group) => group.every((error) => !error)),
);

function apply() {
  if (!canApply.value) return;
  const result: SearchWorkflowGroupV1[] = groups.value.map((group) => ({
    node_type: group.node_type,
    predicates: group.predicates.map((predicate) => {
      const definition = definitionFor(group, predicate)!;
      let value: string | number | boolean = predicate.value;
      if (definition.type === "integer" || definition.type === "real") value = Number(predicate.value);
      if (definition.type === "boolean") value = predicate.value === "true";
      return { property: predicate.property, op: predicate.op, value };
    }),
  }));
  emit("apply", result);
}
</script>

<template>
  <section class="workflow-builder" aria-labelledby="workflow-builder-title">
    <div class="builder-heading">
      <div>
        <p id="workflow-builder-title"><Workflow /> Workflow filters</p>
        <span>Predicates in a group must match the same node.</span>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        :disabled="groups.length >= 4 || !nodeTypes.length"
        @click="addGroup"
      >
        <Plus /> Add group
      </Button>
    </div>

    <p v-if="!nodeTypes.length" class="empty">Workflow capabilities are unavailable.</p>
    <div v-for="(group, groupIndex) in groups" :key="groupIndex" class="workflow-group">
      <div class="group-heading">
        <label :for="`workflow-node-${groupIndex}`">Node type</label>
        <select
          :id="`workflow-node-${groupIndex}`"
          :value="group.node_type"
          @change="setNodeType(groupIndex, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="nodeType in nodeTypes" :key="nodeType" :value="nodeType">{{ nodeType }}</option>
        </select>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          :aria-label="`Remove workflow group ${groupIndex + 1}`"
          @click="groups = groups.filter((_, index) => index !== groupIndex)"
        >
          <Trash2 />
        </Button>
      </div>

      <div v-for="(predicate, predicateIndex) in group.predicates" :key="predicateIndex" class="predicate-row">
        <select
          :aria-label="`Property for group ${groupIndex + 1}, row ${predicateIndex + 1}`"
          :value="predicate.property"
          @change="setProperty(groupIndex, predicateIndex, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="property in Object.keys(registry[group.node_type] ?? {})" :key="property" :value="property">
            {{ property }}
          </option>
        </select>
        <select
          :aria-label="`Operator for group ${groupIndex + 1}, row ${predicateIndex + 1}`"
          :value="predicate.op"
          @change="
            updatePredicate(groupIndex, predicateIndex, {
              op: ($event.target as HTMLSelectElement).value as SearchWorkflowPredicateV1['op'],
            })
          "
        >
          <option
            v-for="operator in definitionFor(group, predicate)?.operators ?? []"
            :key="operator"
            :value="operator"
          >
            {{ operator }}
          </option>
        </select>
        <select
          v-if="definitionFor(group, predicate)?.type === 'boolean'"
          :value="predicate.value"
          :aria-label="`Value for group ${groupIndex + 1}, row ${predicateIndex + 1}`"
          @change="updatePredicate(groupIndex, predicateIndex, { value: ($event.target as HTMLSelectElement).value })"
        >
          <option value="true">True</option>
          <option value="false">False</option>
        </select>
        <Input
          v-else
          :model-value="predicate.value"
          :inputmode="
            ['integer', 'real', 'uint64_token'].includes(definitionFor(group, predicate)?.type ?? '')
              ? 'numeric'
              : 'text'
          "
          :aria-label="`Value for group ${groupIndex + 1}, row ${predicateIndex + 1}`"
          :aria-invalid="Boolean(errors[groupIndex]?.[predicateIndex])"
          @update:model-value="updatePredicate(groupIndex, predicateIndex, { value: String($event) })"
        />
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          :disabled="group.predicates.length === 1"
          :aria-label="`Remove predicate ${predicateIndex + 1}`"
          @click="
            replaceGroup(groupIndex, {
              ...group,
              predicates: group.predicates.filter((_, index) => index !== predicateIndex),
            })
          "
        >
          <Trash2 />
        </Button>
        <p v-if="errors[groupIndex]?.[predicateIndex]" class="row-error" role="alert">
          {{ errors[groupIndex][predicateIndex] }}
        </p>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        :disabled="group.predicates.length >= 8"
        @click="addPredicate(groupIndex)"
      >
        <Plus /> Add predicate
      </Button>
    </div>

    <Button type="button" size="sm" :disabled="!canApply" @click="apply">Show matching assets</Button>
  </section>
</template>

<style scoped>
.workflow-builder {
  display: grid;
  gap: 12px;
}
.builder-heading,
.group-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.builder-heading p {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  font-weight: 650;
}
.builder-heading svg {
  width: 16px;
}
.builder-heading span,
.empty {
  color: var(--muted-foreground);
  font-size: 12px;
}
.workflow-group {
  display: grid;
  gap: 9px;
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 10px;
}
.group-heading label {
  font-size: 12px;
  font-weight: 600;
}
select {
  min-height: 36px;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 0 8px;
  background: var(--background);
  font-size: 12px;
}
.group-heading select {
  flex: 1;
}
.predicate-row {
  display: grid;
  grid-template-columns: 1.15fr 0.75fr 1fr auto;
  gap: 6px;
  align-items: start;
}
.row-error {
  grid-column: 1 / -1;
  color: var(--destructive);
  font-size: 11px;
}
@media (max-width: 640px) {
  .predicate-row {
    grid-template-columns: 1fr 1fr;
  }
  .predicate-row > :nth-child(3) {
    grid-column: 1 / -1;
  }
}
</style>
