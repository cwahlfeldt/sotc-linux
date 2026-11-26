/* Linux rwlocks behind the PS4 pointer-to-handle ABI.
 *
 * sotc: the hot path takes no process-wide lock. Before, every acquire and every unlock of every
 * guest rwlock took one global registry mutex (twice per acquire), walked the list of all
 * rwlocks to validate the handle, and allocated/freed a holder record: the game's readers of
 * unrelated rwlocks queued behind each other on that mutex and on malloc. Now:
 *   - handles are slots of one arena, so a handle is validated by its address alone (inside the
 *     arena, on a slot boundary) and its slot state; a stray pointer is refused without being read;
 *   - each thread keeps the rwlocks it holds in a small table of its own (recursion, ownership and
 *     reader/writer errors as before: EDEADLK, EBUSY, EPERM, EAGAIN);
 *   - each lock counts its users (holds plus acquisitions in progress, all threads), and destroy
 *     moves the slot LIVE -> DYING and back when anyone uses it (EBUSY), the same answers as the
 *     registry gave. Waiting happens in the host rwlock, as before.
 * The arena and the free list are only locked to create and destroy. */
#define _GNU_SOURCE
#include "runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <errno.h>
#include <limits.h>
#include <sys/mman.h>

enum { SLOT_FREE = 0, SLOT_LIVE = 1, SLOT_DYING = 2 }; /* an untouched arena page reads as FREE */
typedef struct Rwlock {
    union {
        pthread_rwlock_t native;    /* LIVE or DYING */
        struct Rwlock *next_free;   /* FREE, on the free list */
    };
    uint32_t state;                 /* SLOT_*, __atomic */
    uint32_t users;                 /* holds + acquisitions in progress, all threads, __atomic */
} __attribute__((aligned(64))) Rwlock; /* one cache line per lock on glibc x86-64 */
_Static_assert(sizeof(Rwlock) % 64 == 0, "rwlock slots are whole cache lines");
typedef struct { int64_t seconds, nanoseconds; } GuestTime;

/* 2^18 slots: 16 MiB of address space, pages touched only as slots are handed out. Destroyed
 * slots are reused, so this bounds the rwlocks alive at once, not the ones ever created. */
#define ARENA_SLOTS (UINT32_C(1) << 18)
static Rwlock *arena;                  /* __atomic: set once, under arena_lock */
static uint32_t arena_used;            /* slots handed out at least once (arena_lock) */
static Rwlock *free_slots;             /* destroyed slots (arena_lock) */
static pthread_mutex_t arena_lock = PTHREAD_MUTEX_INITIALIZER;
static size_t created, destroyed;      /* arena_lock */
static size_t reads, writes, unlocks;  /* RUNTIME_STAT */

static int32_t error(int e) {
    if (!e) return 0;
    unsigned code;
    switch(e) {
    case EPERM: code=1; break;
    case EDEADLK: code=11; break;
    case ENOMEM: code=12; break;
    case EBUSY: code=16; break;
    case EINVAL: code=22; break;
    case EAGAIN: code=35; break;
    case ETIMEDOUT: code=60; break;
    default: fprintf(stderr,"STOP: unmapped rwlock error %d\n",e); exit(21);
    }
    return (int32_t)(UINT32_C(0x80020000)|code);
}
static inline void spin_relax(void) {
#if defined(__x86_64__)
    __builtin_ia32_pause();
#endif
}

