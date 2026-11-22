// Compress the raw GLBs from the Blender export into the files the site loads,
// and write the manifest site/src/data/model.json.
//
//   node tools/gltf/optimize.mjs
//
// in   blender/out/export/rj28_lod0.raw.glb, rj28_lod1.raw.glb, rj28_edges.raw.glb
// out  site/public/models/rj28_lod0.glb, rj28_lod1.glb, rj28_edges.glb
//      site/src/data/model.json
//
// Nodes are never joined, flattened, instanced or given a transform: the site
// sets node matrices itself (mount pose, exploded view). That rules out the
// usual position quantisation, which hides a scale and an offset in each node.
// Positions stay 32-bit floats snapped to a grid of 1/32768 m (0.03 mm); the
// zeroed low bits are what the meshopt codec then squeezes out. Normals go to
// 12 bits in LOD0 and 8 in LOD1, COLOR_0 to 8, decal UVs to 16.

import { readFileSync, writeFileSync, mkdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { NodeIO, PropertyType, Primitive, VertexLayout } from '@gltf-transform/core';
import { ALL_EXTENSIONS, EXTMeshoptCompression, KHRMeshQuantization } from '@gltf-transform/extensions';
import { dedup, prune, weld, reorder, quantize, textureCompress } from '@gltf-transform/functions';
import { MeshoptDecoder, MeshoptEncoder } from 'meshoptimizer';
import sharp from 'sharp';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const RAW = join(ROOT, 'blender', 'out', 'export');
const MODELS = join(ROOT, 'site', 'public', 'models');
const DATA = join(ROOT, 'site', 'src', 'data');
const GRID = 32768; // position steps per metre

const FILES = [
	{ key: 'lod0', raw: 'rj28_lod0.raw.glb', out: 'rj28_lod0.glb', atlas: 2048, normalBits: 12, budget: 30e6 },
	{ key: 'lod1', raw: 'rj28_lod1.raw.glb', out: 'rj28_lod1.glb', atlas: 1024, normalBits: 8, budget: 5e6 },
	{ key: 'edges', raw: 'rj28_edges.raw.glb', out: 'rj28_edges.glb', atlas: 0, normalBits: 0, budget: 3e6 },
];

/** Snap POSITION (and morph POSITION deltas) to the grid, keeping them float. */
function snapPositions() {
	return (doc) => {
		const done = new Set();
		const snap = (acc) => {
			if (!acc || done.has(acc)) return;
			done.add(acc);
			const a = acc.getArray();
			for (let i = 0; i < a.length; i++) a[i] = Math.round(a[i] * GRID) / GRID;
			acc.setArray(a);
		};
		for (const mesh of doc.getRoot().listMeshes()) {
			for (const prim of mesh.listPrimitives()) {
				snap(prim.getAttribute('POSITION'));
				for (const target of prim.listTargets()) snap(target.getAttribute('POSITION'));
			}
		}
	};
}

function stats(doc) {
	const root = doc.getRoot();
	let triangles = 0;
	let segments = 0;
	let vertices = 0;
	let primitives = 0;
	for (const mesh of root.listMeshes()) {
		for (const prim of mesh.listPrimitives()) {
			primitives++;
			const n = prim.getIndices() ? prim.getIndices().getCount() : prim.getAttribute('POSITION').getCount();
			if (prim.getMode() === Primitive.Mode.TRIANGLES) triangles += n / 3;
			if (prim.getMode() === Primitive.Mode.LINES) segments += n / 2;
			vertices += prim.getAttribute('POSITION').getCount();
		}
	}
	const nodes = root.listNodes();
	return {
		nodes: nodes.length,
		part_nodes: nodes.filter((n) => /^RJ28-\d\d-\d\d\d_/.test(n.getName())).length,
		assembly_nodes: nodes.filter((n) => /^RJ28-\d\d_/.test(n.getName())).length,
		axis_nodes: nodes.filter((n) => n.getName().startsWith('AXIS_')).length,
		meshes: root.listMeshes().length,
		primitives,
		triangles,
		segments,
		vertices,
	};
}

async function main() {
	await MeshoptEncoder.ready;
	await MeshoptDecoder.ready;
	const io = new NodeIO()
		.registerExtensions(ALL_EXTENSIONS)
		.registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder })
		.setVertexLayout(VertexLayout.SEPARATE);
	mkdirSync(MODELS, { recursive: true });
	const blender = JSON.parse(readFileSync(join(RAW, 'stats.json'), 'utf8'));
	const manifest = {
		axes: 'glTF: +Y up, the robot faces +Z, its left is +X; metres',
		pose: 'stowed',
		parts: blender.parts,
		position_grid_m: 1 / GRID,
		vertex_color: {
			attribute: 'COLOR_0',
			note: 'Data, not colour. Do not multiply it into the base colour.',
			r: 'edge mask: 1 on the faces of convex bevels and chamfers, 0 elsewhere; per face corner. All 0 in lod1, which has no bevels.',
			g: 'unused, 0',
			b: 'cavity: short-range occlusion (40 mm) on the assembled robot, mount stowed; 0 open, 1 buried. Marks crevices and packed mechanism; wide flat faces are left at 0.',
		},
		uv: 'TEXCOORD_0 only on parts with a decal, mesh or braid material',
		files: {},
	};
	for (const f of FILES) {
		const doc = await io.read(join(RAW, f.raw));
		await doc.transform(
			dedup({ propertyTypes: [PropertyType.ACCESSOR, PropertyType.MATERIAL, PropertyType.TEXTURE] }),
			prune({ keepLeaves: true, keepAttributes: true, keepExtras: true, keepSolidTextures: true }),
			// the line model arrives already ordered end to end by the exporter; reordering would undo that
			...(f.key === 'edges' ? [] : [weld(), reorder({ encoder: MeshoptEncoder, target: 'size', cleanup: false })]),
			snapPositions(),
			quantize({
				pattern: /^(NORMAL|COLOR_0|TEXCOORD_0)$/,
				patternTargets: /^$/,
				quantizeNormal: Number(process.env.RJ28_NORMAL_BITS || f.normalBits) || 8,
				quantizeColor: 8,
				quantizeTexcoord: 16,
				cleanup: false,
			}),
			// reorder and quantize leave the accessors they replaced behind
			prune({ propertyTypes: [PropertyType.ACCESSOR], keepLeaves: true, keepAttributes: true, keepExtras: true, keepSolidTextures: true }),
		);
		// normals are now normalised 16-bit integers, which the core format does not allow
		if (f.key !== 'edges') doc.createExtension(KHRMeshQuantization).setRequired(true);
		let texture = null;
		if (f.atlas) {
			await doc.transform(
				textureCompress({ encoder: sharp, targetFormat: 'webp', resize: [f.atlas, f.atlas], lossless: true, effort: 100 }),
			);
			const tex = doc.getRoot().listTextures();
			if (tex.length !== 1) throw new Error(`${f.raw}: expected the decal atlas only, found ${tex.length} textures`);
			tex[0].setName('rj28_decals').setURI('');
			texture = { name: 'rj28_decals', mime: tex[0].getMimeType(), size: tex[0].getSize(), bytes: tex[0].getImage().byteLength };
		}
		doc.getRoot().getAsset().generator = 'rj28 export';
		const meshopt = doc
			.createExtension(EXTMeshoptCompression)
			.setRequired(true)
			.setEncoderOptions({ method: EXTMeshoptCompression.EncoderMethod.QUANTIZE });
		// One compressed buffer view per attribute layout instead of one per accessor. The writer groups
		// vertex attributes by the primitive that owns them; with 1,083 primitives that is 0.8 MB of JSON.
		const prewrite = meshopt.prewrite.bind(meshopt);
		meshopt.prewrite = (context, propertyType) => {
			context.accessorUsageGroupedByParent.delete('ARRAY_BUFFER');
			return prewrite(context, propertyType);
		};
		const out = join(MODELS, f.out);
		await io.write(out, doc);
		const bytes = statSync(out).size;
		const s = stats(doc);
		const entry = { file: f.out, url: `models/${f.out}`, bytes, ...s };
		if (f.key === 'edges') {
			delete entry.triangles;
			delete entry.axis_nodes;
		} else {
			delete entry.segments;
			entry.materials = doc.getRoot().listMaterials().map((m) => m.getName()).sort();
			entry.texture = texture;
		}
		entry.extensions = doc.getRoot().listExtensionsUsed().map((e) => e.extensionName).sort();
		manifest.files[f.key] = entry;
		const flag = bytes > f.budget ? 'OVER BUDGET' : 'ok';
		console.log(`OPTIMIZE ${f.out} ${bytes} bytes (${(bytes / 1e6).toFixed(2)} MB, budget ${f.budget / 1e6} MB ${flag})`, JSON.stringify(s));
	}
	if (blender.hdri) manifest.hdri = { file: blender.hdri.file, url: `hdri/${blender.hdri.file}`, bytes: blender.hdri.bytes, width: blender.hdri.width, height: blender.hdri.height };
	manifest.materials = manifest.files.lod0.materials;
	writeFileSync(join(DATA, 'model.json'), JSON.stringify(manifest, null, 1) + '\n');
	console.log('OPTIMIZE model.json written');
}

main().catch((e) => {
	console.error(e);
	process.exit(1);
});
