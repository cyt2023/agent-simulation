<script setup>
import { Bot, Headphones, MicOff, UserRound } from '@lucide/vue'

defineProps({
  role: { type: String, required: true },
  label: { type: String, required: true },
  state: { type: String, default: 'waiting' },
  active: Boolean,
  local: Boolean,
  muted: Boolean,
  proxy: Boolean,
  placeholder: Boolean,
})
</script>

<template>
  <article
    class="participant-seat"
    data-participant-seat
    :data-role="role"
    :data-state="state"
    :data-placeholder="placeholder ? 'true' : undefined"
    :class="{ active: active && !placeholder, proxy, placeholder }"
  >
    <div class="avatar" aria-hidden="true">
      <Headphones v-if="placeholder" :size="30" />
      <Bot v-else-if="proxy" :size="30" />
      <UserRound v-else :size="30" />
    </div>
    <div class="seat-copy">
      <strong>{{ label }}</strong>
      <span v-if="local" class="local-label">You</span>
      <small>{{ placeholder ? 'Not in the room' : active ? 'Speaking' : state === 'connected' ? 'Listening' : 'Waiting to join' }}</small>
    </div>
    <MicOff v-if="local && muted" class="seat-state" :size="18" aria-label="Microphone muted" />
    <Headphones v-else class="seat-state" :size="18" aria-hidden="true" />
  </article>
</template>

<style scoped>
.participant-seat { min-width:0; min-height:164px; display:grid; grid-template-rows:1fr auto; justify-items:center; align-items:center; gap:.75rem; padding:1.15rem; border:1px solid #3c494f; border-radius:6px; background:#222d32; color:#eef3f4; }
.participant-seat.active { border-color:#46a58b; box-shadow:0 0 0 3px rgba(70,165,139,.16); }
.participant-seat.proxy { background:#1d302f; border-color:#376a63; }
.participant-seat.placeholder { border-style:dashed; background:#1b2529; color:#bdc8cc; }
.avatar { width:68px; height:68px; display:grid; place-items:center; border-radius:50%; background:#3a464c; color:#c8d2d6; }
.active .avatar { background:#285b4f; color:#e3f4ee; }
.proxy .avatar { background:#28504b; color:#c7e9df; }
.placeholder .avatar { background:#2a3439; color:#89999f; }
.seat-copy { min-width:0; display:grid; justify-items:center; gap:.2rem; text-align:center; }
.seat-copy strong { max-width:100%; font-size:.96rem; overflow-wrap:anywhere; }
.seat-copy small { color:#9eacb2; font-size:.76rem; }
.local-label { padding:.1rem .35rem; border-radius:4px; background:#354148; color:#d7e0e3; font-size:.68rem; font-weight:700; text-transform:uppercase; }
.seat-state { position:absolute; justify-self:end; align-self:start; color:#9eacb2; }
.participant-seat { position:relative; }
@media (max-width:680px) { .participant-seat { min-height:132px; grid-template-columns:52px 1fr auto; grid-template-rows:1fr; justify-items:start; text-align:left; } .avatar { width:52px; height:52px; } .seat-copy { justify-items:start; text-align:left; } .seat-state { position:static; } }
</style>
