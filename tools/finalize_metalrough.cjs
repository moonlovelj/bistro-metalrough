/** Repair invalid tangents in the baked copy, then validate every resource.
 * Dependencies come from the installed @gltf-transform/cli (4.5.1).
 * Set GLTF_TRANSFORM_CLI_ROOT to override its installation directory.
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const {createRequire} = require('node:module');

const project = path.resolve(__dirname, '..');
const output = path.resolve(process.argv[2] || path.join(project, 'build', 'bistro'));
if (output === project || !output.startsWith(project + path.sep)) {
  throw new Error('Output must be a separate directory below the project');
}
const sourceRoot = path.resolve(process.argv[3] || path.join(project, '..', 'niagara_bistro-source'));
let dependencyAnchor;
if (process.env.GLTF_TRANSFORM_CLI_ROOT) {
  dependencyAnchor = path.join(process.env.GLTF_TRANSFORM_CLI_ROOT, 'package.json');
} else {
  try {
    dependencyAnchor = require.resolve('@gltf-transform/cli');
  } catch {
    dependencyAnchor = path.join(os.homedir(), 'AppData', 'Roaming', 'npm', 'node_modules', '@gltf-transform', 'cli', 'package.json');
  }
}
const deps = createRequire(dependencyAnchor);
const {NodeIO} = deps('@gltf-transform/core');
const {ALL_EXTENSIONS} = deps('@gltf-transform/extensions');
const {unweldPrimitive, weldPrimitive} = deps('@gltf-transform/functions');
const {generateTangents} = deps('mikktspace');
const validator = deps('gltf-validator');

// Compare the rendered attribute sequence, allowing exact vertex reindexing
// and tangent seam splits but no changes to positions, normals or UVs.
function geometryHash(document) {
  const hash = crypto.createHash('sha256');
  for (const mesh of document.getRoot().listMeshes()) {
    hash.update(mesh.getName());
    for (const primitive of mesh.listPrimitives()) {
      hash.update(String(primitive.getMode()));
      const indices = primitive.getIndices()?.getArray();
      for (const semantic of primitive.listSemantics().filter(s => s !== 'TANGENT').sort()) {
        const attribute = primitive.getAttribute(semantic);
        const array = attribute.getArray();
        const elementBytes = attribute.getElementSize() * array.BYTES_PER_ELEMENT;
        const bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength);
        hash.update(`${semantic}:${attribute.getType()}:${attribute.getComponentType()}:${attribute.getNormalized()}`);
        if (indices) {
          const expanded = Buffer.allocUnsafe(indices.length * elementBytes);
          for (let i = 0; i < indices.length; i++) {
            bytes.copy(expanded, i * elementBytes, indices[i] * elementBytes, (indices[i] + 1) * elementBytes);
          }
          hash.update(expanded);
        } else {
          hash.update(bytes);
        }
      }
    }
  }
  return hash.digest('hex');
}

function invalidTangent(array, offset) {
  const length = Math.hypot(array[offset], array[offset + 1], array[offset + 2]);
  return !Number.isFinite(length) || Math.abs(length - 1) > 0.0001 || ![1, -1].includes(array[offset + 3]);
}

async function main() {
  const filename = path.join(output, 'bistro_metalrough.gltf');
  const reportFile = path.join(output, 'conversion_report.json');
  const report = JSON.parse(await fs.readFile(reportFile, 'utf8'));
  const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
  console.log('Loading baked model and recording geometry checksum...');
  const document = await io.read(filename);
  const before = geometryHash(document);
  const stats = {rebuiltPrimitives: 0, removedUnusedTangentAttributes: 0, degenerateCornerFallbacks: 0};
  for (const mesh of document.getRoot().listMeshes()) {
    for (const primitive of mesh.listPrimitives()) {
      const tangent = primitive.getAttribute('TANGENT');
      if (!primitive.getMaterial()?.getNormalTexture()) {
        if (tangent) {
          primitive.setAttribute('TANGENT', null);
          if (tangent.listParents().length === 1) tangent.dispose();
          stats.removedUnusedTangentAttributes++;
        }
        continue;
      }
      const old = tangent?.getArray();
      let needsRepair = !old;
      for (let i = 0; old && i < old.length && !needsRepair; i += 4) needsRepair = invalidTangent(old, i);
      if (!needsRepair) continue;
      if (primitive.getMode() !== 4 || !primitive.getAttribute('NORMAL') || !primitive.getAttribute('TEXCOORD_0')) {
        throw new Error(`Cannot rebuild tangents on ${mesh.getName()}`);
      }
      // MikkTSpace expects triangle corners. Re-weld only bitwise-identical
      // vertices afterwards, retaining any tangent discontinuities it creates.
      unweldPrimitive(primitive);
      const previous = primitive.getAttribute('TANGENT');
      const position = primitive.getAttribute('POSITION');
      const normals = primitive.getAttribute('NORMAL').getArray();
      const uv = primitive.getAttribute('TEXCOORD_0').getArray();
      const rebuilt = generateTangents(position.getArray(), normals, uv);
      for (let i = 0, vertex = 0; i < rebuilt.length; i += 4, vertex++) {
        rebuilt[i + 3] *= -1; // glTF UV handedness convention.
        let x = rebuilt[i], y = rebuilt[i + 1], z = rebuilt[i + 2];
        let length = Math.hypot(x, y, z);
        if (!Number.isFinite(length) || length < 1e-10 || ![1, -1].includes(rebuilt[i + 3])) {
          // A degenerate UV triangle has no uniquely defined tangent. Give it
          // a finite basis perpendicular to its unchanged vertex normal.
          const n = normals.subarray(vertex * 3, vertex * 3 + 3);
          const nLength = Math.hypot(...n);
          if (!Number.isFinite(nLength) || nLength < 1e-10) throw new Error('Invalid source normal');
          const nx = n[0] / nLength, ny = n[1] / nLength, nz = n[2] / nLength;
          if (Math.abs(nx) <= Math.abs(ny) && Math.abs(nx) <= Math.abs(nz)) {
            x = 0; y = nz; z = -ny;
          } else if (Math.abs(ny) <= Math.abs(nz)) {
            x = -nz; y = 0; z = nx;
          } else {
            x = ny; y = -nx; z = 0;
          }
          length = Math.hypot(x, y, z);
          rebuilt[i + 3] = 1;
          stats.degenerateCornerFallbacks++;
        }
        rebuilt[i] = x / length;
        rebuilt[i + 1] = y / length;
        rebuilt[i + 2] = z / length;
      }
      const replacement = document.createAccessor().setType('VEC4').setArray(rebuilt).setBuffer(position.getBuffer());
      primitive.setAttribute('TANGENT', replacement);
      if (previous && previous.listParents().length === 1) previous.dispose();
      weldPrimitive(primitive);
      stats.rebuiltPrimitives++;
      if (stats.rebuiltPrimitives % 10 === 0) console.log(`Rebuilt tangents on ${stats.rebuiltPrimitives} primitives`);
    }
  }
  for (const accessor of document.getRoot().listAccessors()) {
    if (accessor.listParents().length === 1) accessor.dispose();
  }
  const after = geometryHash(document);
  if (before !== after) throw new Error('Geometry changed while rebuilding tangents');
  report.tangents = stats;
  report.geometry_unchanged = true;
  report.rendered_geometry_sha256 = before;
  console.log('Writing repaired model...');
  await io.write(filename, document);
  console.log('Validating glTF, all external buffers and all images...');
  const validation = await validator.validateString(await fs.readFile(filename, 'utf8'), {
    uri: 'bistro_metalrough.gltf',
    maxIssues: 0,
    externalResourceFunction: async uri => {
      const resolved = path.resolve(output, decodeURIComponent(uri));
      if (!resolved.startsWith(output + path.sep)) throw new Error(`External resource outside output directory: ${uri}`);
      return new Uint8Array(await fs.readFile(resolved));
    },
  });
  await fs.writeFile(path.join(output, 'validation.json'), JSON.stringify(validation, null, 2));
  const result = JSON.parse(await fs.readFile(filename, 'utf8'));
  const forbidden = ['KHR_materials_pbrSpecularGlossiness', 'KHR_materials_specular', 'KHR_materials_ior', 'MSFT_texture_dds'];
  if (forbidden.some(ext => result.extensionsUsed?.includes(ext) || result.extensionsRequired?.includes(ext) || result.materials.some(m => m.extensions?.[ext]))) {
    throw new Error('Unexpected spec/gloss, specular, IOR or DDS extension in output');
  }
  if (!result.materials.every(m => m.pbrMetallicRoughness)) throw new Error('Missing core MR material');
  for (const [relative, expected] of Object.entries(report.source_hashes)) {
    const actual = crypto.createHash('sha256').update(await fs.readFile(path.join(sourceRoot, relative))).digest('hex');
    if (actual !== expected) throw new Error(`Tracked source changed: ${relative}`);
  }
  report.source_files_unchanged = true;
  report.validation = {validator: validator.version(), errors: validation.issues.numErrors, warnings: validation.issues.numWarnings, infos: validation.issues.numInfos, hints: validation.issues.numHints};
  report.output = {materials: result.materials.length, meshes: result.meshes.length, nodes: result.nodes.length, animations: result.animations?.length || 0, images: result.images.length, extensions: result.extensionsUsed};
  await fs.writeFile(reportFile, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({tangents: stats, validation: report.validation, output: report.output}, null, 2));
  if (validation.issues.numErrors) process.exitCode = 1;
}

main().catch(error => { console.error(error); process.exitCode = 1; });
