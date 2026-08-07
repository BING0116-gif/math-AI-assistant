<template>
  <section ref="container" class="galaxy" aria-label="可旋转的三维课程知识图谱">
    <canvas ref="canvas" @pointerdown="pauseMotion" @pointermove="onPointerMove" @click="onCanvasClick" />
    <div class="hud"><span>拖动旋转</span><span>滚轮缩放</span><span>点击节点进入</span></div>
    <div v-for="label in labels" :key="label.id" class="node-label" :class="label.type" :style="label.style">{{ label.name }}</div>
    <div class="view-controls"><button type="button" aria-label="重置图谱视角" @click="resetView">重置视角</button><button type="button" :aria-pressed="!motionPaused" @click="motionPaused = !motionPaused">{{ motionPaused ? '播放动效' : '暂停动效' }}</button></div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const props = defineProps({ tree: { type: Object, required: true } })
const emit = defineEmits(['select-point', 'select-branch'])
const container = ref(null); const canvas = ref(null); const motionPaused = ref(false); const labels = ref([])
let scene; let camera; let renderer; let controls; let raycaster; let pointer; let animationId; let resizeObserver; let meshes = []; let labelNodes = []; let started = false
const typeColors = { course: 0x6366f1, chapter: 0x38bdf8, section: 0xa78bfa, point: 0xf59e0b }

const graphNodes = computed(() => {
  if (!props.tree) return []
  const items = [{ id: props.tree.course.id, name: props.tree.course.name, type: 'course', data: props.tree.course, position: new THREE.Vector3(0, 0, 0) }]
  props.tree.chapters.forEach((chapter, chapterIndex) => {
    const chapterPosition = new THREE.Vector3(0, 3.8 + chapterIndex * 1.2, -1.2)
    items.push({ id: chapter.id, name: chapter.name, type: 'chapter', data: chapter, parentId: props.tree.course.id, position: chapterPosition })
    chapter.children.forEach((section, sectionIndex) => {
      const angle = (sectionIndex / Math.max(chapter.children.length, 1)) * Math.PI * 2 - Math.PI / 2
      const sectionPosition = new THREE.Vector3(Math.cos(angle) * 6.5, 1.2 + Math.sin(angle) * 1.6, Math.sin(angle) * 4.3 - 0.5)
      items.push({ id: section.id, name: section.name, type: 'section', data: section, position: sectionPosition, parentId: chapter.id })
      section.knowledge_points.forEach((point, pointIndex) => {
        const pointAngle = angle + (pointIndex - (section.knowledge_points.length - 1) / 2) * 0.26
        const radius = 2.6 + pointIndex * 0.14
        items.push({ id: point.id, name: point.name, type: 'point', data: point, parentId: section.id, position: new THREE.Vector3(sectionPosition.x + Math.cos(pointAngle) * radius, sectionPosition.y + (pointIndex - 1) * .92, sectionPosition.z + Math.sin(pointAngle) * radius) })
      })
    })
  })
  return items
})

