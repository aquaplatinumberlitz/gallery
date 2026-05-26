# Album Section: Horizontal Scroll Proposal

## Current behavior

Trong GalleryGrid.vue, albums section hiện tại dùng CSS grid:
```css
.album-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 32px;
}
```

Album cards có chiều cao ~320px (280px cover + info). Nhiều album → nhiều hàng → đẩy photos section xuống dưới, người dùng phải scroll mới thấy ảnh.

## Proposed behavior

User đề xuất:
1. Albums luôn **1 hàng duy nhất** (max 1 row)
2. Nếu số album > số cột có thể chứa → **scroll ngang** (horizontal scroll/carousel)
3. Photos section luôn thấy ngay dưới albums, không bị đẩy xuống sâu
4. Số cột trên desktop vẫn linh hoạt (auto-fill là OK)

## Yêu cầu

1. **Đánh giá:** ý tưởng này có tốt không? So sánh với pattern của Google Photos, Apple Photos, Pinterest?
2. **Implementation đề xuất:**
   - CSS: `overflow-x: auto; flex-wrap: nowrap` hoặc `display: flex` thay vì grid
   - Scroll behavior: ẩn scrollbar (Chrome, Firefox, Safari)
   - Scroll snap: snap từng card
   - Gradient fade ở 2 đầu (tùy chọn)
3. **Code cụ thể:** CSS cho album grid thành horizontal scroll, chỉ 1 row
4. **Rủi ro:** responsive, touch devices, keyboard navigation

Đọc code GalleryGrid.vue (album section HTML + CSS) và AlbumCard.vue để đề xuất chính xác.

## Output

Trả lời bằng tiếng Việt, kèm code CSS + HTML thay đổi cụ thể.
