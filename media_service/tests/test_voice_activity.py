from array import array

from media_service.app.voice_activity import VoiceActivityBuffer


def _pcm(amplitude, milliseconds, sample_rate=1000):
    samples = array('h', [amplitude] * (sample_rate * milliseconds // 1000))
    return samples.tobytes()


def test_voice_activity_emits_one_utterance_after_silence():
    detector = VoiceActivityBuffer(
        sample_rate=1000,
        threshold=200,
        min_speech_ms=200,
        end_silence_ms=300,
    )

    assert detector.feed(_pcm(0, 100)) == []
    assert detector.feed(_pcm(1000, 250)) == []
    assert detector.feed(_pcm(0, 200)) == []
    utterances = detector.feed(_pcm(0, 100))

    assert len(utterances) == 1
    assert utterances[0].start_ms == 100
    assert utterances[0].end_ms == 650
    assert len(utterances[0].pcm_s16le) == 1100


def test_voice_activity_discards_short_noise():
    detector = VoiceActivityBuffer(
        sample_rate=1000,
        threshold=200,
        min_speech_ms=200,
        end_silence_ms=300,
    )
    detector.feed(_pcm(1000, 50))
    assert detector.feed(_pcm(0, 300)) == []
