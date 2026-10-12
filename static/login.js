'use strict';
const $ = (id) => document.getElementById(id);
$('show-password').addEventListener('click', () => {
  const visible = $('password').type === 'password';
  $('password').type = visible ? 'text' : 'password';
  $('show-password').textContent = visible ? 'Ẩn' : 'Hiện';
  $('show-password').setAttribute('aria-pressed', String(visible));
  $('show-password').setAttribute('aria-label', visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu');
});
$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('login-button');
  button.disabled = true;
  button.textContent = 'Đang đăng nhập…';
  $('message').textContent = '';
  try {
    const response = await fetch('/auth/login', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({identifier: $('identifier').value.trim(), password: $('password').value})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Kiểm tra lại email/SĐT và mật khẩu.');
    sessionStorage.setItem('access_token', data.access_token);
    $('password').value = '';
    location.replace('/ui/admin.html');
  } catch (error) {
    $('message').textContent = error instanceof TypeError ? 'Không kết nối được API. Kiểm tra backend đang chạy.' : error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Đăng nhập →';
  }
});
if (sessionStorage.getItem('access_token')) {
  fetch('/auth/me', {headers: {Authorization: 'Bearer ' + sessionStorage.getItem('access_token')}})
    .then((response) => {
      if (response.ok) location.replace('/ui/admin.html');
      else if (response.status === 401) sessionStorage.removeItem('access_token');
    }).catch(() => {});
}
const notice = new URLSearchParams(location.search).get('notice');
if (notice === 'password-changed') { $('message').textContent = 'Đổi mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.'; $('message').style.color = '#13786b'; }
if (notice === 'expired') $('message').textContent = 'Phiên đăng nhập đã hết hạn hoặc bị thu hồi. Vui lòng đăng nhập lại.';
