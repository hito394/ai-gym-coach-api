'use strict';

// ── State ───────────────────────────────────────────────────────────────────
const S = {
  token:  localStorage.getItem('gl_token')  || null,
  userId: Number(localStorage.getItem('gl_uid')) || null,
};

// ── API helper ───────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers['Authorization'] = `Bearer ${S.token}`;
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
  if (res.status === 401) { doLogout(); return null; }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────────
async function doLogin(email, password) {
  const d = await api('POST', '/v1/auth/token', { email, password });
  saveAuth(d);
}
async function doRegister(email, password) {
  const d = await api('POST', '/v1/auth/register', { email, password });
  saveAuth(d);
}
function saveAuth(d) {
  S.token = d.access_token; S.userId = d.user_id;
  localStorage.setItem('gl_token', d.access_token);
  localStorage.setItem('gl_uid', String(d.user_id));
  screen('home');
}
function doLogout() {
  S.token = null; S.userId = null;
  localStorage.removeItem('gl_token'); localStorage.removeItem('gl_uid');
  screen('auth');
}

// ── Exercises ─────────────────────────────────────────────────────────────────
const EXERCISES = [
  ['squat','スクワット'],['back_squat','バックスクワット'],['front_squat','フロントスクワット'],
  ['goblet_squat','ゴブレットスクワット'],['lunge','ランジ'],['bulgarian_split_squat','ブルガリアンSS'],
  ['deadlift','デッドリフト'],['romanian_deadlift','RDL'],['sumo_deadlift','スモウDL'],
  ['hip_thrust','ヒップスラスト'],['bench_press','ベンチプレス'],['incline_bench_press','インクラインBP'],
  ['dumbbell_bench_press','DBベンチプレス'],['overhead_press','オーバーヘッドプレス'],
  ['push_up','プッシュアップ'],['dips','ディップス'],['pull_up','プルアップ'],
  ['chin_up','チンアップ'],['lat_pulldown','ラットプルダウン'],['barbell_row','バーベルロウ'],
  ['seated_row','シーテッドロウ'],['face_pull','フェイスプル'],['lateral_raise','サイドレイズ'],
  ['front_raise','フロントレイズ'],['biceps_curl','アームカール'],['hammer_curl','ハンマーカール'],
  ['triceps_pushdown','プッシュダウン'],['skull_crusher','スカルクラッシャー'],
  ['leg_press','レッグプレス'],['leg_curl','レッグカール'],['leg_extension','レッグエクステンション'],
  ['calf_raise','カーフレイズ'],['plank','プランク'],['ab_wheel','腹筋ローラー'],
];
function exKey(name) {
  const m = EXERCISES.find(([,n]) => n === name);
  return m ? m[0] : name.toLowerCase().replace(/\s+/g,'_');
}

// ── Screen router ─────────────────────────────────────────────────────────────
function screen(name, data) {
  const app = document.getElementById('app');
  if (name === 'auth') { app.innerHTML = ''; app.appendChild(authScreen()); return; }
  const wrap = el('div','app-wrapper');
  const content = el('div','screen-content');
  wrap.appendChild(content);
  wrap.appendChild(navBar(name));
  app.innerHTML = '';
  app.appendChild(wrap);
  if      (name === 'home')    homeScreen(content);
  else if (name === 'history') historyScreen(content);
  else if (name === 'weight')  weightScreen(content);
}
window.goScreen = screen;

// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}
function showErr(id, msg) { const e = document.getElementById(id); if(e) e.textContent = msg; }

// ── Bottom nav ────────────────────────────────────────────────────────────────
function navBar(active) {
  const nav = el('nav','bottom-nav');
  nav.innerHTML = [
    ['home',    '💪', '記録'],
    ['history', '📋', '履歴'],
    ['weight',  '⚖️', '体重'],
  ].map(([id,icon,label]) =>
    `<button class="nav-btn ${active===id?'active':''}" onclick="goScreen('${id}')">
       <span class="nav-icon">${icon}</span>
       <span class="nav-label">${label}</span>
     </button>`
  ).join('');
  return nav;
}

