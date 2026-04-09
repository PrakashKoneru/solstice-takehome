const ADJECTIVES = [
  'Blue', 'Teal', 'Amber', 'Coral', 'Jade', 'Ruby', 'Sage', 'Gold',
  'Mint', 'Rose', 'Plum', 'Onyx', 'Lime', 'Cyan', 'Fern', 'Iris',
]

const ANIMALS = [
  'Fox', 'Panda', 'Owl', 'Wolf', 'Bear', 'Lynx', 'Hawk', 'Deer',
  'Hare', 'Swan', 'Crane', 'Otter', 'Raven', 'Finch', 'Seal', 'Wren',
]

function randomPick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

function generateId(): string {
  return crypto.randomUUID()
}

function generateDisplayName(): string {
  return `${randomPick(ADJECTIVES)} ${randomPick(ANIMALS)}`
}

export type UserIdentity = {
  userId: string
  displayName: string
}

const STORAGE_KEY = 'presence_identity'

export function getUserIdentity(): UserIdentity {
  if (typeof window === 'undefined') {
    return { userId: 'ssr', displayName: 'Unknown' }
  }

  const stored = sessionStorage.getItem(STORAGE_KEY)
  if (stored) {
    try {
      return JSON.parse(stored)
    } catch {
      // fall through to generate new
    }
  }

  const identity: UserIdentity = {
    userId: generateId(),
    displayName: generateDisplayName(),
  }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(identity))
  return identity
}
