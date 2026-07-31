import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SharedArtifactPhase from './SharedArtifactPhase.vue'

function lockedDraft() {
  return {
    shared_artifact_id: 'artifact-1',
    kind: 'team_final',
    current_revision_id: 'revision-1',
    locked: false,
    current_revision: {
      revision_id: 'revision-1',
      content: {
        candidate_id: 'candidate-a',
        rationale: 'Current shared rationale.',
        confidence: 5,
        decision_status: 'tentative',
      },
      confirmed_roles: ['principal', 'teammate_1', 'teammate_2'],
      locked: false,
    },
  }
}

describe('SharedArtifactPhase', () => {
  it('shows all three confirmations and resets them after a new revision', async () => {
    const wrapper = mount(SharedArtifactPhase, {
      props: {
        kind: 'team_final',
        role: 'teammate_2',
        candidates: ['candidate-a', 'candidate-b', 'candidate-c'],
        artifact: lockedDraft(),
      },
    })

    expect(wrapper.text()).toContain('3 of 3 confirmed')

    await wrapper.get('input[value="candidate-b"]').setValue(true)
    await wrapper.get('[data-test="shared-rationale"]').setValue('The combined evidence now supports B.')
    await wrapper.get('[data-test="save-shared-revision"]').trigger('click')

    expect(wrapper.emitted('edit')[0][0]).toEqual({
      parent_revision_id: 'revision-1',
      content: {
        candidate_id: 'candidate-b',
        rationale: 'The combined evidence now supports B.',
        confidence: 5,
        decision_status: 'tentative',
        ratings: {},
      },
    })

    await wrapper.setProps({
      artifact: {
        ...lockedDraft(),
        current_revision_id: 'revision-2',
        locked_revision_id: null,
        locked: false,
        current_revision: {
          revision_id: 'revision-2',
          content: {
            candidate_id: 'candidate-b',
            rationale: 'The combined evidence now supports B.',
            confidence: 5,
            decision_status: 'tentative',
            ratings: {},
          },
          confirmed_roles: [],
          locked: false,
        },
      },
    })

    expect(wrapper.text()).toContain('0 of 3 confirmed')
  })

  it('confirms the current revision explicitly', async () => {
    const wrapper = mount(SharedArtifactPhase, {
      props: {
        kind: 'team_final',
        role: 'principal',
        candidates: ['candidate-a', 'candidate-b', 'candidate-c'],
        artifact: {
          ...lockedDraft(),
          locked: false,
          current_revision: {
            ...lockedDraft().current_revision,
            locked: false,
            confirmed_roles: ['teammate_1'],
          },
        },
      },
    })

    await wrapper.get('[data-test="confirm-shared-revision"]').trigger('click')

    expect(wrapper.emitted('confirm')[0][0]).toEqual('revision-1')
  })

  it('disables edit and confirmation controls independently from the server capabilities', () => {
    const wrapper = mount(SharedArtifactPhase, {
      props: {
        kind: 'team_final',
        role: 'principal',
        candidates: ['candidate-a'],
        artifact: lockedDraft(),
        canEdit: false,
        canConfirm: false,
      },
    })

    expect(wrapper.text()).toContain('Editing and confirmation are not available')
    expect(wrapper.get('[data-test="save-shared-revision"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="confirm-shared-revision"]').attributes('disabled')).toBeDefined()
  })
})