// ── Auth screen ───────────────────────────────────────────────────────────────
function authScreen() {
  const div = el('div','auth-screen');
  div.innerHTML = `
    <div class="logo">💪</div>
    <h1 class="logo-text">GymLog</h1>
    <div class="auth-tabs">
      <button class="auth-tab active" id="tab-in"  onclick="authTab('login')">ログイン</button>
      <button class="auth-tab"        id="tab-up"  onclick="authTab('register')">新規登録</button>
    </div>
    <form class="auth-form" id="auth-form" onsubmit="handleAuth(event)">
      <input type="email"    name="email"    placeholder="メールアドレス" required autocomplete="email">
      <input type="password" name="password" placeholder="パスワード（8文字以上）" required minlength="8" autocomplete="current-password">
      <button class="btn-primary" id="auth-btn">ログイン</button>
      <p id="auth-err" class="error-msg"></p>
    </form>`;
  return div;
}
window.authTab = function(mode) {
  document.getElementById('tab-in').classList.toggle('active', mode==='login');
  document.getElementById('tab-up').classList.toggle('active', mode==='register');
  document.getElementById('auth-btn').textContent = mode==='login' ? 'ログイン' : '新規登録';
  document.getElementById('auth-form').dataset.mode = mode;
};
window.handleAuth = async function(e) {
  e.preventDefault();
  const f = e.target, mode = f.dataset.mode || 'login';
  const btn = document.getElementById('auth-btn');
  btn.disabled = true; showErr('auth-err','');
  try {
    mode==='register'
      ? await doRegister(f.email.value, f.password.value)
      : await doLogin(f.email.value, f.password.value);
  } catch(err) { showErr('auth-err', err.message); btn.disabled = false; }
};

// ── Home screen ───────────────────────────────────────────────────────────────
async function homeScreen(container) {
  container.innerHTML = '<div class="loading">読み込み中…</div>';
  let session = null;
  try { session = await api('GET', `/v1/workouts/sessions/active/${S.userId}`); } catch {}
  container.innerHTML = '';
  container.appendChild(homeContent(session));
}

function homeContent(session) {
  const div = el('div');
  if (!session) {
    div.innerHTML = `
      <div class="screen-header">
        <h2>今日のトレーニング</h2>
        <button class="icon-btn" onclick="confirmLogout()">⚙️</button>
      </div>
      <div class="start-card">
        <div class="start-icon">🏋️</div>
        <p>新しいワークアウトを始めましょう</p>
        <button class="btn-primary btn-large" onclick="startWorkout()">ワークアウト開始</button>
      </div>`;
  } else {
    const sets = session.sets || [];
    const vol = sets.reduce((s, r) => s + r.weight * r.reps, 0);
    div.innerHTML = `
      <div class="screen-header">
        <h2>記録中 🔴</h2>
        <button class="btn-outline btn-danger-outline" onclick="finishWorkout('${session.session_key}')">終了</button>
      </div>
      <div class="session-stats">
        <div class="stat"><span class="stat-val">${sets.length}</span><span class="stat-label">セット</span></div>
        <div class="stat"><span class="stat-val">${vol.toFixed(0)}</span><span class="stat-label">総ボリューム(kg)</span></div>
      </div>
      <div class="add-set-card">
        <h3>セット追加</h3>
        <form id="set-form" onsubmit="addSet(event,'${session.session_key}')">
          <div class="form-row">
            <input list="ex-list" name="exercise" placeholder="種目を選択または入力" required autocomplete="off">
            <datalist id="ex-list">${EXERCISES.map(([,n])=>`<option value="${n}">`).join('')}</datalist>
          </div>
          <div class="form-row two-col">
            <div><label class="input-label">重量 (kg)</label><input class="compact-input" type="number" name="weight" step="0.5" min="0" placeholder="60" required></div>
            <div><label class="input-label">回数</label><input class="compact-input" type="number" name="reps" min="1" placeholder="5" required></div>
          </div>
          <div class="form-row two-col mt-8">
            <div><label class="input-label">RPE (任意)</label><input class="compact-input" type="number" name="rpe" step="0.5" min="1" max="10" placeholder="8"></div>
            <div><label class="input-label">気分 1-10</label><input class="compact-input" type="number" name="feeling" min="1" max="10" placeholder="8"></div>
          </div>
          <div class="mt-14"><button class="btn-primary" type="submit">追加</button></div>
          <p id="set-err" class="error-msg"></p>
        </form>
      </div>
      ${sets.length ? `<p class="section-title">このセッションのセット</p>
        <div class="sets-list">
          ${sets.map((s,i)=>`
            <div class="set-row">
              <span class="set-num">${i+1}</span>
              <span class="set-exercise">${s.exercise}</span>
              <span class="set-detail">${s.weight}kg×${s.reps}${s.rpe?` @${s.rpe}`:''}</span>
            </div>`).join('')}
        </div>` : '<p class="empty-msg">セットを追加してください</p>'}`;
  }
  return div;
}

window.startWorkout = async function() {
  try {
    const s = await api('POST', '/v1/workouts/sessions', { user_id: S.userId });
    const c = document.querySelector('.screen-content');
    if (c) { c.innerHTML=''; c.appendChild(homeContent(s)); }
  } catch(e) { alert(e.message); }
};

