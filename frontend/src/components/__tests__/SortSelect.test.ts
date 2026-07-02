import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import SortSelect from "../SortSelect.vue";

type SortValue = "date_desc" | "date_asc" | "name_asc" | "name_desc";

function mountSubject(modelValue: SortValue = "name_asc") {
  const onUpdate = vi.fn();

  const wrapper = mount(SortSelect, {
    props: {
      modelValue,
      "onUpdate:modelValue": onUpdate,
    },
    global: {
      stubs: {
        Button: { template: "<button type='button'><slot /></button>" },
        DropdownMenu: { template: "<div><slot /></div>" },
        DropdownMenuTrigger: { template: "<div><slot /></div>" },
        DropdownMenuContent: { template: "<div><slot /></div>" },
        DropdownMenuGroup: { template: "<div><slot /></div>" },
        DropdownMenuItem: { template: "<button type='button' @click=\"$emit('select')\"><slot /></button>" },
      },
    },
  });

  return { wrapper, onUpdate };
}

describe("SortSelect", () => {
  it("toggles the active field direction", async () => {
    const { wrapper, onUpdate } = mountSubject("name_asc");
    const [, nameItem] = wrapper.findAll("button");

    await nameItem.trigger("click");

    expect(onUpdate).toHaveBeenCalledWith("name_desc");
  });

  it("uses newest-first when switching to modified", async () => {
    const { wrapper, onUpdate } = mountSubject("name_asc");
    const [, , modifiedItem] = wrapper.findAll("button");

    await modifiedItem.trigger("click");

    expect(onUpdate).toHaveBeenCalledWith("date_desc");
  });

  it("toggles modified to oldest-first", async () => {
    const { wrapper, onUpdate } = mountSubject("date_desc");
    const [, , modifiedItem] = wrapper.findAll("button");

    await modifiedItem.trigger("click");

    expect(onUpdate).toHaveBeenCalledWith("date_asc");
  });
});
