'use client'

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'
import { getUserIdentity, type UserIdentity } from '@/lib/user-identity'

export type CursorPosition = {
  x: number
  y: number
  slide_index: number | null
}

export type PresenceUser = {
  user_id: string
  display_name: string
  editing_slide: number | null
}

type PresenceContextValue = {
  users: PresenceUser[]
  cursors: Map<string, CursorPosition & { display_name: string }>
  myIdentity: UserIdentity
  startEditing: (slideIndex: number) => void
  stopEditing: () => void
  broadcastCursor: (x: number, y: number, slideIndex: number | null) => void
  broadcastSlideSave: (slideIndex: number, html: string) => void
  onRemoteSlideUpdate: React.MutableRefObject<((slideIndex: number, html: string, userId: string) => void) | null>
  onRemoteContentUpdate: React.MutableRefObject<((html: string, message: string) => void) | null>
}

const PresenceContext = createContext<PresenceContextValue | null>(null)

export function usePresence() {
  const ctx = useContext(PresenceContext)
  if (!ctx) throw new Error('usePresence must be used within PresenceProvider')
  return ctx
}

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001'

export function PresenceProvider({ sessionId, children }: { sessionId: number; children: React.ReactNode }) {
  const [users, setUsers] = useState<PresenceUser[]>([])
  const [cursors, setCursors] = useState<Map<string, CursorPosition & { display_name: string }>>(new Map())
  const socketRef = useRef<Socket | null>(null)
  const identityRef = useRef<UserIdentity | null>(null)
  const onRemoteSlideUpdate = useRef<((slideIndex: number, html: string, userId: string) => void) | null>(null)
  const onRemoteContentUpdate = useRef<((html: string, message: string) => void) | null>(null)

  // Stable identity per tab
  if (typeof window !== 'undefined' && !identityRef.current) {
    identityRef.current = getUserIdentity()
  }
  const myIdentity = identityRef.current ?? { userId: 'ssr', displayName: 'Unknown' }

  useEffect(() => {
    if (typeof window === 'undefined' || !sessionId) return

    const socket = io(BACKEND_URL, {
      transports: ['websocket', 'polling'],
    })
    socketRef.current = socket

    socket.on('connect', () => {
      socket.emit('join_session', {
        session_id: sessionId,
        user_id: myIdentity.userId,
        display_name: myIdentity.displayName,
      })
    })

    socket.on('presence:users_changed', (data: { session_id: number; users: PresenceUser[] }) => {
      if (data.session_id === sessionId) {
        setUsers(data.users)
        // Remove cursors for users who left
        const activeIds = new Set(data.users.map(u => u.user_id))
        setCursors(prev => {
          let changed = false
          const next = new Map(prev)
          for (const uid of next.keys()) {
            if (!activeIds.has(uid)) { next.delete(uid); changed = true }
          }
          return changed ? next : prev
        })
      }
    })

    socket.on('presence:editing_changed', () => {
      // Users list update handles this via users_changed; editing_changed is
      // available for more granular UI updates if needed later.
    })

    socket.on('presence:slide_updated', (data: { session_id: number; slide_index: number; html: string; user_id: string }) => {
      if (data.session_id === sessionId) {
        onRemoteSlideUpdate.current?.(data.slide_index, data.html, data.user_id)
      }
    })

    socket.on('presence:content_updated', (data: { session_id: number; html: string; message: string }) => {
      if (data.session_id === sessionId) {
        onRemoteContentUpdate.current?.(data.html, data.message)
      }
    })

    socket.on('presence:cursor_moved', (data: { session_id: number; user_id: string; display_name: string; x: number; y: number; slide_index: number | null }) => {
      if (data.session_id === sessionId) {
        setCursors(prev => {
          const next = new Map(prev)
          next.set(data.user_id, { x: data.x, y: data.y, slide_index: data.slide_index, display_name: data.display_name })
          return next
        })
      }
    })

    return () => {
      socket.emit('leave_session', { session_id: sessionId })
      socket.disconnect()
      socketRef.current = null
      setUsers([])
    }
  }, [sessionId, myIdentity.userId, myIdentity.displayName])

  const startEditing = useCallback((slideIndex: number) => {
    socketRef.current?.emit('presence:start_editing', { session_id: sessionId, slide_index: slideIndex })
  }, [sessionId])

  const stopEditing = useCallback(() => {
    socketRef.current?.emit('presence:stop_editing', { session_id: sessionId })
  }, [sessionId])

  const broadcastCursor = useCallback((x: number, y: number, slideIndex: number | null) => {
    socketRef.current?.emit('presence:cursor_moved', { session_id: sessionId, x, y, slide_index: slideIndex })
  }, [sessionId])

  const broadcastSlideSave = useCallback((slideIndex: number, html: string) => {
    socketRef.current?.emit('presence:slide_saved', { session_id: sessionId, slide_index: slideIndex, html })
  }, [sessionId])

  return (
    <PresenceContext.Provider value={{ users, cursors, myIdentity, startEditing, stopEditing, broadcastCursor, broadcastSlideSave, onRemoteSlideUpdate, onRemoteContentUpdate }}>
      {children}
    </PresenceContext.Provider>
  )
}
