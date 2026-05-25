# Nhiệm vụ: Research & Plan UI/UX Mobile Best Practices cho Gallery Vue App

## Bối cảnh

Gallery Vue 3 app tại `/home/ubuntu/gallery-repo/gallery/frontend/`.
Đã có research cơ bản ở `_ux_research.md`.

## Yêu cầu

### Phần 1: Research sâu hơn (web search)

Search web để tìm các best practices UI/UX mobile cho photo gallery app:

1. **Material Design 3** — Navigation bar, Search, Top app bar patterns
2. **iOS HIG** — Tab bars, Navigation bars, Search bars
3. **Bài viết UX về mobile photo gallery app** — "mobile photo gallery UI best practices 2024 2025"
4. **Bottom navigation design patterns** — Khi nào nên dùng, bao nhiêu tabs, icon + label?
5. **Collapsible header patterns** — Scroll-based header hide/show
6. **Search UX patterns** — Full-width search bar vs icon expand, search suggestions

Dùng web search tool và browser tool (nếu được) để lấy thông tin từ các bài viết, blog UI/UX.

### Phần 2: Phân tích cụ thể cho Gallery Vue

Đọc lại toàn bộ code:
- `frontend/src/App.vue` — shell layout, header, sidebar, theme toggle, search
- `frontend/src/components/GalleryGrid.vue` — grid header, nav buttons, breadcrumb, sort, grid slider, folder bar
- `frontend/src/components/Lightbox.vue` — lightbox mobile bottom sheet
- `frontend/src/components/SidebarHeader.vue` — sidebar
- `frontend/src/components/FolderTreeItem.vue` — folder tree
- `frontend/src/styles/main.scss` — global styles

Phân tích:
- **Current mobile user flow:** User mở app → thấy gì? → làm gì tiếp? → navigation thế nào?
- **Pain points:** Điểm nào khó chịu trên mobile hiện tại?
- **So sánh với best practices:** Gallery Vue đang thiếu gì so với chuẩn?

### Phần 3: Lên Plan chi tiết

Viết plan cụ thể, theo thứ tự ưu tiên, gồm:

#### Phase 1 (High Impact, Low Effort — làm ngay được)
- Những thay đổi CSS thuần (không cần sửa HTML/JS)
- Gom/gọn/bỏ element dư thừa

#### Phase 2 (Medium Impact, Medium Effort)
- Thay đổi cấu trúc HTML (thêm/bỏ component)
- Search UX cải tiến

#### Phase 3 (High Impact, High Effort)
- Bottom navigation bar
- Bỏ hamburger menu pattern
- Collapsible header
- Grid gestures

#### Phase 4 (Enhancements)
- Animation, transition
- Haptic feedback
- Pull-to-refresh
- Pinch-to-zoom grid

### Output

Ghi vào file `_mobile_ux_plan.md` trong thư mục gốc dự án.
Plan phải có:
- Mỗi item: mô tả, file cần sửa, estimated effort (phút/giờ)
- Rủi ro khi implement
- Cách test/verify
