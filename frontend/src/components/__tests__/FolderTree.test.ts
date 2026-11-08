import { describe, it, expect, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { mount } from "@vue/test-utils";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { createIsolatedQueryClient } from "@/test/queryClient";
import { useGalleryStore } from "@/stores/gallery";
import FolderTree from "../FolderTree.vue";
import type { FolderTreeNode } from "@/types";

function folder(overrides: Partial<FolderTreeNode>): FolderTreeNode {
  return {
    name: "Folder",
    path: "/library/Folder",
    type: "folder",
    has_children: false,
    children: undefined,
    ...overrides,
  } as FolderTreeNode;
}

function mountExpandedTree(tree: FolderTreeNode[]) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const galleryStore = useGalleryStore();
  for (const node of tree) galleryStore.setFolderExpanded(node.path, true);

  return mount(FolderTree, {
    props: { tree, activePath: "" },
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient: createIsolatedQueryClient() }]],
    },
    attachTo: document.body,
  });
}

describe("FolderTree empty placeholder", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("shows No subfolders for an expanded folder that has media but no subfolders", () => {
    const wrapper = mountExpandedTree([
      folder({
        name: "Night City",
        path: "/library/Night City",
        has_children: true,
        image_count: 12,
        children: [],
      }),
    ]);

    expect(wrapper.text()).toContain("No subfolders");
    expect(wrapper.text()).not.toContain("(Empty)");
    wrapper.unmount();
  });

  it("keeps (Empty) for a truly empty folder", () => {
    const wrapper = mountExpandedTree([
      folder({
        name: "Empty Folder",
        path: "/library/Empty Folder",
        has_children: true,
        image_count: 0,
        children: [],
      }),
    ]);

    expect(wrapper.text()).toContain("(Empty)");
    expect(wrapper.text()).not.toContain("No subfolders");
    wrapper.unmount();
  });
});
