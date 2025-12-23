// 七夢学習アプリ - Firebase プッシュ通知

const FIREBASE_CONFIG = {
    apiKey: "AIzaSyDZN9IdxzDQzyWCOl-JwC1RSpgBnxvpBEY",
    authDomain: "nanami-learning.firebaseapp.com",
    projectId: "nanami-learning",
    storageBucket: "nanami-learning.firebasestorage.app",
    messagingSenderId: "626845653458",
    appId: "1:626845653458:web:c871bd3964b09cbe96900b"
};

const VAPID_KEY = "BMtZ_YN_ECEsoLBj6x8fKjemaj29FWaVhdGnsDHLVY2MNFCpfwYjYhpvy4wCmqSQeIRUS8WucUAC9s_cKt6e0Ds";

let messaging = null;

// テスト用関数（コンソールから呼び出し可能）
window.testNotification = function () {
    try {
        const testPayload = {
            notification: {
                title: "🔔 テスト通知",
                body: "これはテスト通知です。バナーと音が表示されれば成功！"
            },
            data: {
                type: "test",
                url: "/dashboard"
            }
        };
        console.log("テスト通知を表示します...");
        showLocalNotification(testPayload);
        // スマホでも確認できるようにアラートを表示
        setTimeout(() => {
            alert("テスト通知を送信しました！\n\n・ピンク色のバナーが画面上部に表示されましたか？\n・ピンポン音が鳴りましたか？");
        }, 500);
    } catch (e) {
        alert("エラーが発生しました: " + e.message);
        console.error("テスト通知エラー:", e);
    }
};

// Firebase初期化
async function initFirebase() {
    try {
        // Firebase SDKを動的にロード
        const { initializeApp } = await import('https://www.gstatic.com/firebasejs/9.0.0/firebase-app.js');
        const { getMessaging, getToken, onMessage } = await import('https://www.gstatic.com/firebasejs/9.0.0/firebase-messaging.js');

        const app = initializeApp(FIREBASE_CONFIG);
        messaging = getMessaging(app);

        // Service Workerを登録
        if ('serviceWorker' in navigator) {
            const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
            console.log('Service Worker 登録成功');
        }

        return { getToken, onMessage };
    } catch (error) {
        console.error('Firebase初期化エラー:', error);
        return null;
    }
}

// プッシュ通知の許可をリクエスト
async function requestPushPermission() {
    try {
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            console.log('通知が許可されませんでした');
            return null;
        }

        const firebase = await initFirebase();
        if (!firebase || !messaging) return null;

        // FCMトークンを取得
        const token = await firebase.getToken(messaging, { vapidKey: VAPID_KEY });
        console.log('FCMトークン取得:', token);

        // サーバーにトークンを保存
        await saveTokenToServer(token);

        // onMessageはsetupFirebaseMessaging()で一元管理するため、ここでは登録しない

        return token;
    } catch (error) {
        console.error('プッシュ通知設定エラー:', error);
        return null;
    }
}

// サーバーにトークンを保存
async function saveTokenToServer(token) {
    try {
        const response = await fetch('/api/save-fcm-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token })
        });
        if (response.ok) {
            console.log('FCMトークンをサーバーに保存しました');
        }
    } catch (error) {
        console.error('トークン保存エラー:', error);
    }
}

// ローカル通知表示
async function showLocalNotification(payload) {
    const title = payload.notification?.title || '七夢学習アプリ';
    const body = payload.notification?.body || '新着があります';
    const url = payload.data?.url || '/dashboard';
    const type = payload.data?.type || 'general';

    // ブラウザ通知を表示（許可されている場合）
    if (Notification.permission === 'granted') {
        const options = {
            body: body,
            icon: '/static/icon-192.png',
            badge: '/static/icon-192.png',
            vibrate: [200, 100, 200],
            tag: 'nanami-notification',
            data: { url: url }
        };

        try {
            // Service Worker経由で通知を表示（スマホ対応）
            const registration = await navigator.serviceWorker.getRegistration();
            if (registration) {
                await registration.showNotification(title, options);
            } else {
                // Service Workerがない場合は従来の方法を試す（PC向け）
                try {
                    const notification = new Notification(title, options);
                    notification.onclick = () => {
                        window.focus();
                        window.location.href = url;
                        notification.close();
                    };
                } catch (e) {
                    console.log('Notification APIエラー:', e);
                }
            }
        } catch (e) {
            console.log('通知表示エラー:', e);
        }
    }

    // アプリ内通知バナーを表示
    showInAppNotification(title, body, url);

    // 通知音を再生
    playNotificationSound();

    // ページを自動更新（リアルタイム反映）
    autoRefreshPage(type, url);
}

