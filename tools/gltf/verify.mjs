// Check the compressed GLBs against the site data, then write uncompressed
// copies for the Blender re-import check (its importer cannot read meshopt).
//
//   node tools/gltf/verify.mjs
//
// Exits non-zero on the first file that fails. Every failure is printed.

import { readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { NodeIO, Primitive } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RAW = join(ROOT, 'blender', 'out', 'export');
const MODELS = join(ROOT, 'site', 'public', 'models');
const DATA = join(ROOT, 'site', 'src', 'data');
const BUDGET = { lod0: 30e6, lod1: 5e6, edges: 3e6 };
const TRIANGLES = { lod0: [900e3, 1400e3], lod1: [150e3, 200e3] };

const json = (name) => JSON.parse(readFileSync(join(DATA, name), 'utf8'));
const close = (a, b, tol = 2e-4) => a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) <= tol);
const IDENTITY = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const glOffset = (o) => [o[0], o[2], -o[1]];

let failures = 0;
function fail(file, msg) {
	failures++;
	console.log(`VERIFY FAIL ${file}: ${msg}`);
}

async function main() {
	await MeshoptDecoder.ready;
	await MeshoptEncoder.ready;
	const io = new NodeIO()
		.registerExtensions(ALL_EXTENSIONS)
		.registerDependencies({ 'meshopt.decoder': MeshoptDecoder, 'meshopt.encoder': MeshoptEncoder });
	const parts = json('parts.json');
	const mount = json('mount.json');
	const stations = json('stations.json');
	const model = json('model.json');
	const byNode = new Map(parts.map((p) => [p.node, p]));
	const assemblies = new Set(parts.map((p) => p.assembly));
	console.log(`VERIFY parts.json ${parts.length} parts, ${assemblies.size} assemblies`);

	for (const key of ['lod0', 'lod1', 'edges']) {
		const file = `rj28_${key}.glb`;
		const path = join(MODELS, file);
		const bytes = statSync(path).size;
		const doc = await io.read(path);
		const root = doc.getRoot();
		const before = failures;
		const ext = root.listExtensionsRequired().map((e) => e.extensionName);
		if (!ext.includes('EXT_meshopt_compression')) fail(file, 'not meshopt-compressed');
		if (bytes > BUDGET[key]) fail(file, `${bytes} bytes is over the ${BUDGET[key] / 1e6} MB budget`);
		if (model.files[key].bytes !== bytes) fail(file, 'model.json byte size is stale');

		const nodes = root.listNodes();
		const named = new Map(nodes.map((n) => [n.getName(), n]));
		if (named.size !== nodes.length) fail(file, 'duplicate node names');
		const scene = root.listScenes()[0];
		const top = scene.listChildren().map((n) => n.getName());
		const asmNodes = top.filter((n) => /^RJ28-\d\d_/.test(n));
		if (asmNodes.length !== 17) fail(file, `${asmNodes.length} assembly nodes at the scene root, expected 17`);
		const wantTop = key === 'edges' ? 17 : 18;
		if (top.length !== wantTop) fail(file, `${top.length} root nodes, expected ${wantTop}`);

		// every part in parts.json is a node, and nothing else is
		const partNodes = nodes.filter((n) => /^RJ28-\d\d-\d\d\d_/.test(n.getName()));
		if (partNodes.length !== parts.length) fail(file, `${partNodes.length} part nodes, parts.json has ${parts.length}`);
		const missing = parts.filter((p) => !named.has(p.node)).map((p) => p.node);
		if (missing.length) fail(file, `${missing.length} parts.json nodes missing, e.g. ${missing.slice(0, 3).join(', ')}`);
		const unknown = partNodes.filter((n) => !byNode.has(n.getName())).map((n) => n.getName());
		if (unknown.length) fail(file, `${unknown.length} part nodes not in parts.json, e.g. ${unknown.slice(0, 3).join(', ')}`);

		let triangles = 0;
		let noColor = 0;
		let badMode = 0;
		let badAttr = 0;
		let moved = 0;
		let badExtras = 0;
		let badParent = 0;
		let unsnapped = 0;
		const materials = new Set();
		const elev = new Set(mount.groups.elev.nodes);
		const trav = new Set(mount.groups.trav.nodes);
		for (const node of partNodes) {
			const p = byNode.get(node.getName());
			if (!p) continue;
			const parent = node.getParentNode();
			if (!parent || !/^RJ28-\d\d_/.test(parent.getName()) || parent.getParentNode()) badParent++;
			if (node.listChildren().length) fail(file, `${node.getName()} has children`);
			// transforms: identity, or the stowed mount pose
			const m = node.getMatrix();
			const want = elev.has(p.node) ? mount.check[mount.glb_pose].elev : trav.has(p.node) ? mount.check[mount.glb_pose].trav : IDENTITY;
			if (!close(m, want, 1e-5)) moved++;
			if (key !== 'edges') {
				const x = node.getExtras();
				const isDecal = p.material_key === 'decal';
				const hostAsm = isDecal && x.host ? byNode.get(x.host)?.assembly : p.assembly;
				const ok =
					x.number === p.number &&
					x.assembly === p.assembly &&
					x.material_key === p.material_key &&
					x.material_class === p.material_class &&
					x.explode_stage === 2 &&
					Array.isArray(x.explode_offset) &&
					close(x.explode_offset, glOffset(p.explode_offset), 1.5e-4) &&
					(x.mount_group || '') === (p.mount_group || '') &&
					parent?.getExtras().assembly === hostAsm;
				if (!ok) {
					if (badExtras < 3) console.log('   extras differ', p.node, JSON.stringify(x));
					badExtras++;
				}
			}
			const mesh = node.getMesh();
			if (!mesh) {
				if (key !== 'edges') fail(file, `${p.node} has no mesh`);
				continue;
			}
			for (const prim of mesh.listPrimitives()) {
				const pos = prim.getAttribute('POSITION');
				const arr = pos.getArray();
				if (!(arr instanceof Float32Array)) fail(file, `${p.node} positions are not float`);
				for (let i = 0; i < Math.min(arr.length, 300); i++) {
					const g = arr[i] / model.position_grid_m;
					if (Math.abs(g - Math.round(g)) > 1e-3) unsnapped++;
				}
				if (key === 'edges') {
					if (prim.getMode() !== Primitive.Mode.LINES) badMode++;
					if (prim.listSemantics().join() !== 'POSITION') badAttr++;
				} else {
					if (prim.getMode() !== Primitive.Mode.TRIANGLES) badMode++;
					triangles += prim.getIndices().getCount() / 3;
					const col = prim.getAttribute('COLOR_0');
					if (!col) noColor++;
					if (!prim.getAttribute('NORMAL')) badAttr++;
					const mat = prim.getMaterial();
					if (!mat) fail(file, `${p.node} has a primitive without material`);
					else materials.add(mat.getName());
					const uv = prim.getAttribute('TEXCOORD_0');
					if (mat && mat.getName() === 'RJ28_decal' && !uv) fail(file, `${p.node} decal has no UVs`);
				}
			}
		}
		if (badParent) fail(file, `${badParent} part nodes are not direct children of an assembly node`);
		if (moved) fail(file, `${moved} part nodes carry a transform other than identity or the stowed mount pose`);
		if (badExtras) fail(file, `${badExtras} part nodes have extras that disagree with parts.json`);
		if (noColor) fail(file, `${noColor} primitives without COLOR_0`);
		if (badMode) fail(file, `${badMode} primitives in the wrong mode`);
		if (badAttr) fail(file, `${badAttr} primitives with the wrong attributes`);
		if (unsnapped) fail(file, `${unsnapped} sampled position components off the grid`);

		for (const name of asmNodes) {
			const n = named.get(name);
			if (!close(n.getMatrix(), IDENTITY, 1e-9)) fail(file, `${name} has a transform`);
			if (key === 'edges') continue;
			const x = n.getExtras();
			if (!assemblies.has(x.assembly) || x.explode_stage !== 1 || !Array.isArray(x.explode_offset) || !x.title) fail(file, `${name} extras incomplete`);
		}

		if (key !== 'edges') {
			const [lo, hi] = TRIANGLES[key];
			if (triangles < lo || triangles > hi) fail(file, `${triangles} triangles, outside ${lo}-${hi}`);
			const mats = [...materials].sort();
			const allMats = root.listMaterials().map((m) => m.getName()).sort();
			if (mats.join() !== allMats.join()) fail(file, 'unused materials in the file');
			if (mats.length > 16 || mats.some((m) => !m.startsWith('RJ28_'))) fail(file, `materials: ${mats.join(' ')}`);
			const wantMats = [...new Set(parts.map((p) => `RJ28_${p.material_key}`))];
			for (const m of wantMats) if (!materials.has(m)) fail(file, `material ${m} of parts.json is not in the file`);
			const decal = root.listMaterials().find((m) => m.getName() === 'RJ28_decal');
			if (!decal || !decal.getBaseColorTexture() || decal.getAlphaMode() !== 'BLEND') fail(file, 'decal material lost its atlas or its alpha blend');
			if (root.listTextures().length !== 1) fail(file, `${root.listTextures().length} textures, expected the decal atlas only`);

			// joint axes: 46 under AXES, local +Z is the axis
			const axesNode = named.get('AXES');
			const axisNodes = axesNode ? axesNode.listChildren() : [];
			if (axisNodes.length !== 46) fail(file, `${axisNodes.length} AXIS nodes under AXES, expected 46`);
			let badAxis = 0;
			for (const n of axisNodes) {
				const m = n.getWorldMatrix();
				const x = n.getExtras();
				if (!x.axis || !close([m[8], m[9], m[10]], x.axis, 1e-4) || !close([m[12], m[13], m[14]], x.origin, 1e-4)) badAxis++;
			}
			if (badAxis) fail(file, `${badAxis} AXIS nodes whose local +Z or origin disagrees with their extras`);
			for (const r of mount.riders) if (!named.has(r.node)) fail(file, `rider ${r.node} missing`);
			const ea = named.get(mount.elevation.axis_node)?.getExtras();
			if (!ea || !close(ea.origin, mount.elevation.pivot, 1e-4)) fail(file, 'elevation pivot disagrees with AXIS_mount_elevation');

			console.log(`VERIFY ${file} ${bytes} bytes, ${nodes.length} nodes, ${partNodes.length} parts, ${triangles} triangles, materials: ${mats.map((m) => m.slice(5)).join(' ')}`);
		} else {
			console.log(`VERIFY ${file} ${bytes} bytes, ${nodes.length} nodes, ${partNodes.length} parts`);
		}

		// energy chain morph
		const chain = named.get(mount.energy_chain.node)?.getMesh();
		const prim = chain?.listPrimitives()[0];
		if (!chain || !prim || prim.listTargets().length !== 1 || !close(chain.getWeights(), [mount.energy_chain.glb_weight]) ||
			(chain.getExtras().targetNames || [])[0] !== mount.energy_chain.target) {
			fail(file, 'energy chain morph target missing or not at the stowed weight');
		}
		for (const g of ['elev', 'trav']) for (const n of mount.groups[g].nodes) if (!named.has(n)) fail(file, `mount ${g} node ${n} missing`);

		if (key !== 'edges') {
			// uncompressed copy for the Blender check
			for (const e of root.listExtensionsUsed()) if (e.extensionName === 'EXT_meshopt_compression') e.dispose();
			await io.write(join(RAW, `check_${key}.glb`), doc);
		}
		console.log(`VERIFY ${file} ${failures === before ? 'PASS' : 'FAIL'}`);
	}

	// stations
	const ids = stations.map((s) => s.id).join();
	if (ids !== '00,01,02,03,04,05,06,07,08,09') fail('stations.json', `ids ${ids}`);
	for (const s of stations) {
		for (const k of ['section', 'title', 'position', 'target', 'lens_mm', 'sensor_mm', 'mount', 'focus', 'highlight', 'xray']) {
			if (!(k in s)) fail('stations.json', `${s.id} lacks ${k}`);
		}
		if (!byNode.has(s.focus) && !assemblies.has(s.focus)) fail('stations.json', `${s.id} focus ${s.focus} is neither a part node nor an assembly`);
		for (const a of s.highlight) if (!assemblies.has(a)) fail('stations.json', `${s.id} highlights unknown assembly ${a}`);
		if (!(s.mount in mount.states)) fail('stations.json', `${s.id} mount ${s.mount}`);
	}
	console.log(`VERIFY stations.json ${stations.length} stations`);
	console.log(failures ? `VERIFY ${failures} FAILURES` : 'VERIFY ALL PASS');
	process.exit(failures ? 1 : 0);
}

main().catch((e) => {
	console.error(e);
	process.exit(1);
});
