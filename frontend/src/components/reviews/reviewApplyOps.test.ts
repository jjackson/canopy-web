import { describe, it, expect } from 'vitest'
import { applyReviewOps, projectBuildOrder } from './reviewApplyOps'
import type { ReviewNarrationItem } from '../../api/reviews'
import type { PendingReviewOp } from './reviewEditorTypes'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ORIGINAL: ReviewNarrationItem[] = [
  {
    scene: 1,
    id: 'scene-1',
    text: 'Original narration one',
    features: [
      { id: 'feat-a', description: 'Feature A', verify: 'check A' },
    ],
  },
  {
    scene: 2,
    id: 'scene-2',
    text: 'Original narration two',
    features: [],
  },
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('applyReviewOps', () => {
  it('returns effective scenes with no ops (identity)', () => {
    const scenes = applyReviewOps(ORIGINAL, [])
    expect(scenes).toHaveLength(2)
    expect(scenes[0].id).toBe('scene-1')
    expect(scenes[0].narration).toBe('Original narration one')
    expect(scenes[0].deleted).toBe(false)
    expect(scenes[0].features[0].id).toBe('feat-a')
    expect(scenes[0].features[0].feedback).toBe('')
  })

  it('edit-narration updates the narration text', () => {
    const ops: PendingReviewOp[] = [
      { op: 'edit-narration', sceneId: 'scene-1', text: 'Edited narration' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes[0].narration).toBe('Edited narration')
    // other scene unchanged
    expect(scenes[1].narration).toBe('Original narration two')
  })

  it('edit-feature updates description and verify', () => {
    const ops: PendingReviewOp[] = [
      { op: 'edit-feature', sceneId: 'scene-1', featureId: 'feat-a', field: 'description', value: 'New desc' },
      { op: 'edit-feature', sceneId: 'scene-1', featureId: 'feat-a', field: 'verify', value: 'new verify' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    const feat = scenes[0].features[0]
    expect(feat.description).toBe('New desc')
    expect(feat.verify).toBe('new verify')
  })

  it('set-feature-feedback sets feedback', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-feature-feedback', sceneId: 'scene-1', featureId: 'feat-a', text: 'nice feature' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes[0].features[0].feedback).toBe('nice feature')
  })

  it('add-feature appends a new empty feature', () => {
    const ops: PendingReviewOp[] = [
      { op: 'add-feature', sceneId: 'scene-2', featureId: 'new-1' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    const scene2 = scenes.find((s) => s.id === 'scene-2')!
    expect(scene2.features).toHaveLength(1)
    expect(scene2.features[0].id).toBe('new-1')
    expect(scene2.features[0].description).toBe('')
    expect(scene2.features[0].deleted).toBe(false)
  })

  it('delete-feature marks feature as deleted', () => {
    const ops: PendingReviewOp[] = [
      { op: 'delete-feature', sceneId: 'scene-1', featureId: 'feat-a' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes[0].features[0].deleted).toBe(true)
  })

  it('add-scene appends a new empty scene', () => {
    const ops: PendingReviewOp[] = [
      { op: 'add-scene', sceneId: 'new-1', title: 'Brand New Scene' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes).toHaveLength(3)
    const newScene = scenes[2]
    expect(newScene.id).toBe('new-1')
    expect(newScene.title).toBe('Brand New Scene')
    expect(newScene.narration).toBe('')
    expect(newScene.features).toHaveLength(0)
    expect(newScene.deleted).toBe(false)
  })

  it('delete-scene marks scene as deleted', () => {
    const ops: PendingReviewOp[] = [
      { op: 'delete-scene', sceneId: 'scene-1' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes[0].deleted).toBe(true)
    expect(scenes[1].deleted).toBe(false)
  })

  it('set-scene-feedback sets scene feedback', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-scene-feedback', sceneId: 'scene-2', text: 'great scene' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    expect(scenes[1].feedback).toBe('great scene')
  })

  it('set-overall-feedback is a noop in applyReviewOps (handled by caller)', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-overall-feedback', text: 'global feedback' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    // Scenes unchanged
    expect(scenes).toHaveLength(2)
    expect(scenes[0].narration).toBe('Original narration one')
  })

  it('multiple ops applied in order — edit then delete', () => {
    const ops: PendingReviewOp[] = [
      { op: 'edit-narration', sceneId: 'scene-1', text: 'Changed' },
      { op: 'delete-scene', sceneId: 'scene-1' },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    // narration was edited, then scene deleted — deleted wins at render time
    expect(scenes[0].narration).toBe('Changed')
    expect(scenes[0].deleted).toBe(true)
  })

  it('set-build-order is a noop in applyReviewOps (handled by projectBuildOrder)', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-build-order', orderedSceneIds: ['scene-2', 'scene-1'] },
    ]
    const scenes = applyReviewOps(ORIGINAL, ops)
    // Scenes unchanged — build order is projected separately.
    expect(scenes).toHaveLength(2)
    expect(scenes[0].id).toBe('scene-1')
    expect(scenes[1].id).toBe('scene-2')
  })

  it('does not mutate the original items', () => {
    const orig = JSON.parse(JSON.stringify(ORIGINAL)) as ReviewNarrationItem[]
    const ops: PendingReviewOp[] = [
      { op: 'edit-narration', sceneId: 'scene-1', text: 'Mutated?' },
      { op: 'add-scene', sceneId: 'new-1', title: 'Extra' },
    ]
    applyReviewOps(orig, ops)
    // original should be unchanged
    expect(orig[0].text).toBe('Original narration one')
    expect(orig).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// projectBuildOrder tests
// ---------------------------------------------------------------------------

describe('projectBuildOrder', () => {
  // Helper: build effective scenes from original + ops.
  function effectiveFor(ops: PendingReviewOp[]) {
    return applyReviewOps(ORIGINAL, ops)
  }

  it('defaults to narration order when no op and no initialBuildOrder', () => {
    const effective = effectiveFor([])
    const order = projectBuildOrder(ORIGINAL, [], null, effective)
    expect(order).toEqual(['scene-1', 'scene-2'])
  })

  it('uses initialBuildOrder when no set-build-order op', () => {
    const effective = effectiveFor([])
    const order = projectBuildOrder(ORIGINAL, [], ['scene-2', 'scene-1'], effective)
    expect(order).toEqual(['scene-2', 'scene-1'])
  })

  it('set-build-order op overrides initialBuildOrder', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-build-order', orderedSceneIds: ['scene-2', 'scene-1'] },
    ]
    const effective = effectiveFor(ops)
    // initialBuildOrder would be ['scene-1', 'scene-2'] but the op wins.
    const order = projectBuildOrder(ORIGINAL, ops, ['scene-1', 'scene-2'], effective)
    expect(order).toEqual(['scene-2', 'scene-1'])
  })

  it('last set-build-order op wins (coalescing: only one in buffer)', () => {
    // The reducer coalesces to one, but simulate the last-one-wins logic.
    const ops: PendingReviewOp[] = [
      { op: 'set-build-order', orderedSceneIds: ['scene-2', 'scene-1'] },
    ]
    const effective = effectiveFor(ops)
    const order = projectBuildOrder(ORIGINAL, ops, null, effective)
    expect(order).toEqual(['scene-2', 'scene-1'])
  })

  it('newly added scene is appended to the end of the build order', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-build-order', orderedSceneIds: ['scene-2', 'scene-1'] },
      { op: 'add-scene', sceneId: 'new-1', title: 'Brand New' },
    ]
    const effective = effectiveFor(ops)
    const order = projectBuildOrder(ORIGINAL, ops, null, effective)
    // new-1 is not in the set-build-order list, so it appends.
    expect(order).toEqual(['scene-2', 'scene-1', 'new-1'])
  })

  it('deleted scene is dropped from the build order', () => {
    const ops: PendingReviewOp[] = [
      { op: 'set-build-order', orderedSceneIds: ['scene-2', 'scene-1'] },
      { op: 'delete-scene', sceneId: 'scene-1' },
    ]
    const effective = effectiveFor(ops)
    const order = projectBuildOrder(ORIGINAL, ops, null, effective)
    expect(order).toEqual(['scene-2'])
  })

  it('defaulting to narration order: added scene appends, deleted drops', () => {
    const ops: PendingReviewOp[] = [
      { op: 'add-scene', sceneId: 'new-42', title: 'Extra Scene' },
      { op: 'delete-scene', sceneId: 'scene-2' },
    ]
    const effective = effectiveFor(ops)
    // No set-build-order op, no initialBuildOrder → falls back to narration order
    // then reconciles: scene-2 deleted → drop it; new-42 added → append.
    const order = projectBuildOrder(ORIGINAL, ops, null, effective)
    expect(order).toEqual(['scene-1', 'new-42'])
  })
})