// ページ自動更新
function autoRefreshPage(type, url) {
    const currentPath = window.location.pathname;

    // ダッシュボードにいる場合は常に更新
    if (currentPath === '/dashboard' || currentPath === '/') {
        setTimeout(() => {
            window.location.reload();
        }, 1500); // 通知バナーが表示されてから1.5秒後に更新
        return;
    }

    // 通知タイプに応じた更新
    if (type === 'problem' && currentPath.includes('/problem')) {
        setTimeout(() => window.location.reload(), 1500);
    } else if (type === 'answer' && currentPath.includes('/problem')) {
        setTimeout(() => window.location.reload(), 1500);
    } else if (type === 'feedback' && currentPath.includes('/problem')) {
        setTimeout(() => window.location.reload(), 1500);
    } else if (type === 'announcement' && currentPath.includes('/announcement')) {
        setTimeout(() => window.location.reload(), 1500);
    }
}

// アプリ内通知バナー
function showInAppNotification(title, body, url) {
    // 既存のバナーを削除
    const existing = document.getElementById('in-app-notification');
    if (existing) existing.remove();

    // スタイルを追加（既に存在しない場合のみ）
    if (!document.getElementById('notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideDown {
                from { transform: translateY(-100%); opacity: 0; }
                to { transform: translateY(0); opacity: 1; }
            }
            .in-app-notification-container {
                position: fixed;
                top: 10px;
                left: 10px;
                right: 10px;
                background: linear-gradient(135deg, #e91e8c, #c4177a);
                color: white;
                padding: 16px;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                z-index: 99999;
                display: flex;
                align-items: flex-start;
                gap: 12px;
                cursor: pointer;
                animation: slideDown 0.3s ease-out;
            }
            @media (max-width: 768px) {
                .in-app-notification-container {
                    top: 5px;
                    left: 5px;
                    right: 5px;
                    padding: 12px;
                }
            }
            @supports (top: env(safe-area-inset-top)) {
                .in-app-notification-container {
                    top: calc(env(safe-area-inset-top) + 10px);
                }
            }
        `;
        document.head.appendChild(style);
    }

    const banner = document.createElement('div');
    banner.id = 'in-app-notification';
    banner.innerHTML = `
        <div class="in-app-notification-container">
            <span style="font-size: 1.5rem;">🔔</span>
            <div style="flex: 1; min-width: 0;">
                <div style="font-weight: 600;">${title}</div>
                <div style="font-size: 0.85rem; opacity: 0.9; margin-top: 2px; word-break: break-word;">${body}</div>
            </div>
            <button id="close-in-app-notification" style="padding: 8px; background: transparent; color: white; border: none; font-size: 1.5rem; cursor: pointer; line-height: 1;">×</button>
        </div>
    `;

    // アニメーション用CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideDown {
            from { transform: translateY(-100%); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);

    document.body.appendChild(banner);

    // クリックで遷移
    banner.querySelector('div').addEventListener('click', (e) => {
        if (e.target.id !== 'close-in-app-notification') {
            window.location.href = url;
        }
    });

    // 閉じるボタン
    document.getElementById('close-in-app-notification').addEventListener('click', () => {
        banner.remove();
    });

    // 5秒後に自動で消える
    setTimeout(() => {
        if (banner.parentNode) {
            banner.style.transition = 'opacity 0.3s, transform 0.3s';
            banner.style.opacity = '0';
            banner.style.transform = 'translateY(-20px)';
            setTimeout(() => banner.remove(), 300);
        }
    }, 5000);
}

// 通知音を再生
function playNotificationSound() {
    try {
        // 短い「ピンポン」音を生成
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();

        // 最初の音（ピン）
        const osc1 = audioContext.createOscillator();
        const gain1 = audioContext.createGain();
        osc1.connect(gain1);
        gain1.connect(audioContext.destination);
        osc1.frequency.value = 880; // A5
        gain1.gain.setValueAtTime(0.3, audioContext.currentTime);
        gain1.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.15);
        osc1.start(audioContext.currentTime);
        osc1.stop(audioContext.currentTime + 0.15);

        // 2番目の音（ポン）
        const osc2 = audioContext.createOscillator();
        const gain2 = audioContext.createGain();
        osc2.connect(gain2);
        gain2.connect(audioContext.destination);
        osc2.frequency.value = 1100; // C#6
        gain2.gain.setValueAtTime(0.3, audioContext.currentTime + 0.15);
        gain2.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);
        osc2.start(audioContext.currentTime + 0.15);
        osc2.stop(audioContext.currentTime + 0.3);
    } catch (e) {
        console.log('通知音再生エラー:', e);
    }
}

// 通知設定UI表示
function showNotificationPrompt() {
    if (!('Notification' in window)) {
        console.log('このブラウザは通知をサポートしていません');
        return;
    }

    if (Notification.permission === 'default') {
        // 通知許可バナーを表示
        const banner = document.createElement('div');
        banner.id = 'notification-banner';
        banner.innerHTML = `
            <div style="position: fixed; bottom: 80px; left: 16px; right: 16px; background: linear-gradient(135deg, #e91e8c, #c4177a); color: white; padding: 16px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); z-index: 1001; display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.5rem;">🔔</span>
                <div style="flex: 1;">
                    <div style="font-weight: 600;">通知を有効にしますか？</div>
                    <div style="font-size: 0.85rem; opacity: 0.9;">新着問題やフィードバックをお知らせします</div>
                </div>
                <button id="enable-notifications" style="padding: 8px 16px; background: white; color: #e91e8c; border: none; border-radius: 8px; font-weight: 600; cursor: pointer;">有効にする</button>
                <button id="dismiss-notifications" style="padding: 8px; background: transparent; color: white; border: none; font-size: 1.2rem; cursor: pointer;">×</button>
            </div>
        `;
        document.body.appendChild(banner);

        document.getElementById('enable-notifications').addEventListener('click', async () => {
            banner.remove();
            await requestPushPermission();
        });

        document.getElementById('dismiss-notifications').addEventListener('click', () => {
            banner.remove();
            localStorage.setItem('notification-dismissed', 'true');
        });
    } else if (Notification.permission === 'granted') {
        requestPushPermission();
    }
}

// ページロード時に初期化
document.addEventListener('DOMContentLoaded', function () {
    // 通知が許可されている場合は常にonMessageをセットアップ
    if (Notification.permission === 'granted') {
        setupFirebaseMessaging();
    }

    // 通知プロンプトの表示（まだ却下されていない場合）
    if (!localStorage.getItem('notification-dismissed') && Notification.permission === 'default') {
        setTimeout(showNotificationPrompt, 2000);
    }
});

// Firebaseメッセージングのセットアップ（常に呼ばれる）
async function setupFirebaseMessaging() {
    try {
        const firebase = await initFirebase();
        if (!firebase || !messaging) {
            console.log('Firebase初期化に失敗');
            return;
        }

        // フォアグラウンドでのメッセージ受信を常にセットアップ
        firebase.onMessage(messaging, (payload) => {
            console.log('🔔 フォアグラウンド通知を受信:', payload);
            showLocalNotification(payload);
        });

        console.log('✅ Firebaseメッセージング準備完了');

        // トークンも取得しておく（更新される可能性があるため）
        try {
            const token = await firebase.getToken(messaging, { vapidKey: VAPID_KEY });
            if (token) {
                await saveTokenToServer(token);
            }
        } catch (e) {
            console.log('トークン取得エラー:', e);
        }
    } catch (error) {
        console.error('Firebaseセットアップエラー:', error);
    }
}