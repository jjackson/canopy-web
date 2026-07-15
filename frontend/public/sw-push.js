// Injected into the generated service worker (vite-plugin-pwa's injectManifest
// would replace the whole SW; importScripts keeps its precaching intact).
//
// Without a 'push' listener the payload arrives and NOTHING happens — no error,
// no notification, just silence. That is the single most confusing way for push
// to be broken, so this file is small and does exactly two things.

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = {}
  }
  const title = data.title || 'Canopy'
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || '',
      icon: 'icons/icon-192.png',
      badge: 'icons/icon-192.png',
      // Collapse to one notification per agent: five separate buzzes for the
      // same agent is how you get muted.
      tag: title,
      renotify: true,
      data: { url: data.url || '/supervisor' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(event.notification.data.url, self.location.origin).href
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((cls) => {
      // Focus an open tab if there is one rather than stacking another.
      for (const c of cls) {
        if (c.url === target && 'focus' in c) return c.focus()
      }
      return self.clients.openWindow(target)
    }),
  )
})
