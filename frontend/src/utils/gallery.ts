export function shouldLoadMoreImages(input: {
  hasMoreImages: boolean;
  isLoadingMore: boolean;
  isFetching: boolean;
  hasSearchQuery: boolean;
}): boolean {
  return input.hasMoreImages && !input.isLoadingMore && !input.isFetching && !input.hasSearchQuery;
}