/* ---- slots ---- */
/* The slot a handle names, or NULL when it is not one (never dereferenced to find out). */
static Rwlock *slot_of(const Rwlock *handle) {
    const Rwlock *base = __atomic_load_n(&arena, __ATOMIC_ACQUIRE);
    const uintptr_t p = (uintptr_t)handle, b = (uintptr_t)base;
    if (!base || p < b || p - b >= (uintptr_t)ARENA_SLOTS * sizeof(Rwlock) || (p - b) % sizeof(Rwlock))
        return NULL;
    return (Rwlock *)(uintptr_t)handle;
}
/* Requires arena_lock. */
static int create_locked(Rwlock **out) {
    if (!arena) {
        void *p = mmap(NULL, (size_t)ARENA_SLOTS * sizeof(Rwlock), PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
        if (p == MAP_FAILED) return ENOMEM;
        __atomic_store_n(&arena, (Rwlock *)p, __ATOMIC_RELEASE);
    }
    Rwlock *r = free_slots;
    if (r) free_slots = r->next_free;
    else if (arena_used < ARENA_SLOTS) r = &arena[arena_used++];
    else {
        static int told;
        if (!told++) fprintf(stderr, "Runtime: %u rwlocks alive at once: no slot left\n", (unsigned)ARENA_SLOTS);
        return ENOMEM;
    }
    int e = pthread_rwlock_init(&r->native, NULL);
    if (e) { r->next_free = free_slots; free_slots = r; return e; }
    /* `users` is left alone: a stale handle's acquire may be counting itself in and out right
     * now (it sees FREE and leaves); every destroy found it at 0 before freeing the slot. */
    __atomic_store_n(&r->state, SLOT_LIVE, __ATOMIC_RELEASE);
    ++created;
    *out = r;
    return 0;
}
/* The slot behind a handle; a statically initialized (NULL) handle gets its lock on first use. */
static int handle_get(Rwlock **handle, Rwlock **out) {
    Rwlock *h = __atomic_load_n(handle, __ATOMIC_ACQUIRE);
    if (!h) {
        int e = 0;
        pthread_mutex_lock(&arena_lock);
        h = *handle;
        if (!h) {
            e = create_locked(&h);
            if (!e) __atomic_store_n(handle, h, __ATOMIC_RELEASE);
        }
        pthread_mutex_unlock(&arena_lock);
        if (e) return e;
    }
    *out = slot_of(h);
    return *out ? 0 : EINVAL;
}
/* Counts the caller among the lock's users while it is live (0: not a live lock). A destroy in
 * progress (DYING) is waited out: it goes back to LIVE (someone uses the lock) or frees the slot.
 * Sequentially consistent with rw_destroy: either destroy sees this user, or this sees DYING. */
static int enter(Rwlock *r) {
    for (;;) {
        __atomic_fetch_add(&r->users, 1, __ATOMIC_SEQ_CST);
        const uint32_t state = __atomic_load_n(&r->state, __ATOMIC_SEQ_CST);
        if (state == SLOT_LIVE) return 1;
        __atomic_fetch_sub(&r->users, 1, __ATOMIC_SEQ_CST);
        if (state != SLOT_DYING) return 0;
        while (__atomic_load_n(&r->state, __ATOMIC_ACQUIRE) == SLOT_DYING) spin_relax();
    }
}
static void leave(Rwlock *r) { __atomic_fetch_sub(&r->users, 1, __ATOMIC_RELEASE); }

/* ---- what the calling thread holds ---- */
typedef struct { Rwlock *lock; unsigned readers, writer; } Held;
static _Thread_local Held *held;
static _Thread_local unsigned held_count, held_capacity;
static pthread_key_t held_key;
static pthread_once_t held_once = PTHREAD_ONCE_INIT;
static int held_key_ready;
static void held_release(void *table) { free(table); }
static void held_key_create(void) { held_key_ready = !pthread_key_create(&held_key, held_release); }
static Held *held_find(const Rwlock *r) {
    for (unsigned i = 0; i < held_count; ++i) if (held[i].lock == r) return &held[i];
    return NULL;
}
static Held *held_add(Rwlock *r) {
    if (held_count == held_capacity) {
        const unsigned capacity = held_capacity ? held_capacity * 2 : 8;
        Held *grown = realloc(held, capacity * sizeof(*held));
        if (!grown) return NULL;
        held = grown; held_capacity = capacity;
        pthread_once(&held_once, held_key_create);
        if (held_key_ready) pthread_setspecific(held_key, held); /* freed when the thread exits */
    }
    held[held_count] = (Held){.lock = r};
    return &held[held_count++];
}
/* Drops the entry once the thread holds the lock no more (h is invalid afterwards). */
static void held_forget(Held *h) {
    if (h->readers || h->writer) return;
    *h = held[--held_count];
}

/* ---- guest API ---- */
static ABI int32_t rw_init(Rwlock **out, void *const *attr, const char *name) {
    (void)name;
    if (!out || (attr && !*attr)) return error(EINVAL);
    if (attr) { fputs("STOP: non-default PS4 rwlock attributes are not implemented\n",stderr); exit(21); }
    /* POSIX allows uninitialized storage, so never read *out during init. */
    Rwlock *r = NULL;
    pthread_mutex_lock(&arena_lock);
    int e = create_locked(&r);
    pthread_mutex_unlock(&arena_lock);
    if (!e) *out = r;
    return error(e);
}
enum Operation { READ, WRITE, TRY_READ, TRY_WRITE, TIMED_READ, TIMED_WRITE };
static int32_t acquire(Rwlock **handle, enum Operation op, const GuestTime *time) {
    if (!handle) return error(EINVAL);
    const int writer=op==WRITE || op==TRY_WRITE || op==TIMED_WRITE;
    const int attempt=op==TRY_READ || op==TRY_WRITE;
    const int timed=op==TIMED_READ || op==TIMED_WRITE;
    Rwlock *r = NULL;
    int e = handle_get(handle, &r);
    if (e) return error(e);
    Held *h = held_find(r);
    if (h && (h->writer || (writer && h->readers))) return error(attempt ? EBUSY : EDEADLK);
    if (h && h->readers==UINT_MAX) return error(EAGAIN);
    if (!enter(r)) return error(EINVAL);
    if (!h && !(h = held_add(r))) { leave(r); return error(ENOMEM); }
    /* Timed operations first try the lock, matching POSIX timeout validation. */
    if (attempt || timed) e=writer ? pthread_rwlock_trywrlock(&r->native) : pthread_rwlock_tryrdlock(&r->native);
    else e=writer ? pthread_rwlock_wrlock(&r->native) : pthread_rwlock_rdlock(&r->native);
    if (timed && e==EBUSY) {
        if (!time || time->nanoseconds<0 || time->nanoseconds>=1000000000) e=EINVAL;
        else {
            struct timespec deadline={.tv_sec=(time_t)time->seconds,.tv_nsec=(long)time->nanoseconds};
            e=writer ? pthread_rwlock_timedwrlock(&r->native,&deadline) : pthread_rwlock_timedrdlock(&r->native,&deadline);
        }
    }
    if (e) { held_forget(h); leave(r); return error(e); }
    if (writer) { h->writer=1; RUNTIME_STAT(writes); }
    else { ++h->readers; RUNTIME_STAT(reads); }
    return 0;
}
static ABI int32_t rw_read(Rwlock **r) { return acquire(r,READ,NULL); }
static ABI int32_t rw_write(Rwlock **r) { return acquire(r,WRITE,NULL); }
static ABI int32_t rw_tryread(Rwlock **r) { return acquire(r,TRY_READ,NULL); }
static ABI int32_t rw_trywrite(Rwlock **r) { return acquire(r,TRY_WRITE,NULL); }
static ABI int32_t rw_timedread(Rwlock **r,const GuestTime *t) { return acquire(r,TIMED_READ,t); }
static ABI int32_t rw_timedwrite(Rwlock **r,const GuestTime *t) { return acquire(r,TIMED_WRITE,t); }
static ABI int32_t rw_unlock(Rwlock **handle) {
    if (!handle) return error(EINVAL);
    Rwlock *r = slot_of(__atomic_load_n(handle, __ATOMIC_ACQUIRE));
    if (!r || __atomic_load_n(&r->state, __ATOMIC_ACQUIRE) == SLOT_FREE) return error(EINVAL);
    Held *h = held_find(r);
    if (!h || (!h->readers && !h->writer)) return error(EPERM);
    const int e = pthread_rwlock_unlock(&r->native);
    if (e) return error(e);
    if (h->writer) h->writer=0; else --h->readers;
    RUNTIME_STAT(unlocks);
    held_forget(h);
    leave(r);
    return 0;
}
static ABI int32_t rw_destroy(Rwlock **handle) {
    if (!handle) return error(EINVAL);
    Rwlock *h = __atomic_load_n(handle, __ATOMIC_ACQUIRE);
    if (!h) return 0;
    Rwlock *r = slot_of(h);
    if (!r) return error(EINVAL);
    uint32_t state = SLOT_LIVE;
    if (!__atomic_compare_exchange_n(&r->state, &state, SLOT_DYING, 0, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST))
        return error(state == SLOT_DYING ? EBUSY : EINVAL); /* another destroy, or not a live lock */
    if (__atomic_load_n(&r->users, __ATOMIC_SEQ_CST)) {
        __atomic_store_n(&r->state, SLOT_LIVE, __ATOMIC_RELEASE);
        return error(EBUSY);
    }
    const int e = pthread_rwlock_destroy(&r->native);
    if (e) { __atomic_store_n(&r->state, SLOT_LIVE, __ATOMIC_RELEASE); return error(e); }
    pthread_mutex_lock(&arena_lock);
    __atomic_store_n(&r->state, SLOT_FREE, __ATOMIC_RELEASE);
    r->next_free = free_slots; free_slots = r;
    ++destroyed;
    pthread_mutex_unlock(&arena_lock);
    *handle = (Rwlock *)(uintptr_t)1;
    return 0;
}
uintptr_t runtime_rwlock_resolve(const char *name) {
    if (!strcmp(name,"6ULAa0fq4jA")) return (uintptr_t)rw_init;
    if (!strcmp(name,"BB+kb08Tl9A")) return (uintptr_t)rw_destroy;
    if (!strcmp(name,"Ox9i0c7L5w0")) return (uintptr_t)rw_read;
    if (!strcmp(name,"mqdNorrB+gI")) return (uintptr_t)rw_write;
    if (!strcmp(name,"XD3mDeybCnk")) return (uintptr_t)rw_tryread;
    if (!strcmp(name,"bIHoZCTomsI")) return (uintptr_t)rw_trywrite;
    if (!strcmp(name,"+L98PIbGttk")) return (uintptr_t)rw_unlock;
    if (!strcmp(name,"iPtZRWICjrM")) return (uintptr_t)rw_timedread;
    if (!strcmp(name,"adh--6nIqTk")) return (uintptr_t)rw_timedwrite;
    return 0;
}
void runtime_rwlock_report(void) {
    pthread_mutex_lock(&arena_lock);
    const size_t made = created, gone = destroyed;
    pthread_mutex_unlock(&arena_lock);
    printf("Runtime: rwlocks created=%zu, destroyed=%zu, reads~%zu, writes~%zu, unlocks~%zu\n", made, gone,
           RUNTIME_STAT_READ(reads), RUNTIME_STAT_READ(writes), RUNTIME_STAT_READ(unlocks));
}