function init() {
  if (!container.value || !canvas.value || started) return
  started = true; scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x07111f, .026)
  camera = new THREE.PerspectiveCamera(45, 1, .1, 100); camera.position.set(0, 5, 19)
  renderer = new THREE.WebGLRenderer({ canvas: canvas.value, antialias: true, alpha: true }); renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setClearColor(0x07111f, 1)
  controls = new OrbitControls(camera, canvas.value); controls.enableDamping = true; controls.dampingFactor = .06; controls.minDistance = 9; controls.maxDistance = 30; controls.target.set(0, 1, 0)
  scene.add(new THREE.HemisphereLight(0xbfd7ff, 0x07111f, 2.2)); const light = new THREE.PointLight(0x8b5cf6, 28, 35); light.position.set(0, 7, 8); scene.add(light)
  raycaster = new THREE.Raycaster(); pointer = new THREE.Vector2(); rebuild(); resizeObserver = new ResizeObserver(resize); resizeObserver.observe(container.value); resize(); animate()
}
function rebuild() {
  if (!scene) return
  meshes.forEach(({ mesh, line }) => { scene.remove(mesh); if (line) scene.remove(line) }); meshes = []; labelNodes = []
  const nodesById = new Map(graphNodes.value.map(node => [node.id, node]))
  graphNodes.value.forEach(node => {
    const radius = node.type === 'course' ? 1.25 : node.type === 'chapter' ? .9 : node.type === 'section' ? .68 : .42
    const material = new THREE.MeshStandardMaterial({ color: typeColors[node.type], emissive: typeColors[node.type], emissiveIntensity: node.type === 'point' ? .45 : .25, roughness: .25, metalness: .25 })
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 36, 24), material); mesh.position.copy(node.position); mesh.userData = node; scene.add(mesh)
    const glow = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.28, 24, 16), new THREE.MeshBasicMaterial({ color: typeColors[node.type], transparent: true, opacity: .11, side: THREE.BackSide })); mesh.add(glow)
    let line; if (node.parentId && nodesById.has(node.parentId)) { const geometry = new THREE.BufferGeometry().setFromPoints([nodesById.get(node.parentId).position, node.position]); line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: typeColors[node.type], transparent: true, opacity: .48 })); scene.add(line) }
    meshes.push({ mesh, line }); labelNodes.push({ node, mesh })
  })
}
function resize() { if (!container.value || !renderer) return; const { width, height } = container.value.getBoundingClientRect(); camera.aspect = width / height; camera.updateProjectionMatrix(); renderer.setSize(width, height, false) }
function animate() { animationId = requestAnimationFrame(animate); if (!motionPaused.value) { scene.rotation.y += .0016 } controls.update(); updateLabels(); renderer.render(scene, camera) }
function updateLabels() { if (!camera) return; labels.value = labelNodes.map(({ node, mesh }) => { const p = mesh.position.clone(); scene.localToWorld(p); p.project(camera); const visible = p.z < 1; return { id: node.id, name: node.name, type: node.type, style: { left: `${(p.x * .5 + .5) * 100}%`, top: `${(-p.y * .5 + .5) * 100}%`, opacity: visible ? 1 : 0 } } }) }
function onPointerMove(event) { const bounds = canvas.value.getBoundingClientRect(); pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1; pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1; raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObjects(meshes.map(item => item.mesh))[0]; canvas.value.style.cursor = hit ? 'pointer' : 'grab' }
function onCanvasClick() { raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObjects(meshes.map(item => item.mesh))[0]; if (!hit) return; const node = hit.object.userData; motionPaused.value = true; if (node.type === 'point') emit('select-point', node.data.id); else if (node.type === 'course') emit('select-branch', props.tree.chapters[0]); else emit('select-branch', node.data) }
function pauseMotion() { motionPaused.value = true }
function resetView() { camera.position.set(0, 5, 19); controls.target.set(0, 1, 0); controls.update(); motionPaused.value = false }
watch(graphNodes, () => nextTick(rebuild), { deep: true }); onMounted(init); onBeforeUnmount(() => { cancelAnimationFrame(animationId); resizeObserver?.disconnect(); controls?.dispose(); renderer?.dispose() })
</script>

<style scoped>
.galaxy { position:relative; height:min(72vh,720px); min-height:520px; overflow:hidden; border:1px solid rgba(129,140,248,.28); border-radius:24px; background:#07111f; box-shadow:0 20px 50px rgba(30,41,59,.16); }.galaxy canvas { display:block; width:100%; height:100%; touch-action:none; }.hud { position:absolute; inset:18px auto auto 18px; display:flex; gap:8px; flex-wrap:wrap; max-width:280px; pointer-events:none; }.hud span,.view-controls button { border:1px solid rgba(191,219,254,.25); border-radius:999px; background:rgba(7,17,31,.72); color:#dbeafe; padding:7px 10px; font-size:12px; backdrop-filter:blur(8px); }.view-controls { position:absolute; right:18px; bottom:18px; display:flex; gap:8px; }.view-controls button { cursor:pointer; font:inherit; }.node-label { position:absolute; transform:translate(-50%, -50%); pointer-events:none; color:#f8fafc; font-size:12px; font-weight:700; white-space:nowrap; text-shadow:0 2px 8px #020617; transition:opacity .2s; }.node-label.course { font-size:18px; }.node-label.chapter { font-size:14px; } @media (max-width:768px) { .galaxy { height:62vh; min-height:460px; border-radius:18px; }.hud { display:none; }.view-controls { right:10px; bottom:10px; }.view-controls button { padding:8px; } }
</style>
