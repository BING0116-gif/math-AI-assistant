<template>
  <section ref="container" class="galaxy" aria-label="可旋转的三维课程知识图谱">
    <canvas ref="canvas" @pointerdown="pauseMotion" @pointermove="onPointerMove" @click="onCanvasClick" />
    <div class="hud"><span>拖动旋转</span><span>滚轮缩放</span><span>点击节点查看</span></div>
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
const typeColors = { course: 0xC8913D, chapter: 0x5F947C, section: 0x417E7A, point: 0x5A8A8A }

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
  started = true; scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x0B1924, .024)
  camera = new THREE.PerspectiveCamera(45, 1, .1, 100); camera.position.set(0, 5, 19)
  renderer = new THREE.WebGLRenderer({ canvas: canvas.value, antialias: true, alpha: true }); renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2)); renderer.setClearColor(0x0B1924, 1)
  controls = new OrbitControls(camera, canvas.value); controls.enableDamping = true; controls.dampingFactor = .06; controls.minDistance = 9; controls.maxDistance = 30; controls.target.set(0, 1, 0)
  scene.add(new THREE.HemisphereLight(0xd4c9a8, 0x0B1924, 1.6)); const light = new THREE.PointLight(0xc8913d, 12, 30); light.position.set(0, 7, 8); scene.add(light)
  raycaster = new THREE.Raycaster(); pointer = new THREE.Vector2(); rebuild(); resizeObserver = new ResizeObserver(resize); resizeObserver.observe(container.value); resize(); animate()
}
function rebuild() {
  if (!scene) return
  meshes.forEach(({ mesh, line }) => { scene.remove(mesh); if (line) scene.remove(line) }); meshes = []; labelNodes = []
  const nodesById = new Map(graphNodes.value.map(node => [node.id, node]))
  graphNodes.value.forEach(node => {
    const radius = node.type === 'course' ? 1.25 : node.type === 'chapter' ? .9 : node.type === 'section' ? .68 : .42
    const material = new THREE.MeshStandardMaterial({ color: typeColors[node.type], emissive: typeColors[node.type], emissiveIntensity: node.type === 'course' ? .18 : .12, roughness: .35, metalness: .15 })
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(radius, 36, 24), material); mesh.position.copy(node.position); mesh.userData = node; scene.add(mesh)
    const glow = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.2, 24, 16), new THREE.MeshBasicMaterial({ color: typeColors[node.type], transparent: true, opacity: .07, side: THREE.BackSide })); mesh.add(glow)
    let line; if (node.parentId && nodesById.has(node.parentId)) { const geometry = new THREE.BufferGeometry().setFromPoints([nodesById.get(node.parentId).position, node.position]); line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: 0x5A7A7A, transparent: true, opacity: .28 })); scene.add(line) }
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
.galaxy { position:relative; height:100%; min-height:520px; overflow:hidden; border-radius:16px; background:#0B1924; }.galaxy canvas { display:block; width:100%; height:100%; touch-action:none; }.hud { position:absolute; inset:14px auto auto 14px; display:flex; gap:6px; flex-wrap:wrap; pointer-events:none; }.hud span { border:1px solid rgba(90,122,122,.35); border-radius:999px; background:rgba(11,25,36,.72); color:rgba(180,196,188,.82); padding:5px 9px; font-size:11px; backdrop-filter:blur(8px); }.view-controls { position:absolute; right:14px; bottom:14px; display:flex; gap:6px; }.view-controls button { border:1px solid rgba(90,122,122,.35); border-radius:999px; background:rgba(11,25,36,.72); color:rgba(180,196,188,.82); padding:5px 10px; font-size:11px; cursor:pointer; font:inherit; backdrop-filter:blur(8px); transition:background .2s, border-color .2s; }.view-controls button:hover { border-color:rgba(95,148,124,.5); background:rgba(11,25,36,.9); }.node-label { position:absolute; transform:translate(-50%, -50%); pointer-events:none; color:#d8e0da; font-size:11px; font-weight:600; white-space:nowrap; text-shadow:0 1px 6px rgba(0,0,0,.6); transition:opacity .2s; letter-spacing:.02em; }.node-label.course { font-size:16px; font-weight:700; color:#d4b87a; }.node-label.chapter { font-size:13px; color:#a8c4b4; } @media (max-width:768px) { .galaxy { min-height:400px; border-radius:12px; }.hud { display:none; }.view-controls { right:10px; bottom:10px; }.view-controls button { padding:6px 8px; font-size:10px; } }
</style>