window.addSet = async function(e, key) {
  e.preventDefault();
  const f = e.target;
  const name = f.exercise.value;
  const exKey_ = exKey(name);
  const weight = parseFloat(f.weight.value);
  const reps   = parseInt(f.reps.value);
  const rpe    = f.rpe.value     ? parseFloat(f.rpe.value) : null;
  const feel   = f.feeling.value ? parseInt(f.feeling.value) : null;
  showErr('set-err','');
  try {
    await api('POST', `/v1/workouts/sessions/${key}/sets`, {
      exercise_key: exKey_, exercise_name: name, weight, reps, rpe,
    });
    if (feel) api('POST','/v1/form/log',{user_id:S.userId,exercise_key:exKey_,feeling:feel}).catch(()=>{});
    const c = document.querySelector('.screen-content');
    if (c) homeScreen(c);
  } catch(err) { showErr('set-err', err.message); }
};

window.finishWorkout = async function(key) {
  if (!confirm('ワークアウトを終了しますか？')) return;
  try {
    await api('POST', `/v1/workouts/sessions/${key}/finish`, {});
    const c = document.querySelector('.screen-content');
    if (c) homeScreen(c);
  } catch(e) { alert(e.message); }
};

window.confirmLogout = function() {
  if (confirm('ログアウトしますか？')) doLogout();
};

// ── History screen ────────────────────────────────────────────────────────────
async function historyScreen(container) {
  container.innerHTML = `<div class="screen-header"><h2>トレーニング履歴</h2></div><div class="loading">読み込み中…</div>`;
  try {
    const data = await api('GET', `/v1/workouts/history/${S.userId}`);
    const sessions = (data && data.sessions) || [];
    const list = sessions.length === 0
      ? '<p class="empty-msg">まだ記録がありません</p>'
      : sessions.map(s => {
          const d = new Date(s.performed_at || '');
          const dateStr = isNaN(d) ? s.performed_at : d.toLocaleDateString('ja-JP',{month:'short',day:'numeric',weekday:'short'});
          const exList = s.entries
            ? [...new Set(s.entries.map(e => e.exercise))].slice(0,4).join(' · ')
            : '';
          return `<div class="history-card">
            <div class="history-date">${dateStr}</div>
            <div class="history-exercises">${exList || '（種目なし）'}</div>
            <div class="history-meta">${s.total_sets}セット &nbsp;·&nbsp; ${(s.total_volume||0).toFixed(0)} kg vol</div>
          </div>`;
        }).join('');
    container.innerHTML = `<div class="screen-header"><h2>トレーニング履歴</h2></div><div class="list-container">${list}</div>`;
  } catch(e) {
    container.innerHTML = `<div class="screen-header"><h2>トレーニング履歴</h2></div><p class="error-msg">${e.message}</p>`;
  }
}

// ── Weight screen ─────────────────────────────────────────────────────────────
async function weightScreen(container) {
  container.innerHTML = `<div class="screen-header"><h2>体重記録</h2></div><div class="loading">読み込み中…</div>`;
  try {
    const logs = await api('GET', `/v1/users/${S.userId}/body-weight`) || [];
    container.innerHTML = `
      <div class="screen-header"><h2>体重記録</h2></div>
      <div class="weight-form-card">
        <form onsubmit="logWeight(event)">
          <div class="weight-input-row">
            <input class="weight-big-input" type="number" id="w-input" step="0.1" min="20" max="300" placeholder="70.0" required>
            <span class="weight-unit">kg</span>
          </div>
          <button class="btn-primary" type="submit">記録する</button>
          <p id="w-err" class="error-msg"></p>
        </form>
      </div>
      <div class="list-container">
        ${logs.length === 0 ? '<p class="empty-msg">まだ記録がありません</p>' :
          logs.slice(0,30).map((l,i) => {
            const d = new Date(l.measured_at||'');
            const dateStr = isNaN(d) ? '' : d.toLocaleDateString('ja-JP',{month:'short',day:'numeric'});
            const prev = logs[i+1];
            const diff = prev ? (l.weight_kg - prev.weight_kg) : null;
            const diffHtml = diff !== null
              ? `<span class="${diff>=0?'weight-diff-pos':'weight-diff-neg'}">${diff>=0?'+':''}${diff.toFixed(1)}</span>`
              : '';
            return `<div class="weight-row"><span class="weight-date">${dateStr}</span><span class="weight-val">${l.weight_kg} kg${diffHtml}</span></div>`;
          }).join('')}
      </div>`;
  } catch(e) {
    container.innerHTML = `<div class="screen-header"><h2>体重記録</h2></div><p class="error-msg">${e.message}</p>`;
  }
}

window.logWeight = async function(e) {
  e.preventDefault();
  const w = parseFloat(document.getElementById('w-input').value);
  showErr('w-err','');
  try {
    await api('POST', `/v1/users/${S.userId}/body-weight`, { weight_kg: w });
    const c = document.querySelector('.screen-content');
    if (c) weightScreen(c);
  } catch(err) { showErr('w-err', err.message); }
};

// ── Init ──────────────────────────────────────────────────────────────────────
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
screen(S.token && S.userId ? 'home' : 'auth');
