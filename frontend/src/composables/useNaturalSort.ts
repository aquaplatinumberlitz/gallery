export function naturalSortKey(s: string): (string | number)[] {
  return s.split(/(\d+)/).map((part) => {
    const num = parseInt(part, 10);
    return isNaN(num) ? part.toLowerCase() : num;
  });
}

const naturalCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

export function compareNatural(a: string, b: string): number {
  return naturalCollator.compare(a, b);
}
