'use strict';
const $ = (id) => document.getElementById(id);
const token = sessionStorage.getItem('access_token');
let me = null;
let page = 1;
const limit = 20;
let currentRows = [];
let editingId = null;
let confirmAction = null;
let requestSerial = 0;
const roleLabel = (role) => role === 'ADMIN' ? 'Quản trị viên' : 'Chủ trọ';
const dateLabel = (value) => new Date(value).toLocaleString('vi-VN');
function banner(text, success = false) {
  $('global-message').textContent = text;
  $('global-message').classList.toggle('success', success);
  $('global-message').hidden = !text;
}
function loginAgain(notice = 'expired') {
  sessionStorage.removeItem('access_token');
  location.replace('/ui/?notice=' + notice);
}
function errorText(data) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item) => item.msg.replace(/^Value error, /, '')).join(' ');
  return 'Không xử lý được yêu cầu. Vui lòng thử lại.';
}
async function api(path, method = 'GET', body) {
  const headers = {Authorization: 'Bearer ' + token};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let response;
  try { response = await fetch(path, {method, headers, body: body === undefined ? undefined : JSON.stringify(body)}); }
  catch { throw new Error('Không kết nối được API. Kiểm tra backend đang chạy.'); }
  if (response.status === 401) { loginAgain(); throw new Error('Phiên đăng nhập đã hết hạn.'); }
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(errorText(data));
  return data;
}
function initials(name) { return name.trim().split(/\s+/).slice(-2).map((part) => part[0]).join('').toUpperCase(); }
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function drawProfile(container, user) {
  container.replaceChildren();
  const fields = [
    ['Mã tài khoản', user.user_id], ['Họ tên', user.full_name], ['Email', user.email],
    ['Số điện thoại', user.phone ?? 'Chưa cung cấp'], ['Vai trò', roleLabel(user.role_name)],
    ['Trạng thái', user.status === 'ACTIVE' ? 'Hoạt động' : 'Đã khóa'],
    ['Ngày tạo', dateLabel(user.created_at)], ['Cập nhật', dateLabel(user.updated_at)]
  ];
  for (const [label, value] of fields) container.append(node('dt', label), node('dd', value));
}
function showSection(profile) {
  if (!profile && me?.role_name !== 'ADMIN') return;
  $('admin-section').hidden = profile;
  $('profile-section').hidden = !profile;
  $('accounts-nav').classList.toggle('active', !profile);
  $('profile-nav').classList.toggle('active', profile);
}
function actionButton(label, className, action, disabled = false) {
  const button = node('button', label, 'action-button ' + className);
  button.type = 'button'; button.disabled = disabled;
  button.addEventListener('click', action);
  return button;
}
async function loadStats() {
  const stats = await api('/users/overview');
  for (const key of ['total', 'admins', 'landlords', 'active', 'locked']) $('stat-' + key).textContent = stats[key];
}
function query() {
  const params = new URLSearchParams({page, limit});
  if ($('search').value.trim()) params.set('search', $('search').value.trim());
  if ($('filter-role').value) params.set('role_name', $('filter-role').value);
  if ($('filter-status').value) params.set('status', $('filter-status').value);
  return params;
}
async function loadUsers() {
  const serial = ++requestSerial;
  $('previous').disabled = true; $('next').disabled = true;
  $('table-state').textContent = 'Đang tải danh sách…';
  try {
    const result = await api('/users?' + query());
    if (serial !== requestSerial) return;
    if (page > 1 && result.data.length === 0) { page--; return loadUsers(); }
    currentRows = result.data;
    $('users').replaceChildren();
    for (const user of result.data) {
      const tr = node('tr');
      const personCell = node('td');
      const person = node('div', undefined, 'person');
      const text = node('div'); text.append(node('strong', user.full_name), node('small', 'ID · ' + user.user_id));
      person.append(node('div', initials(user.full_name), 'avatar'), text); personCell.append(person);
      const contact = node('td', undefined, 'contact'); contact.append(node('div', user.email), node('small', user.phone ?? 'Chưa có SĐT'));
      const role = node('td'); role.append(node('span', roleLabel(user.role_name), 'badge ' + (user.role_name === 'ADMIN' ? 'admin' : '')));
      const status = node('td'); status.append(node('span', (user.status === 'ACTIVE' ? '● Hoạt động' : '● Đã khóa'), 'badge ' + (user.status === 'ACTIVE' ? 'active' : 'locked')));
      const actionsCell = node('td'); const actions = node('div', undefined, 'row-actions');
      actions.append(
        actionButton('Xem', '', () => showDetail(user.user_id)),
        actionButton('Sửa', '', () => openUser(user.user_id)),
        actionButton(user.status === 'ACTIVE' ? 'Khóa' : 'Mở khóa', '', () => confirmStatus(user), user.user_id === me.user_id),
        actionButton('Xóa', 'delete', () => confirmDelete(user), user.user_id === me.user_id)
      );
      actionsCell.append(actions); tr.append(personCell, contact, role, status, actionsCell); $('users').append(tr);
    }
    $('table-state').textContent = result.total === 0 ? 'Không có tài khoản phù hợp với bộ lọc.' : '';
    $('total-label').textContent = result.total ? `Hiển thị ${(page - 1) * limit + 1}–${(page - 1) * limit + result.data.length} / ${result.total} tài khoản` : '0 tài khoản';
    $('page-label').textContent = `Trang ${page} / ${Math.max(1, Math.ceil(result.total / limit))}`;
    $('previous').disabled = page <= 1; $('next').disabled = page * limit >= result.total;
  } catch (error) {
    if (serial !== requestSerial) return;
    $('users').replaceChildren(); $('table-state').textContent = error.message;
    $('total-label').textContent = ''; $('page-label').textContent = '';
  }
}
async function reloadAdmin() {
  await Promise.all([loadUsers(), loadStats()]);
}
async function showDetail(id) {
  try { const user = await api('/users/' + id); drawProfile($('user-detail'), user); $('detail-dialog').showModal(); }
  catch (error) { banner(error.message); }
}
async function openUser(id = null) {
  try {
    const user = id ? await api('/users/' + id) : null;
    editingId = id; $('user-form').reset(); $('user-error').textContent = '';
    $('user-title').textContent = id ? 'Cập nhật tài khoản' : 'Tạo tài khoản';
    $('save-user').textContent = id ? 'Lưu thay đổi' : 'Tạo tài khoản';
    $('create-password-field').hidden = !!id; $('user-password').required = !id; $('user-password').disabled = !!id;
    $('user-role').disabled = id === me.user_id; $('user-status').disabled = id === me.user_id;
    if (user) {
      $('full-name').value = user.full_name; $('user-email').value = user.email; $('user-phone').value = user.phone ?? '';
      $('user-role').value = user.role_name; $('user-status').value = user.status;
    }
    $('user-dialog').showModal();
  } catch (error) { banner(error.message); }
}
$('user-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('user-error').textContent = ''; $('save-user').disabled = true;
  const body = {full_name: $('full-name').value.trim(), email: $('user-email').value.trim(), phone: $('user-phone').value.trim() || null};
  if (editingId !== me.user_id) { body.role_name = $('user-role').value; body.status = $('user-status').value; }
  if (!editingId) body.password = $('user-password').value;
  try {
    const user = await api(editingId ? '/users/' + editingId : '/users', editingId ? 'PATCH' : 'POST', body);
    $('user-dialog').close(); $('user-password').value = '';
    if (user.user_id === me.user_id) { me = user; updateMe(); }
    banner(editingId ? 'Đã cập nhật tài khoản.' : 'Đã tạo tài khoản.', true);
    await reloadAdmin();
  } catch (error) { $('user-error').textContent = error.message; }
  finally { $('save-user').disabled = false; }
});
function openConfirm(title, description, action, label, danger = true) {
  $('confirm-title').textContent = title; $('confirm-description').textContent = description;
  $('confirm-error').textContent = ''; $('confirm-action').textContent = label;
  $('confirm-action').className = danger ? 'danger' : 'primary';
  confirmAction = action; $('confirm-dialog').showModal();
}
function confirmStatus(user) {
  const lock = user.status === 'ACTIVE';
  openConfirm(lock ? 'Khóa tài khoản?' : 'Mở khóa tài khoản?',
    lock ? `${user.full_name} sẽ bị đăng xuất và không thể đăng nhập cho đến khi được mở khóa.` : `${user.full_name} sẽ được phép đăng nhập trở lại.`,
    () => api('/users/' + user.user_id + '/status', 'PATCH', {status: lock ? 'LOCKED' : 'ACTIVE'}),
    lock ? 'Khóa tài khoản' : 'Mở khóa', lock);
}
function confirmDelete(user) {
  openConfirm('Xóa tài khoản?', `Xóa tài khoản của ${user.full_name}? Chỉ xóa được khi chưa có dữ liệu nghiệp vụ liên quan. Nếu đã có dữ liệu, hãy khóa tài khoản để giữ lịch sử.`,
    () => api('/users/' + user.user_id, 'DELETE'), 'Xóa tài khoản');
}
$('confirm-action').addEventListener('click', async () => {
  if (!confirmAction) return;
  $('confirm-action').disabled = true;
  try { await confirmAction(); $('confirm-dialog').close(); banner('Đã cập nhật danh sách tài khoản.', true); await reloadAdmin(); }
  catch (error) { $('confirm-error').textContent = error.message; }
  finally { $('confirm-action').disabled = false; }
});
function openPassword() { $('password-form').reset(); $('password-error').textContent = ''; $('password-dialog').showModal(); }
$('password-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('password-error').textContent = '';
  if ($('new-password').value !== $('confirm-password').value) { $('password-error').textContent = 'Xác nhận mật khẩu mới không khớp.'; return; }
  $('save-password').disabled = true;
  try {
    await api('/auth/change-password', 'POST', {current_password: $('current-password').value, new_password: $('new-password').value, confirm_password: $('confirm-password').value});
    $('password-form').reset(); loginAgain('password-changed');
  } catch (error) { $('password-error').textContent = error.message; }
  finally { $('save-password').disabled = false; }
});
for (const button of document.querySelectorAll('.close-dialog')) button.addEventListener('click', () => button.closest('dialog').close());
$('password-nav').addEventListener('click', openPassword); $('profile-password').addEventListener('click', openPassword);
$('accounts-nav').addEventListener('click', () => showSection(false)); $('profile-nav').addEventListener('click', () => showSection(true));
$('create-user').addEventListener('click', () => openUser());
$('filters').addEventListener('submit', (event) => { event.preventDefault(); page = 1; loadUsers(); });
for (const id of ['filter-role', 'filter-status']) $(id).addEventListener('change', () => { page = 1; loadUsers(); });
$('refresh').addEventListener('click', () => { banner(''); reloadAdmin().catch((error) => banner(error.message)); });
$('previous').addEventListener('click', () => { page--; loadUsers(); }); $('next').addEventListener('click', () => { page++; loadUsers(); });
$('logout').addEventListener('click', async () => {
  $('logout').disabled = true;
  try { await api('/auth/logout', 'POST'); sessionStorage.removeItem('access_token'); location.replace('/ui/'); }
  catch (error) { banner(error.message); $('logout').disabled = false; }
});
function updateMe() {
  $('sidebar-name').textContent = me.full_name; $('sidebar-role').textContent = roleLabel(me.role_name); $('avatar').textContent = initials(me.full_name);
  drawProfile($('my-profile'), me);
}
async function start() {
  if (!token) { location.replace('/ui/'); return; }
  try {
    me = await api('/auth/me'); updateMe();
    const isAdmin = me.role_name === 'ADMIN'; $('accounts-nav').hidden = !isAdmin;
    document.title = (isAdmin ? 'Quản lý tài khoản' : 'Tài khoản của tôi') + ' · Trọ Việt';
    showSection(!isAdmin);
    if (isAdmin) await reloadAdmin();
  } catch (error) { banner(error.message); }
}
start();
