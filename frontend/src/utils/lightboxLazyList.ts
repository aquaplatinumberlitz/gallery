/**
 * An array-like list whose items are built the first time they are read.
 *
 * Opening a lightbox over a 200-item album built the whole PhotoSwipe data source up front, and each item
 * costs two `URLSearchParams` URL builds plus a dimension lookup (about 15 ms of the click task at 4x CPU),
 * although PhotoSwipe only reads the opening item and its neighbours. The list is a `Proxy` over an array
 * of the right length, so `Array.isArray`, `length`, `list[index]`, iteration and `map` behave like a plain
 * array, and an item is built once, on first access, and then is an ordinary object that callers may mutate.
 */
export function createLazyList<T extends object>(count: number, build: (index: number) => T): T[] {
  const target = new Array<T>(count);

  const indexOf = (prop: string | symbol): number | null => {
    if (typeof prop !== "string") return null;
    const index = Number(prop);
    return Number.isInteger(index) && index >= 0 && index < target.length && String(index) === prop ? index : null;
  };

  const materialize = (index: number): T => {
    const existing = target[index];
    if (existing !== undefined) return existing;
    const built = build(index);
    target[index] = built;
    return built;
  };

  return new Proxy(target, {
    get(array, prop, receiver) {
      const index = indexOf(prop);
      return index === null ? Reflect.get(array, prop, receiver) : materialize(index);
    },
    has(array, prop) {
      return indexOf(prop) !== null || Reflect.has(array, prop);
    },
    set(array, prop, value, receiver) {
      return Reflect.set(array, prop, value, receiver);
    },
    getOwnPropertyDescriptor(array, prop) {
      const index = indexOf(prop);
      if (index !== null) {
        materialize(index);
      }
      return Reflect.getOwnPropertyDescriptor(array, prop);
    },
    ownKeys(array) {
      for (let index = 0; index < array.length; index += 1) materialize(index);
      return Reflect.ownKeys(array);
    },
  });
}

/**
 * Grows a list made by `createLazyList` in place so that it has `count` items. Existing items, built or not, keep
 * their index and identity; the new slots are built on first read like the original ones. A smaller `count` is
 * ignored: the list only ever grows (a paged album appends pages; it never drops the ones already shown).
 *
 * PhotoSwipe reads `dataSource.length` on every use, so growing the list is how it learns about a new page.
 */
export function growLazyList<T extends object>(list: T[], count: number): void {
  if (count > list.length) list.length = count;
}
