import fs from "node:fs";
import { fileURLToPath } from "node:url";

const wasmPath = fileURLToPath(
  new URL("./sha3_wasm_bg.wasm", import.meta.url)
);

function loadWasm() {
  const bytes = fs.readFileSync(wasmPath);
  const module = new WebAssembly.Module(bytes);
  const instance = new WebAssembly.Instance(module, {});
  return instance.exports;
}

function writeString(exports, value) {
  const bytes = Buffer.from(value, "utf8");
  const ptr = exports.__wbindgen_export_0(bytes.length, 1);
  new Uint8Array(exports.memory.buffer).set(bytes, ptr);
  return [ptr, bytes.length];
}

function solve(input) {
  const exports = loadWasm();
  const memory = exports.memory;

  const retptr = exports.__wbindgen_add_to_stack_pointer(-16);

  try {
    const [challengePtr, challengeLen] =
      writeString(exports, String(input.challenge));
    const [prefixPtr, prefixLen] =
      writeString(exports, String(input.prefix));

    exports.wasm_solve(
      retptr,
      challengePtr,
      challengeLen,
      prefixPtr,
      prefixLen,
      Number(input.difficulty)
    );

    const view = new DataView(memory.buffer);
    const status = view.getInt32(retptr, true);
    const answer = view.getFloat64(retptr + 8, true);

    if (status === 0 || !Number.isFinite(answer)) {
      return null;
    }

    return Math.trunc(answer);
  } finally {
    exports.__wbindgen_add_to_stack_pointer(16);
  }
}

try {
  if (process.argv.includes("--inspect")) {
    const exports = loadWasm();
    console.log(JSON.stringify({
      status: "ok",
      wasm: wasmPath,
      exports: Object.keys(exports)
    }));
    process.exit(0);
  }

  let raw = "";
  for await (const chunk of process.stdin) raw += chunk;

  const input = JSON.parse(raw);
  const answer = solve(input);

  console.log(JSON.stringify({ answer }));
} catch (error) {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
}
