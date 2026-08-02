function participantSample(participant) {
  return {
    identity: String(participant?.identity || participant?.name || ''),
    is_speaking: Boolean(participant?.isSpeaking),
    audio_level: Number.isFinite(participant?.audioLevel) ? participant.audioLevel : 0,
  }
}

export function createLiveKitStatsAdapter(room, options = {}) {
  const now = options.now || (() => new Date())
  return {
    async sample() {
      const remotes = [...(room?.remoteParticipants?.values?.() || [])]
        .map(participantSample)
        .sort((left, right) => left.identity.localeCompare(right.identity))
      return {
        sampled_at: now().toISOString(),
        connection_state: String(room?.state || room?.connectionState || 'disconnected'),
        remote_participant_count: remotes.length,
        local: participantSample(room?.localParticipant),
        remotes,
      }
    },
  }
}
