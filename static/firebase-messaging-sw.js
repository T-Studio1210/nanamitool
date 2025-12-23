// Firebase Messaging Service Worker
// このファイルはプッシュ通知をバックグラウンドで受け取るために必要です

importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-messaging-compat.js');

// Firebase設定
firebase.initializeApp({
    apiKey: "AIzaSyDZN9IdxzDQzyWCOl-JwC1RSpgBnxvpBEY",
    authDomain: "nanami-learning.firebaseapp.com",
    projectId: "nanami-learning",
    storageBucket: "nanami-learning.firebasestorage.app",
    messagingSenderId: "626845653458",
    appId: "1:626845653458:web:c871bd3964b09cbe96900b"
});

const messaging = firebase.messaging();

// バックグラウンドでプッシュ通知を受け取った時の処理
messaging.onBackgroundMessage((payload) => {
    console.log('バックグラウンド通知を受信:', payload);

    const notificationTitle = payload.notification?.title || '七夢学習アプリ';
    const notificationOptions = {
        body: payload.notification?.body || '新着があります',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        vibrate: [200, 100, 200],
        data: payload.data,
        actions: [
            { action: 'open', title: '開く' }
        ]
    };

    self.registration.showNotification(notificationTitle, notificationOptions);
});

// 通知クリック時の処理
self.addEventListener('notificationclick', (event) => {
    event.notification.close();

    const urlToOpen = event.notification.data?.url || '/dashboard';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // 既に開いているタブがあればフォーカス
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        client.navigate(urlToOpen);
                        return client.focus();
                    }
                }
                // なければ新しいタブで開く
                if (clients.openWindow) {
                    return clients.openWindow(urlToOpen);
                }
            })
    );
});
